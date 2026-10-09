"""
台指期交易日與交易時段判斷

交易時段：
- 日盤：交易日 08:45-13:45
- 夜盤：交易日 15:00 至次日 05:00（夜盤延續段是否開盤，取決於「前一天」是否為交易日）
"""
import threading
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays

TAIPEI_TZ = ZoneInfo("Asia/Taipei")

# 以「當天第幾分鐘」表示邊界，結束時間含該分鐘整分鐘（13:45 代表到 13:45:59）
DAY_SESSION_START = 8 * 60 + 45
DAY_SESSION_END = 13 * 60 + 45
NIGHT_SESSION_START = 15 * 60
NIGHT_SESSION_END = 5 * 60

OVERRIDES_PATH = Path(__file__).with_name("overrides.toml")

_public_holidays = holidays.country_holidays("TW")
_holidays_lock = threading.Lock()


@dataclass(frozen=True)
class Overrides:
    """休市日例外：補足 holidays 套件與期交所實際休市日的差異"""
    extra_closed_days: frozenset[date] = frozenset()
    force_open_days: frozenset[date] = frozenset()


def load_overrides(path: Path = OVERRIDES_PATH) -> Overrides:
    """
    讀取休市日例外檔。

    檔案缺失或格式錯誤時視為沒有例外：把休市日當成交易日只是空轉，
    反過來把交易日當成休市日則會漏資料，所以出錯時寧可多跑。
    """
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
        return Overrides(
            extra_closed_days=frozenset(date.fromisoformat(s) for s in raw.get("extra_closed_days", [])),
            force_open_days=frozenset(date.fromisoformat(s) for s in raw.get("force_open_days", [])),
        )
    except (OSError, tomllib.TOMLDecodeError, ValueError, TypeError) as e:
        print(f"❌ 讀取休市日例外檔失敗，將忽略例外設定: {path} ({type(e).__name__}: {e})")
        return Overrides()


@lru_cache(maxsize=1)
def _overrides() -> Overrides:
    return load_overrides()


def _is_public_holiday(d: date) -> bool:
    # holidays 物件查詢新年份時會就地展開資料，非 thread-safe
    with _holidays_lock:
        return d in _public_holidays


def _to_taipei(dt: datetime | None) -> datetime:
    """轉成不帶 tzinfo 的台北時間；naive 輸入視為已是台北時間（與 Shioaji tick 時間一致）"""
    if dt is None:
        return datetime.now(TAIPEI_TZ).replace(tzinfo=None)
    if dt.tzinfo is not None:
        return dt.astimezone(TAIPEI_TZ).replace(tzinfo=None)
    return dt


def is_trading_day(d: date) -> bool:
    """是否為交易日：週一到週五且非休市日"""
    if d.weekday() >= 5:
        return False

    overrides = _overrides()
    if d in overrides.force_open_days:
        return True
    if d in overrides.extra_closed_days:
        return False

    return not _is_public_holiday(d)


def is_session_open(dt: datetime | None = None) -> bool:
    """指定時間是否在日盤或夜盤交易時段內（預設為現在的台北時間）"""
    now = _to_taipei(dt)
    minutes = now.hour * 60 + now.minute

    # 00:00-05:00 屬於前一天夜盤的延續（週五夜盤會延續到週六凌晨）
    if minutes <= NIGHT_SESSION_END and is_trading_day(now.date() - timedelta(days=1)):
        return True

    if not is_trading_day(now.date()):
        return False

    if DAY_SESSION_START <= minutes <= DAY_SESSION_END:
        return True

    return minutes >= NIGHT_SESSION_START


@dataclass(frozen=True)
class ActiveWindow:
    """服務啟用窗口：交易時段開始前 warmup 就緒，收盤後 grace 才收尾"""
    warmup: timedelta = timedelta(0)
    grace: timedelta = timedelta(0)

    def contains(self, dt: datetime | None = None) -> bool:
        now = _to_taipei(dt)
        return is_session_open(now + self.warmup) or is_session_open(now - self.grace)
