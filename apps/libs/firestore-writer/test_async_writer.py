"""
測試 AsyncFirestoreWriter：寫入不阻塞呼叫端、依序執行、失敗不影響 worker、收尾時清空佇列
"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))

from firestore_writer.async_writer import AsyncFirestoreWriter


class FakeWriter:
    """記錄寫入內容；可用 gate 讓寫入卡住，或指定哪些文件寫入失敗"""

    def __init__(self, fail_ids: set[str] | None = None, gate: threading.Event | None = None) -> None:
        self.writes: list[tuple[str, str | None, dict, bool]] = []
        self._fail_ids = fail_ids or set()
        self._gate = gate
        self.write_threads: set[str] = set()
        self.created_at_flags: list[bool] = []

    def write_document(
        self,
        collection: str,
        data: dict,
        document_id: str | None = None,
        merge: bool = False,
        set_created_at: bool = True,
    ) -> str | None:
        if self._gate is not None:
            self._gate.wait(5)
        self.write_threads.add(threading.current_thread().name)
        if document_id in self._fail_ids:
            raise RuntimeError("firestore down")
        self.writes.append((collection, document_id, dict(data), merge))
        self.created_at_flags.append(set_created_at)
        return document_id


def test_write_document_returns_immediately_while_write_is_blocked() -> None:
    """Firestore 寫入卡住時，呼叫端不會被卡住"""
    gate = threading.Event()
    fake = FakeWriter(gate=gate)
    writer = AsyncFirestoreWriter(fake)

    result = writer.write_document("market/MXF/20260727", data={"close": 1}, document_id="1030")

    assert result == "1030"
    assert fake.writes == []  # 還沒寫完，但已經返回
    assert writer.get_stats()["pending"] == 1

    gate.set()
    assert writer.close() is True
    assert fake.writes == [("market/MXF/20260727", "1030", {"close": 1}, False)]


def test_writes_run_in_worker_thread_in_order() -> None:
    fake = FakeWriter()
    writer = AsyncFirestoreWriter(fake)

    for i in range(20):
        writer.write_document("c", data={"n": i}, document_id=str(i))
    assert writer.close() is True

    assert [w[1] for w in fake.writes] == [str(i) for i in range(20)]
    assert fake.write_threads == {"firestore-writer-0"}


def test_data_is_copied_when_submitted() -> None:
    """排入後呼叫端再修改字典，不影響實際寫入的內容"""
    gate = threading.Event()
    fake = FakeWriter(gate=gate)
    writer = AsyncFirestoreWriter(fake)
    data = {"close": 1}

    writer.write_document("c", data=data, document_id="a")
    data["close"] = 999
    gate.set()
    writer.close()

    assert fake.writes[0][2] == {"close": 1}


def test_merge_flag_is_forwarded_only_when_requested() -> None:
    fake = FakeWriter()
    writer = AsyncFirestoreWriter(fake)

    writer.write_document("c", data={"a": 1}, document_id="x")
    writer.write_document("c", data={"a": 2}, document_id="y", merge=True)
    writer.close()

    assert [(w[1], w[3]) for w in fake.writes] == [("x", False), ("y", True)]


def test_set_created_at_option_is_forwarded() -> None:
    """補寫既有文件時 set_created_at=False 要傳到底層 writer，避免重設建立時間"""
    fake = FakeWriter()
    writer = AsyncFirestoreWriter(fake)

    writer.write_document("c", data={"a": 1}, document_id="x")
    writer.write_document("c", data={"a": 2}, document_id="y", merge=True, set_created_at=False)
    writer.close()

    assert fake.created_at_flags == [True, False]


def test_failed_write_is_counted_and_worker_keeps_running(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeWriter(fail_ids={"bad"})
    writer = AsyncFirestoreWriter(fake)

    writer.write_document("c", data={"a": 1}, document_id="bad")
    writer.write_document("c", data={"a": 2}, document_id="good")
    assert writer.close() is True

    assert [w[1] for w in fake.writes] == ["good"]
    assert writer.get_stats() == {"written": 1, "failed": 1, "dropped": 0, "pending": 0}
    assert "非同步寫入失敗" in capsys.readouterr().out


def test_full_queue_drops_new_writes_without_blocking() -> None:
    gate = threading.Event()
    fake = FakeWriter(gate=gate)
    writer = AsyncFirestoreWriter(fake, max_queue_size=2)

    results = [writer.write_document("c", data={"n": i}, document_id=str(i)) for i in range(6)]

    # worker 取走第 1 筆（卡在 gate）後，佇列最多再容納 2 筆；其餘被丟棄
    accepted = [r for r in results if r is not None]
    assert 2 <= len(accepted) <= 3
    assert writer.get_stats()["dropped"] == 6 - len(accepted)

    gate.set()
    assert writer.close() is True
    assert len(fake.writes) == len(accepted)


def test_close_drains_pending_writes_before_returning() -> None:
    """收尾時已排入的寫入都要寫完（收盤全部 flush 的資料不能遺失）"""
    fake = FakeWriter()
    writer = AsyncFirestoreWriter(fake)

    for i in range(100):
        writer.write_document("c", data={"n": i}, document_id=str(i))

    assert writer.close() is True
    assert len(fake.writes) == 100


def test_close_times_out_when_write_is_stuck() -> None:
    gate = threading.Event()
    fake = FakeWriter(gate=gate)
    writer = AsyncFirestoreWriter(fake)
    writer.write_document("c", data={"a": 1}, document_id="stuck")

    assert writer.close(drain_timeout=0.1) is False

    gate.set()


def test_write_after_close_is_dropped() -> None:
    fake = FakeWriter()
    writer = AsyncFirestoreWriter(fake)
    writer.close()

    assert writer.write_document("c", data={"a": 1}, document_id="late") is None

    assert fake.writes == []
    assert writer.get_stats()["dropped"] == 1


def test_close_can_be_called_repeatedly(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeWriter()
    writer = AsyncFirestoreWriter(fake)
    writer.close()
    capsys.readouterr()

    assert writer.close() is True
    assert capsys.readouterr().out == ""


def test_wait_until_idle_returns_after_all_processed() -> None:
    gate = threading.Event()
    fake = FakeWriter(gate=gate)
    writer = AsyncFirestoreWriter(fake)
    writer.write_document("c", data={"a": 1}, document_id="x")

    assert writer.wait_until_idle(timeout=0.05) is False
    gate.set()
    assert writer.wait_until_idle(timeout=3) is True

    writer.close()
