"""
測試交易日、交易時段與啟用窗口判斷（含國定假日與例外檔）
"""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))

from trading_calendar import ActiveWindow, Overrides, is_session_open, is_trading_day, load_overrides
from trading_calendar import sessions


def taipei(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """建立 naive 台北時間（與 Shioaji tick 時間一致）"""
    return datetime(year, month, day, hour, minute)


@pytest.fixture(autouse=True)
def no_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """預設不套用例外檔，避免 repo 內例外設定影響測試結果"""
    monkeypatch.setattr(sessions, "_overrides", lambda: Overrides())


# 2026-07-27 為週一、2026-07-31 為週五


@pytest.mark.parametrize(
    "dt",
    [
        taipei(2026, 7, 27, 8, 45),
        taipei(2026, 7, 27, 10, 30),
        taipei(2026, 7, 27, 13, 45),
        taipei(2026, 7, 27, 15, 0),
        taipei(2026, 7, 27, 16, 30),
        taipei(2026, 7, 28, 4, 59),
        taipei(2026, 7, 28, 5, 0),
    ],
)
def test_session_open_during_day_and_night_sessions(dt: datetime) -> None:
    assert is_session_open(dt) is True


@pytest.mark.parametrize(
    "dt",
    [
        taipei(2026, 7, 27, 7, 0),
        taipei(2026, 7, 27, 8, 44),
        taipei(2026, 7, 27, 13, 46),
        taipei(2026, 7, 27, 14, 59),
        taipei(2026, 7, 28, 5, 1),
    ],
)
def test_session_closed_between_sessions(dt: datetime) -> None:
    assert is_session_open(dt) is False


def test_friday_night_session_continues_into_saturday_morning() -> None:
    assert is_session_open(taipei(2026, 7, 31, 23, 0)) is True
    assert is_session_open(taipei(2026, 8, 1, 2, 0)) is True
    assert is_session_open(taipei(2026, 8, 1, 5, 1)) is False


def test_session_closed_on_sunday_and_monday_early_morning() -> None:
    assert is_session_open(taipei(2026, 8, 2, 10, 30)) is False
    assert is_session_open(taipei(2026, 8, 2, 16, 0)) is False
    assert is_session_open(taipei(2026, 8, 3, 2, 0)) is False  # 週日沒有夜盤，週一凌晨不開


def test_aware_datetime_is_converted_to_taipei_time() -> None:
    """UTC 01:00 等於台北 09:00（日盤中）；若誤當成台北 01:00 則會判成休市"""
    utc_dt = datetime(2026, 7, 27, 1, 0, tzinfo=timezone.utc)

    assert is_session_open(utc_dt) is True


def test_public_holiday_closes_day_and_night_session() -> None:
    """2026-10-09（週五）為國慶日補假：當天日盤與夜盤都不開"""
    assert is_trading_day(date(2026, 10, 9)) is False
    assert is_session_open(taipei(2026, 10, 9, 10, 30)) is False
    assert is_session_open(taipei(2026, 10, 9, 16, 0)) is False


def test_night_session_before_holiday_still_runs_through_holiday_morning() -> None:
    """假日前最後交易日的夜盤照常，延續到假日凌晨 05:00；假日夜盤與隔天凌晨則不開"""
    assert is_session_open(taipei(2026, 10, 8, 16, 0)) is True
    assert is_session_open(taipei(2026, 10, 9, 2, 0)) is True
    assert is_session_open(taipei(2026, 10, 10, 2, 0)) is False


def test_first_trading_day_after_holiday_opens_normally() -> None:
    assert is_session_open(taipei(2026, 10, 12, 8, 45)) is True
    assert is_session_open(taipei(2026, 10, 12, 2, 0)) is False


def test_lunar_new_year_week_is_closed() -> None:
    assert is_trading_day(date(2026, 2, 17)) is False
    assert is_session_open(taipei(2026, 2, 17, 10, 30)) is False


def test_extra_closed_day_override_closes_day_but_not_previous_night_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sessions, "_overrides", lambda: Overrides(extra_closed_days=frozenset({date(2026, 7, 28)})))

    assert is_session_open(taipei(2026, 7, 28, 10, 30)) is False
    assert is_session_open(taipei(2026, 7, 28, 16, 0)) is False
    assert is_session_open(taipei(2026, 7, 28, 2, 0)) is True  # 週一夜盤延續


def test_force_open_day_override_reopens_public_holiday(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sessions, "_overrides", lambda: Overrides(force_open_days=frozenset({date(2026, 10, 9)})))

    assert is_trading_day(date(2026, 10, 9)) is True
    assert is_session_open(taipei(2026, 10, 9, 10, 30)) is True


def test_force_open_day_cannot_open_weekend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sessions, "_overrides", lambda: Overrides(force_open_days=frozenset({date(2026, 8, 1)})))

    assert is_trading_day(date(2026, 8, 1)) is False


def test_load_overrides_reads_valid_file(tmp_path: Path) -> None:
    path = tmp_path / "overrides.toml"
    path.write_text('extra_closed_days = ["2026-07-28"]\nforce_open_days = ["2026-10-09"]\n', encoding="utf-8")

    overrides = load_overrides(path)

    assert overrides.extra_closed_days == frozenset({date(2026, 7, 28)})
    assert overrides.force_open_days == frozenset({date(2026, 10, 9)})


def test_load_overrides_ignores_missing_file(tmp_path: Path) -> None:
    assert load_overrides(tmp_path / "missing.toml") == Overrides()


def test_load_overrides_ignores_malformed_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "overrides.toml"
    path.write_text('extra_closed_days = ["not-a-date"]\n', encoding="utf-8")

    assert load_overrides(path) == Overrides()
    assert "讀取休市日例外檔失敗" in capsys.readouterr().out


def test_repo_overrides_file_is_valid() -> None:
    """repo 內附的例外檔本身必須能正常解析（解析失敗時 load_overrides 會靜默退回空例外）"""
    path = sessions.OVERRIDES_PATH

    assert path.exists()
    # 手動解析以避免 load_overrides 吞掉錯誤
    import tomllib

    with path.open("rb") as f:
        raw = tomllib.load(f)
    for key in ("extra_closed_days", "force_open_days"):
        for value in raw[key]:
            date.fromisoformat(value)


WARMUP_5_GRACE_3 = ActiveWindow(warmup=timedelta(minutes=5), grace=timedelta(minutes=3))


@pytest.mark.parametrize(
    ("dt", "expected"),
    [
        (taipei(2026, 7, 27, 8, 39), False),
        (taipei(2026, 7, 27, 8, 40), True),  # 日盤開盤前 5 分鐘
        (taipei(2026, 7, 27, 13, 45), True),
        (taipei(2026, 7, 27, 13, 48), True),  # 收盤後緩衝 3 分鐘
        (taipei(2026, 7, 27, 13, 49), False),
        (taipei(2026, 7, 27, 14, 54), False),
        (taipei(2026, 7, 27, 14, 55), True),  # 夜盤開盤前 5 分鐘
        (taipei(2026, 7, 28, 5, 3), True),
        (taipei(2026, 7, 28, 5, 4), False),
    ],
)
def test_active_window_extends_session_by_warmup_and_grace(dt: datetime, expected: bool) -> None:
    assert WARMUP_5_GRACE_3.contains(dt) is expected


def test_active_window_without_warmup_or_grace_matches_session() -> None:
    window = ActiveWindow()

    assert window.contains(taipei(2026, 7, 27, 8, 44)) is False
    assert window.contains(taipei(2026, 7, 27, 8, 45)) is True
    assert window.contains(taipei(2026, 7, 27, 13, 46)) is False


def test_active_window_stays_inactive_on_holidays_and_weekends() -> None:
    assert WARMUP_5_GRACE_3.contains(taipei(2026, 10, 9, 8, 40)) is False  # 國慶補假
    assert WARMUP_5_GRACE_3.contains(taipei(2026, 8, 1, 8, 40)) is False  # 週六
    assert WARMUP_5_GRACE_3.contains(taipei(2026, 8, 2, 14, 55)) is False  # 週日不會有夜盤預熱
    assert WARMUP_5_GRACE_3.contains(taipei(2026, 8, 2, 23, 58)) is False  # 預熱不會跨午夜誤開週一凌晨


def test_active_window_covers_friday_night_tail_with_grace() -> None:
    assert WARMUP_5_GRACE_3.contains(taipei(2026, 8, 1, 5, 3)) is True
    assert WARMUP_5_GRACE_3.contains(taipei(2026, 8, 1, 5, 4)) is False
