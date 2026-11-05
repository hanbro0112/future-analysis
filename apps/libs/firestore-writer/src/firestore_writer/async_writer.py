"""
非同步 Firestore 寫入模組
把寫入工作交給獨立的 worker 執行緒，避免 Firestore 的延遲與重試（最久數秒）
卡住呼叫端（例如處理 tick 的 Pub/Sub 回調執行緒）。
"""
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .client import FirestoreWriter

# 佇列上限：寫入速度跟不上時丟棄新的寫入並計數，而不是讓記憶體無限成長
DEFAULT_MAX_QUEUE_SIZE = 10_000

# 收尾時最多等待佇列清空的秒數
DEFAULT_DRAIN_TIMEOUT_SECONDS = 30.0

# 寫入失敗的 log 節流：第 1 次與之後每 N 次才印一行
WRITE_FAILURE_LOG_EVERY = 20


@dataclass
class _WriteTask:
    """待寫入的一筆文件"""
    collection: str
    document_id: Optional[str]
    data: Dict[str, Any]
    merge: bool
    set_created_at: bool


class AsyncFirestoreWriter:
    """
    包裝 FirestoreWriter，寫入改由背景 worker 依序執行。

    write_document() 只把工作放進有上限的佇列就返回，介面與 FirestoreWriter 相容，
    現有呼叫端不需要修改。close() 會先等佇列寫完（有逾時上限）再停止 worker；
    底層 FirestoreWriter 的連線仍由建立它的人負責關閉。
    """

    def __init__(
        self,
        writer: FirestoreWriter,
        max_queue_size: int = DEFAULT_MAX_QUEUE_SIZE,
        num_workers: int = 1,
    ) -> None:
        """
        Args:
            writer: 實際執行寫入（含重試）的 FirestoreWriter
            max_queue_size: 佇列上限，滿了就丟棄新的寫入
            num_workers: worker 數量；同一份文件的先後兩次寫入請用 1 個 worker 以保持順序
        """
        self._writer = writer
        self._queue: queue.Queue[Optional[_WriteTask]] = queue.Queue(maxsize=max_queue_size)
        self._closed = False
        self._lock = threading.Lock()
        self._idle = threading.Condition(self._lock)
        self._pending = 0  # 已接受但尚未處理完（含正在寫）的數量

        self._written_count = 0
        self._failed_count = 0
        self._dropped_count = 0

        self._workers = [
            threading.Thread(target=self._run, name=f"firestore-writer-{i}", daemon=True)
            for i in range(num_workers)
        ]
        for worker in self._workers:
            worker.start()

    def write_document(
        self,
        collection: str,
        document_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        merge: bool = False,
        set_created_at: bool = True,
    ) -> Optional[str]:
        """
        排入一筆寫入工作（不等待實際寫入完成），參數與 FirestoreWriter.write_document 相同。

        資料會先淺複製一份，呼叫端之後修改原字典不影響已排入的內容。

        Returns:
            文件 ID；佇列已滿或已關閉而被丟棄時回傳 None
        """
        task = _WriteTask(
            collection=collection,
            document_id=document_id,
            data=dict(data) if data is not None else {},
            merge=merge,
            set_created_at=set_created_at,
        )

        with self._lock:
            if self._closed:
                self._dropped_count += 1
                dropped = self._dropped_count
                accepted = False
            else:
                try:
                    self._queue.put_nowait(task)
                except queue.Full:
                    self._dropped_count += 1
                    dropped = self._dropped_count
                    accepted = False
                else:
                    self._pending += 1
                    accepted = True

        if not accepted:
            print(f"⚠️  Firestore 寫入佇列已滿或已關閉，丟棄 {collection}/{document_id}（累計 {dropped} 筆）")
            return None

        return document_id

    def wait_until_idle(self, timeout: float = DEFAULT_DRAIN_TIMEOUT_SECONDS) -> bool:
        """等待目前已排入的工作全部處理完（成功或失敗都算處理完）；逾時回傳 False"""
        deadline = time.monotonic() + timeout
        with self._idle:
            while self._pending > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._idle.wait(remaining)
        return True

    def close(self, drain_timeout: float = DEFAULT_DRAIN_TIMEOUT_SECONDS) -> bool:
        """
        停止接受新的寫入，等佇列寫完後停止 worker。可重複呼叫。

        Returns:
            True 代表所有已排入的寫入都處理完；False 代表逾時，仍有寫入未完成而被放棄
        """
        with self._lock:
            already_closed = self._closed
            self._closed = True

        if already_closed:
            return self.get_stats()["pending"] == 0

        drained = self.wait_until_idle(drain_timeout)
        if not drained:
            print(f"⚠️  Firestore 寫入佇列在 {drain_timeout:.0f} 秒內未清空，仍有 "
                  f"{self.get_stats()['pending']} 筆寫入被放棄")

        # 通知 worker 結束（佇列滿時可能放不進去，worker 為 daemon 執行緒，不會卡住結束）
        for _ in self._workers:
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                break
        for worker in self._workers:
            worker.join(timeout=1.0)

        stats = self.get_stats()
        print(f"📊 Firestore 非同步寫入統計: 成功 {stats['written']} / "
              f"失敗 {stats['failed']} / 丟棄 {stats['dropped']}")
        return drained

    def get_stats(self) -> Dict[str, int]:
        """取得寫入統計：written（成功）、failed（重試後仍失敗）、dropped（未排入）、pending（待處理）"""
        with self._lock:
            return {
                "written": self._written_count,
                "failed": self._failed_count,
                "dropped": self._dropped_count,
                "pending": self._pending,
            }

    def _run(self) -> None:
        """worker 主迴圈：依序取出工作寫入，任何例外都只記錄，不讓 worker 結束"""
        while True:
            task = self._queue.get()
            if task is None:
                return

            succeeded = False
            try:
                # 只傳入非預設值的選項，維持與只接受基本參數的 writer 相容
                options: Dict[str, Any] = {}
                if task.merge:
                    options["merge"] = True
                if not task.set_created_at:
                    options["set_created_at"] = False
                self._writer.write_document(
                    collection=task.collection,
                    data=task.data,
                    document_id=task.document_id,
                    **options,
                )
                succeeded = True
            except Exception as e:
                with self._lock:
                    self._failed_count += 1
                    failed = self._failed_count
                if failed == 1 or failed % WRITE_FAILURE_LOG_EVERY == 0:
                    print(f"❌ Firestore 非同步寫入失敗（累計 {failed} 筆）"
                          f"{task.collection}/{task.document_id}: {type(e).__name__}: {e}")
            finally:
                with self._idle:
                    if succeeded:
                        self._written_count += 1
                    self._pending -= 1
                    if self._pending == 0:
                        self._idle.notify_all()
