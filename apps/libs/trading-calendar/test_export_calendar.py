"""
測試休市日匯出（供前端使用的靜態 JSON）
"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "src"))

from trading_calendar import Overrides, is_trading_day
from trading_calendar import sessions
from trading_calendar.export_calendar import build_calendar_data, main, write_calendar_data


@pytest.fixture(autouse=True)
def no_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """預設不套用例外檔，避免 repo 內例外設定影響測試結果"""
    monkeypatch.setattr(sessions, "_overrides", lambda: Overrides())


def test_closed_days_include_public_holidays_and_exclude_weekends() -> None:
    data = build_calendar_data(2026, 2026)

    assert "2026-10-09" in data["closedDays"]  # 國慶日補假
    assert "2026-02-17" in data["closedDays"]  # 春節
    assert "2026-10-10" not in data["closedDays"]  # 週六，由前端規則判斷
    assert "2026-07-27" not in data["closedDays"]  # 一般交易日


def test_closed_days_match_is_trading_day_for_every_weekday() -> None:
    data = build_calendar_data(2026, 2027)
    closed = set(data["closedDays"])

    current = date(2026, 1, 1)
    while current <= date(2027, 12, 31):
        if current.weekday() < 5:
            assert (current.isoformat() in closed) is (not is_trading_day(current))
        current += timedelta(days=1)


def test_closed_days_are_sorted_and_within_range() -> None:
    data = build_calendar_data(2025, 2026)

    assert data["closedDays"] == sorted(data["closedDays"])
    assert all("2025-01-01" <= d <= "2026-12-31" for d in data["closedDays"])


def test_extra_closed_and_force_open_overrides_are_applied(monkeypatch: pytest.MonkeyPatch) -> None:
    overrides = Overrides(
        extra_closed_days=frozenset({date(2026, 7, 27)}),
        force_open_days=frozenset({date(2026, 10, 9)}),
    )
    monkeypatch.setattr(sessions, "_overrides", lambda: overrides)

    data = build_calendar_data(2026, 2026)

    assert "2026-07-27" in data["closedDays"]
    assert "2026-10-09" not in data["closedDays"]


def test_start_year_after_end_year_raises() -> None:
    with pytest.raises(ValueError):
        build_calendar_data(2027, 2026)


def test_write_calendar_data_outputs_json_file(tmp_path: Path) -> None:
    output = tmp_path / "nested" / "calendar.json"

    write_calendar_data(output, 2026, 2026)

    loaded = json.loads(output.read_text(encoding="utf-8"))
    assert loaded["startYear"] == 2026
    assert loaded["endYear"] == 2026
    assert "2026-10-09" in loaded["closedDays"]
    assert output.read_text(encoding="utf-8").endswith("\n")


def test_main_writes_file_with_cli_args(tmp_path: Path) -> None:
    output = tmp_path / "calendar.json"

    exit_code = main(["--output", str(output), "--start-year", "2026", "--end-year", "2026"])

    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["startYear"] == 2026
