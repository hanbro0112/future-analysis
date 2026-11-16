"""
測試 Firestore 舊資料清理：cutoff 計算、日期解析、刪除額度預扣與批次刪除
"""
from datetime import date, datetime
from typing import Optional
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest
from google.cloud import firestore

import data_cleanup
from data_cleanup import (
    BATCH_SIZE,
    DAILY_REPORT_ID_RE,
    MARKET_SUBCOLLECTION_RE,
    PTT_POST_ID_RE,
    CleanupResult,
    FirestoreQuotaLedger,
    compute_cutoff,
    compute_grant,
    extract_date,
    parse_budget,
    quota_date_pacific,
    run_cleanup,
    subtract_months,
)

CUTOFF = date(2026, 8, 14)  # 台北 2026-11-14 − 3 個月


# ========== Firestore 假物件 ==========

class FakeDocRef:
    def __init__(self, path: str) -> None:
        self.path = path
        self.id = path.rsplit("/", 1)[-1]


class FakeCollection:
    def __init__(self, path: str, doc_ids: list[str]) -> None:
        self.path = path
        self.id = path.rsplit("/", 1)[-1]
        self._doc_ids = doc_ids

    def list_documents(self) -> list[FakeDocRef]:
        return [FakeDocRef(f"{self.path}/{doc_id}") for doc_id in self._doc_ids]


class FakeSymbolRef(FakeDocRef):
    def __init__(self, path: str, sub_collections: dict[str, int]) -> None:
        super().__init__(path)
        self._sub_collections = sub_collections

    def collections(self) -> list[FakeCollection]:
        return [
            FakeCollection(f"{self.path}/{name}", [f"{i:06d}" for i in range(count)])
            for name, count in self._sub_collections.items()
        ]


class FakeBatch:
    def __init__(self, db: "FakeDb") -> None:
        self._db = db
        self._refs: list[FakeDocRef] = []

    def delete(self, ref: FakeDocRef) -> None:
        self._refs.append(ref)

    def commit(self) -> None:
        if self._db.fail_commit:
            raise RuntimeError("commit 失敗")
        self._db.batch_sizes.append(len(self._refs))
        self._db.deleted_paths.extend(ref.path for ref in self._refs)


class FakeDb:
    """market: {商品: {子集合 ID: 文件數}}；top_level: {集合: [文件 ID]}"""

    def __init__(
        self,
        market: Optional[dict[str, dict[str, int]]] = None,
        top_level: Optional[dict[str, list[str]]] = None,
    ) -> None:
        self._market = market or {}
        self._top_level = top_level or {}
        self.fail_commit = False
        self.deleted_paths: list[str] = []
        self.batch_sizes: list[int] = []
        self.listed_collections: list[str] = []

    def collection(self, name: str) -> object:
        self.listed_collections.append(name)
        if name == "market":
            symbols = [FakeSymbolRef(f"market/{code}", subs) for code, subs in self._market.items()]
            return _Listable(symbols)
        return FakeCollection(name, self._top_level.get(name, []))

    def batch(self) -> FakeBatch:
        return FakeBatch(self)


class _Listable:
    def __init__(self, refs: list[FakeSymbolRef]) -> None:
        self._refs = refs

    def list_documents(self) -> list[FakeSymbolRef]:
        return self._refs


class InMemoryLedger:
    """與 FirestoreQuotaLedger 相同的預扣邏輯，但存在記憶體；used 跨多次 run 累計"""

    def __init__(self, budget: int, used: int = 0) -> None:
        self.budget = budget
        self.used = used

    def reserve(self, requested: int) -> int:
        granted, self.used = compute_grant(
            {"quota_date": "X", "deleted": self.used}, "X", self.budget, requested
        )
        return granted

    def remaining(self) -> int:
        return max(0, self.budget - self.used)


def _run(db: FakeDb, ledger: InMemoryLedger, dry_run: bool = False) -> CleanupResult:
    return run_cleanup(db, ledger, CUTOFF, ledger.budget, dry_run)  # type: ignore[arg-type]


# ========== cutoff 與日期解析 ==========

@pytest.mark.parametrize(
    ("day", "months", "expected"),
    [
        (date(2026, 11, 14), 3, date(2026, 8, 14)),
        (date(2026, 5, 31), 3, date(2026, 2, 28)),
        (date(2024, 5, 31), 3, date(2024, 2, 29)),
        (date(2026, 1, 15), 3, date(2025, 10, 15)),
        (date(2026, 3, 31), 1, date(2026, 2, 28)),
    ],
)
def test_subtract_months(day: date, months: int, expected: date) -> None:
    assert subtract_months(day, months) == expected


def test_compute_cutoff_uses_taipei_date() -> None:
    assert compute_cutoff(datetime(2026, 11, 14, 6, 0)) == date(2026, 8, 14)


@pytest.mark.parametrize(
    ("identifier", "pattern", "expected"),
    [
        ("20260101", MARKET_SUBCOLLECTION_RE, date(2026, 1, 1)),
        ("20260101_tick", MARKET_SUBCOLLECTION_RE, date(2026, 1, 1)),
        ("20261301", MARKET_SUBCOLLECTION_RE, None),  # 不合法月份
        ("20260101_other", MARKET_SUBCOLLECTION_RE, None),
        ("abc", MARKET_SUBCOLLECTION_RE, None),
        ("20260101", DAILY_REPORT_ID_RE, date(2026, 1, 1)),
        ("20260101_x", DAILY_REPORT_ID_RE, None),
        ("20260101_intraday", PTT_POST_ID_RE, date(2026, 1, 1)),
        ("20260101_afterhours", PTT_POST_ID_RE, date(2026, 1, 1)),
        ("20260101", PTT_POST_ID_RE, None),
    ],
)
def test_extract_date(identifier: str, pattern: object, expected: Optional[date]) -> None:
    assert extract_date(identifier, pattern) == expected  # type: ignore[arg-type]


def test_quota_date_uses_pacific_midnight() -> None:
    # 2026-11-14 06:00 台北 = 前一天 14:00 太平洋時間
    taipei = datetime(2026, 11, 14, 6, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    assert quota_date_pacific(taipei) == "20261113"
    # 台北 16:00 已跨過太平洋午夜（冬令 UTC-8）
    assert quota_date_pacific(datetime(2026, 11, 14, 16, 0, tzinfo=ZoneInfo("Asia/Taipei"))) == "20261114"


def test_parse_budget() -> None:
    assert parse_budget(None) == 15_000
    assert parse_budget("") == 15_000
    assert parse_budget("8000") == 8000
    for invalid in ("abc", "0", "-5"):
        with pytest.raises(ValueError):
            parse_budget(invalid)


# ========== 額度預扣 ==========

def test_compute_grant_new_document_and_new_day() -> None:
    assert compute_grant(None, "20261113", 1000, 500) == (500, 500)
    # 舊配額日的用量不計入，視為重置
    assert compute_grant({"quota_date": "20261112", "deleted": 1000}, "20261113", 1000, 300) == (300, 300)


def test_compute_grant_same_day_partial_and_exhausted() -> None:
    stored = {"quota_date": "20261113", "deleted": 800}
    assert compute_grant(stored, "20261113", 1000, 500) == (200, 1000)
    assert compute_grant({"quota_date": "20261113", "deleted": 1000}, "20261113", 1000, 500) == (0, 1000)


def test_compute_grant_corrupted_count_denies() -> None:
    assert compute_grant({"quota_date": "20261113", "deleted": "bad"}, "20261113", 1000, 10)[0] == 0
    assert compute_grant({"quota_date": "20261113", "deleted": -5}, "20261113", 1000, 10)[0] == 0


# ========== run_cleanup ==========

def test_deletes_only_expired_across_all_collections() -> None:
    db = FakeDb(
        market={"MXF": {"20260101": 2, "20260101_tick": 2, "20260814": 3, "20261110": 3, "junk": 1}},
        top_level={
            "daily_reports": ["20260101", "20260813", "20260814", "bad"],
            "pttPosts": ["20260101_intraday", "20260812_afterhours", "20261001_intraday"],
        },
    )
    result = _run(db, InMemoryLedger(15_000))

    assert result.error is None
    assert not result.budget_exhausted
    assert result.deleted == 2 + 2 + 2 + 2  # 分鐘 + tick + daily_reports(0101/0813) + pttPosts(0101/0812)
    assert result.skipped_ids == 2  # junk、bad
    assert all("20260814" not in path and "20261110" not in path for path in db.deleted_paths)
    assert "market/MXF/20260101/000000" in db.deleted_paths
    assert "market/MXF/20260101_tick/000001" in db.deleted_paths
    assert "daily_reports/20260813" in db.deleted_paths
    assert "pttPosts/20260812_afterhours" in db.deleted_paths


def test_supports_multiple_symbols() -> None:
    db = FakeDb(market={"MXF": {"20260101": 2}, "TXF": {"20260102": 3}})
    result = _run(db, InMemoryLedger(15_000))
    assert result.deleted == 5


def test_deletes_oldest_first() -> None:
    db = FakeDb(market={"MXF": {"20260301": 1, "20260101": 1, "20260201": 1}})
    _run(db, InMemoryLedger(15_000))
    assert db.deleted_paths == [
        "market/MXF/20260101/000000",
        "market/MXF/20260201/000000",
        "market/MXF/20260301/000000",
    ]


def test_batches_never_exceed_limit() -> None:
    db = FakeDb(market={"MXF": {"20260101": 1200}})
    result = _run(db, InMemoryLedger(15_000))
    assert result.deleted == 1200
    assert db.batch_sizes == [BATCH_SIZE, BATCH_SIZE, 200]


def test_budget_truncates_exactly() -> None:
    db = FakeDb(market={"MXF": {"20260101": 1200}})
    ledger = InMemoryLedger(700)
    result = _run(db, ledger)

    assert result.deleted == 700
    assert len(db.deleted_paths) == 700
    assert db.batch_sizes == [500, 200]
    assert result.budget_exhausted is True
    assert ledger.used == 700


def test_budget_boundary_exactly_equal_is_not_exhausted() -> None:
    db = FakeDb(market={"MXF": {"20260101": 500}})
    result = _run(db, InMemoryLedger(500))
    assert result.deleted == 500
    assert result.budget_exhausted is False


def test_repeated_runs_same_quota_day_never_exceed_budget() -> None:
    db = FakeDb(market={"MXF": {"20260101": 2500}})
    ledger = InMemoryLedger(1000)

    results = [_run(db, ledger) for _ in range(3)]

    assert len(db.deleted_paths) == 1000
    assert ledger.used == 1000
    assert [r.deleted for r in results] == [1000, 0, 0]


def test_skips_scan_when_budget_already_used() -> None:
    db = FakeDb(market={"MXF": {"20260101": 10}})
    result = _run(db, InMemoryLedger(100, used=100))

    assert result.deleted == 0
    assert result.budget_exhausted is True
    assert db.listed_collections == []  # 沒有掃描任何集合
    assert db.deleted_paths == []


def test_remaining_budget_from_earlier_usage_is_respected() -> None:
    db = FakeDb(market={"MXF": {"20260101": 300}})
    result = _run(db, InMemoryLedger(1000, used=900))
    assert result.deleted == 100
    assert result.budget_exhausted is True


def test_commit_failure_stops_and_keeps_reservation() -> None:
    db = FakeDb(market={"MXF": {"20260101": 1200}})
    db.fail_commit = True
    ledger = InMemoryLedger(15_000)

    result = _run(db, ledger)

    assert result.deleted == 0
    assert result.error is not None and "批次刪除失敗" in result.error
    assert db.deleted_paths == []
    assert ledger.used == BATCH_SIZE  # 失敗的批次額度不退還，且不再繼續下一批


def test_dry_run_does_not_delete_or_consume_budget() -> None:
    db = FakeDb(market={"MXF": {"20260101": 1200}})
    ledger = InMemoryLedger(700)

    result = _run(db, ledger, dry_run=True)

    assert result.dry_run is True
    assert result.deleted == 700  # 與實刪相同的截斷結果
    assert db.deleted_paths == []
    assert ledger.used == 0


def test_nothing_expired() -> None:
    db = FakeDb(market={"MXF": {"20261101": 5}}, top_level={"daily_reports": ["20261101"]})
    result = _run(db, InMemoryLedger(15_000))
    assert result.deleted == 0
    assert result.budget_exhausted is False


# ========== HTTP 入口 ==========

class FakeRequest:
    def __init__(self, args: Optional[dict[str, str]] = None) -> None:
        self.args = args or {}


class FakeWriter:
    def __init__(self, project_id: str) -> None:
        self.db = FakeDb(market={"MXF": {"20200101": 3}})
        self.closed = False
        FakeWriter.last = self

    def close(self) -> None:
        self.closed = True

    last: "FakeWriter"


def _patch_entry(monkeypatch: pytest.MonkeyPatch, budget: int = 15_000) -> None:
    monkeypatch.setattr(data_cleanup, "FirestoreWriter", FakeWriter)
    monkeypatch.setattr(data_cleanup, "FirestoreQuotaLedger", lambda db, b: InMemoryLedger(b))
    monkeypatch.setattr(data_cleanup, "now_taipei", lambda: datetime(2026, 11, 14, 6, 0))
    monkeypatch.setenv("CLEANUP_DELETE_BUDGET", str(budget))


def test_entry_point_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_entry(monkeypatch)
    body, status = data_cleanup.data_cleanup(FakeRequest())  # type: ignore[arg-type]

    assert status == 200
    assert body["deleted"] == 3
    assert body["cutoff"] == "2026-08-14"
    assert FakeWriter.last.closed is True


def test_entry_point_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_entry(monkeypatch)
    body, status = data_cleanup.data_cleanup(FakeRequest({"dry_run": "true"}))  # type: ignore[arg-type]

    assert status == 200
    assert body["dry_run"] is True
    assert FakeWriter.last.db.deleted_paths == []


def test_entry_point_invalid_budget_returns_500(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_entry(monkeypatch)
    monkeypatch.setenv("CLEANUP_DELETE_BUDGET", "abc")
    body, status = data_cleanup.data_cleanup(FakeRequest())  # type: ignore[arg-type]

    assert status == 500
    assert "error" in body


def test_entry_point_returns_500_on_batch_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_entry(monkeypatch)

    class FailingWriter(FakeWriter):
        def __init__(self, project_id: str) -> None:
            super().__init__(project_id)
            self.db.fail_commit = True

    monkeypatch.setattr(data_cleanup, "FirestoreWriter", FailingWriter)
    body, status = data_cleanup.data_cleanup(FakeRequest())  # type: ignore[arg-type]

    assert status == 500
    assert body["error"]


# ========== FirestoreQuotaLedger（真實 firestore.transactional 包裝 + 假 transaction） ==========

_NOON_PACIFIC = datetime(2026, 11, 13, 12, 0, tzinfo=ZoneInfo("America/Los_Angeles"))


def _fake_db(stored: Optional[dict[str, object]]) -> tuple[MagicMock, MagicMock]:
    """回傳 (db, transaction)；db 的計數文件快照內容為 stored"""
    snapshot = MagicMock()
    snapshot.exists = stored is not None
    snapshot.to_dict.return_value = stored
    doc_ref = MagicMock()
    doc_ref.get.return_value = snapshot
    transaction = MagicMock()
    transaction._max_attempts = 5
    transaction._read_only = False
    db = MagicMock()
    db.collection.return_value.document.return_value = doc_ref
    db.transaction.return_value = transaction
    return db, transaction


def test_ledger_uses_single_document_and_reserves_in_transaction() -> None:
    db, transaction = _fake_db({"quota_date": "20261113", "deleted": 400})
    ledger = FirestoreQuotaLedger(db, 1000, clock=lambda: _NOON_PACIFIC)

    assert ledger.reserve(500) == 500

    db.collection.assert_called_with("_maintenance")
    db.collection.return_value.document.assert_called_with("data_cleanup")
    written = transaction.set.call_args.args[1]
    assert written["quota_date"] == "20261113"
    assert written["deleted"] == 900


def test_ledger_caps_at_remaining_and_skips_write_when_exhausted() -> None:
    db, transaction = _fake_db({"quota_date": "20261113", "deleted": 900})
    ledger = FirestoreQuotaLedger(db, 1000, clock=lambda: _NOON_PACIFIC)
    assert ledger.reserve(500) == 100
    assert transaction.set.call_args.args[1]["deleted"] == 1000

    db, transaction = _fake_db({"quota_date": "20261113", "deleted": 1000})
    ledger = FirestoreQuotaLedger(db, 1000, clock=lambda: _NOON_PACIFIC)
    assert ledger.reserve(500) == 0
    transaction.set.assert_not_called()


def test_ledger_resets_on_new_quota_day_and_reports_remaining() -> None:
    db, transaction = _fake_db({"quota_date": "20261112", "deleted": 1000})
    ledger = FirestoreQuotaLedger(db, 1000, clock=lambda: _NOON_PACIFIC)

    assert ledger.remaining() == 1000
    assert ledger.reserve(300) == 300
    assert transaction.set.call_args.args[1] == {
        "quota_date": "20261113",
        "deleted": 300,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }


def test_ledger_missing_document_starts_from_zero() -> None:
    db, _ = _fake_db(None)
    ledger = FirestoreQuotaLedger(db, 1000, clock=lambda: _NOON_PACIFIC)
    assert ledger.remaining() == 1000
