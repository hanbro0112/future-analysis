"""
Firestore 舊資料清理
每天由 Cloud Scheduler 觸發一次，刪除「台北今天 − 3 個月」之前的資料。

清理範圍：
- market/{code}/{YYYYMMDD}        分鐘 K
- market/{code}/{YYYYMMDD}_tick   秒級明細
- daily_reports/{YYYYMMDD}        每日分析報告
- pttPosts/{YYYYMMDD}_{session}   PTT 閒聊推文

Firestore 免費層每日 20,000 次刪除（太平洋時間午夜重置）。為確保不超額，
每批刪除前會先在單一計數文件 `_maintenance/data_cleanup` 以 transaction 預扣額度，
額度用完即停止，未處理的舊資料隔天自動接續。
"""
import calendar
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Callable, Iterable, Optional, Protocol
from zoneinfo import ZoneInfo

from flask import Request
from google.cloud import firestore
from google.cloud.firestore import Client, DocumentReference

from firestore_writer import FirestoreWriter
from timezone_utils import now_taipei

RETENTION_MONTHS = 3
BATCH_SIZE = 500  # Firestore 單一 batch 上限
DEFAULT_DELETE_BUDGET = 15_000
BUDGET_ENV_NAME = "CLEANUP_DELETE_BUDGET"

LEDGER_COLLECTION = "_maintenance"
LEDGER_DOC_ID = "data_cleanup"
QUOTA_TZ = ZoneInfo("America/Los_Angeles")  # Firestore 免費額度以太平洋時間午夜重置

MARKET_COLLECTION = "market"
MARKET_SUBCOLLECTION_RE = re.compile(r"^(\d{8})(?:_tick)?$")
DAILY_REPORTS_COLLECTION = "daily_reports"
DAILY_REPORT_ID_RE = re.compile(r"^(\d{8})$")
PTT_POSTS_COLLECTION = "pttPosts"
PTT_POST_ID_RE = re.compile(r"^(\d{8})_[A-Za-z]+$")


# ========== 日期工具 ==========

def subtract_months(day: date, months: int) -> date:
    """日期減去指定月數；目標月份沒有該日時取該月最後一天（例如 5/31 − 3 個月 = 2/28）"""
    index = day.year * 12 + (day.month - 1) - months
    year, month_zero_based = divmod(index, 12)
    month = month_zero_based + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def compute_cutoff(now: datetime) -> date:
    """保留區間的起點：台北今天 − 3 個月，早於此日期的資料會被刪除"""
    return subtract_months(now.date(), RETENTION_MONTHS)


def extract_date(identifier: str, pattern: re.Pattern[str]) -> Optional[date]:
    """從集合 / 文件 ID 解析出日期；格式不符或不是合法日期時回傳 None"""
    matched = pattern.match(identifier)
    if matched is None:
        return None
    try:
        return datetime.strptime(matched.group(1), "%Y%m%d").date()
    except ValueError:
        return None


def quota_date_pacific(now: Optional[datetime] = None) -> str:
    """目前所屬的 Firestore 配額日（太平洋時間 YYYYMMDD）"""
    current = now.astimezone(QUOTA_TZ) if now else datetime.now(QUOTA_TZ)
    return current.strftime("%Y%m%d")


def parse_budget(raw: Optional[str]) -> int:
    """解析每日刪除預算；未設定用預設值，非正整數則拋出 ValueError"""
    if raw is None or raw.strip() == "":
        return DEFAULT_DELETE_BUDGET
    try:
        budget = int(raw)
    except ValueError as e:
        raise ValueError(f"{BUDGET_ENV_NAME} 必須是整數: {raw!r}") from e
    if budget <= 0:
        raise ValueError(f"{BUDGET_ENV_NAME} 必須大於 0: {budget}")
    return budget


# ========== 刪除額度計數 ==========

def compute_grant(
    stored: Optional[dict[str, object]],
    quota_date: str,
    budget: int,
    requested: int,
) -> tuple[int, int]:
    """
    依計數文件內容計算可預扣的額度（純函式）

    Args:
        stored: 計數文件現有內容，文件不存在為 None
        quota_date: 目前配額日（太平洋時間 YYYYMMDD）
        budget: 每日刪除預算
        requested: 本次想刪除的筆數

    Returns:
        (granted, new_used)：核准筆數、預扣後該配額日累計用量
    """
    used = 0
    if stored is not None and stored.get("quota_date") == quota_date:
        raw_used = stored.get("deleted", 0)
        # 計數內容異常時保守視為額度已用完，避免超額
        used = raw_used if isinstance(raw_used, int) and raw_used >= 0 else budget
    granted = max(0, min(requested, budget - used))
    return granted, used + granted


class QuotaLedger(Protocol):
    """刪除額度計數介面"""

    def reserve(self, requested: int) -> int:
        """預扣額度，回傳實際核准的筆數（可能小於 requested，甚至為 0）"""
        ...

    def remaining(self) -> int:
        """目前配額日剩餘可刪除筆數"""
        ...


@firestore.transactional
def _reserve_in_transaction(
    transaction: firestore.Transaction,
    doc_ref: DocumentReference,
    quota_date: str,
    budget: int,
    requested: int,
) -> int:
    snapshot = doc_ref.get(transaction=transaction)
    stored = snapshot.to_dict() if snapshot.exists else None
    granted, new_used = compute_grant(stored, quota_date, budget, requested)
    if granted > 0:
        transaction.set(
            doc_ref,
            {
                "quota_date": quota_date,
                "deleted": new_used,
                "updated_at": firestore.SERVER_TIMESTAMP,
            },
        )
    return granted


class FirestoreQuotaLedger:
    """以單一 Firestore 文件 `_maintenance/data_cleanup` 記錄當日已預扣的刪除筆數"""

    def __init__(
        self,
        db: Client,
        budget: int,
        clock: Callable[[], datetime] = lambda: datetime.now(QUOTA_TZ),
    ) -> None:
        self._db = db
        self._budget = budget
        self._clock = clock
        self._doc_ref = db.collection(LEDGER_COLLECTION).document(LEDGER_DOC_ID)

    def reserve(self, requested: int) -> int:
        return _reserve_in_transaction(
            self._db.transaction(),
            self._doc_ref,
            quota_date_pacific(self._clock()),
            self._budget,
            requested,
        )

    def remaining(self) -> int:
        snapshot = self._doc_ref.get()
        stored = snapshot.to_dict() if snapshot.exists else None
        granted, _ = compute_grant(
            stored, quota_date_pacific(self._clock()), self._budget, self._budget
        )
        return granted


class _SimulatedLedger:
    """dry-run 用：從目前剩餘額度開始在記憶體內扣除，不寫入 Firestore"""

    def __init__(self, remaining: int) -> None:
        self._remaining = remaining

    def reserve(self, requested: int) -> int:
        granted = max(0, min(requested, self._remaining))
        self._remaining -= granted
        return granted

    def remaining(self) -> int:
        return self._remaining


# ========== 掃描與刪除 ==========

@dataclass
class DeleteSource:
    """一個待刪除的來源：同一天的整個子集合，或單一文件"""

    day: date
    list_refs: Callable[[], Iterable[DocumentReference]]


@dataclass
class CleanupResult:
    cutoff: str
    budget: int
    dry_run: bool
    deleted: int = 0
    skipped_ids: int = 0
    budget_exhausted: bool = False
    error: Optional[str] = None
    sources_found: int = 0


def _document_sources(
    db: Client, collection: str, pattern: re.Pattern[str], cutoff: date
) -> tuple[list[DeleteSource], int]:
    """掃描頂層集合，文件 ID 內含日期且早於 cutoff 者視為待刪"""
    sources: list[DeleteSource] = []
    skipped = 0
    for doc_ref in db.collection(collection).list_documents():
        day = extract_date(doc_ref.id, pattern)
        if day is None:
            skipped += 1
            print(f"⚠️  略過無法解析日期的文件: {collection}/{doc_ref.id}")
            continue
        if day < cutoff:
            sources.append(DeleteSource(day, lambda ref=doc_ref: [ref]))
    return sources, skipped


def _market_sources(db: Client, cutoff: date) -> tuple[list[DeleteSource], int]:
    """掃描所有商品（market/{code}）底下的日期子集合，不寫死商品代碼"""
    sources: list[DeleteSource] = []
    skipped = 0
    for symbol_ref in db.collection(MARKET_COLLECTION).list_documents():
        for sub_collection in symbol_ref.collections():
            day = extract_date(sub_collection.id, MARKET_SUBCOLLECTION_RE)
            if day is None:
                skipped += 1
                print(f"⚠️  略過無法解析日期的集合: {sub_collection.id}")
                continue
            if day < cutoff:
                sources.append(DeleteSource(day, sub_collection.list_documents))
    return sources, skipped


def collect_sources(db: Client, cutoff: date) -> tuple[list[DeleteSource], int]:
    """彙整所有待刪來源，依日期由舊到新排序；回傳 (來源列表, 略過的 ID 數)"""
    sources: list[DeleteSource] = []
    skipped = 0
    for found, found_skipped in (
        _market_sources(db, cutoff),
        _document_sources(db, DAILY_REPORTS_COLLECTION, DAILY_REPORT_ID_RE, cutoff),
        _document_sources(db, PTT_POSTS_COLLECTION, PTT_POST_ID_RE, cutoff),
    ):
        sources.extend(found)
        skipped += found_skipped
    sources.sort(key=lambda source: source.day)
    return sources, skipped


def _commit_delete(db: Client, refs: list[DocumentReference]) -> None:
    batch = db.batch()
    for ref in refs:
        batch.delete(ref)
    batch.commit()


def _process_batch(
    db: Client,
    ledger: QuotaLedger,
    refs: list[DocumentReference],
    dry_run: bool,
    result: CleanupResult,
) -> bool:
    """
    預扣額度後刪除一批文件

    先預扣再刪除：commit 結果不明（例如逾時）時額度也不退還，寧可少刪也不超額。

    Returns:
        True 表示可繼續處理下一批；False 表示額度用完或發生錯誤，應停止
    """
    granted = ledger.reserve(len(refs))
    if granted <= 0:
        result.budget_exhausted = True
        return False

    to_delete = refs[:granted]
    if not dry_run:
        try:
            _commit_delete(db, to_delete)
        except Exception as e:
            result.error = f"批次刪除失敗（已預扣 {granted} 筆額度）: {type(e).__name__}: {e}"
            print(f"❌ {result.error}")
            return False
    result.deleted += granted

    if granted < len(refs):
        result.budget_exhausted = True
        return False
    return True


def run_cleanup(
    db: Client,
    ledger: QuotaLedger,
    cutoff: date,
    budget: int,
    dry_run: bool = False,
) -> CleanupResult:
    """
    刪除早於 cutoff 的資料，累計刪除筆數不會超過 ledger 的剩餘額度

    Args:
        db: Firestore client
        ledger: 刪除額度計數
        cutoff: 早於此日期（不含）的資料會被刪除
        budget: 每日刪除預算（僅用於回報）
        dry_run: True 時只統計不刪除、不寫入計數
    """
    result = CleanupResult(cutoff=cutoff.isoformat(), budget=budget, dry_run=dry_run)

    remaining = ledger.remaining()
    if remaining <= 0:
        result.budget_exhausted = True
        print("⏸️  今日刪除額度已用完，本次跳過")
        return result

    active_ledger: QuotaLedger = _SimulatedLedger(remaining) if dry_run else ledger

    sources, result.skipped_ids = collect_sources(db, cutoff)
    result.sources_found = len(sources)

    buffer: list[DocumentReference] = []
    for source in sources:
        for ref in source.list_refs():
            buffer.append(ref)
            if len(buffer) >= BATCH_SIZE:
                if not _process_batch(db, active_ledger, buffer, dry_run, result):
                    return result
                buffer = []

    if buffer:
        _process_batch(db, active_ledger, buffer, dry_run, result)
    return result


# ========== Cloud Functions 入口 ==========

def _is_truthy(value: Optional[str]) -> bool:
    return value is not None and value.strip().lower() in ("1", "true", "yes")


def data_cleanup(request: Request) -> tuple[dict[str, object], int]:
    """Cloud Functions HTTP entry point：由 Cloud Scheduler 每天觸發一次；?dry_run=true 只統計不刪除"""
    dry_run = _is_truthy(request.args.get("dry_run"))

    try:
        budget = parse_budget(os.getenv(BUDGET_ENV_NAME))
        cutoff = compute_cutoff(now_taipei())

        firestore_writer = FirestoreWriter(project_id=os.getenv("GCP_PROJECT_ID", "demo-project"))
        try:
            ledger = FirestoreQuotaLedger(firestore_writer.db, budget)
            result = run_cleanup(firestore_writer.db, ledger, cutoff, budget, dry_run)
        finally:
            firestore_writer.close()

        status = 500 if result.error else 200
        print(
            f"🧹 清理完成: 刪除 {result.deleted} 筆（預算 {budget}，cutoff {result.cutoff}，"
            f"額度用完={result.budget_exhausted}，dry_run={dry_run}）"
        )
        return asdict(result), status

    except Exception as e:
        print(f"❌ 資料清理發生錯誤: {type(e).__name__}: {e}")
        return {"error": f"資料清理失敗: {e}"}, 500
