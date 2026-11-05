"""
匯出休市日清單給前端使用

前端沒有 `holidays` 套件，改由這裡以 `is_trading_day` 為準（含國定假日、補假與例外檔）
產出靜態 JSON，確保前後端的交易日判斷一致。

用法（每年年初或調整 overrides.toml 後重新執行）：
    uv run python -m trading_calendar.export_calendar --output ../../../web/app/lib/tradingCalendar.data.json
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TypedDict

from .sessions import TAIPEI_TZ, is_trading_day


class CalendarData(TypedDict):
    startYear: int
    endYear: int
    closedDays: list[str]


def build_calendar_data(start_year: int, end_year: int) -> CalendarData:
    """
    建立指定年度範圍內的休市日資料。

    只收錄「週一到週五但休市」的日期，週末由前端規則直接判斷。
    """
    if start_year > end_year:
        raise ValueError(f"start_year ({start_year}) 不可大於 end_year ({end_year})")

    closed_days: list[str] = []
    current = date(start_year, 1, 1)
    last = date(end_year, 12, 31)
    while current <= last:
        if current.weekday() < 5 and not is_trading_day(current):
            closed_days.append(current.isoformat())
        current += timedelta(days=1)

    return {"startYear": start_year, "endYear": end_year, "closedDays": closed_days}


def write_calendar_data(output: Path, start_year: int, end_year: int) -> CalendarData:
    """產出 JSON 檔（固定排序、結尾換行，避免無意義的 diff）"""
    data = build_calendar_data(start_year, end_year)
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        print(f"❌ 寫入休市日資料失敗: {output} ({type(e).__name__}: {e})", file=sys.stderr)
        raise
    return data


def main(argv: list[str] | None = None) -> int:
    this_year = datetime.now(TAIPEI_TZ).year
    parser = argparse.ArgumentParser(description="匯出休市日清單給前端使用")
    parser.add_argument("--output", type=Path, required=True, help="輸出的 JSON 路徑")
    parser.add_argument("--start-year", type=int, default=this_year - 1, help="起始年度（預設去年）")
    parser.add_argument("--end-year", type=int, default=this_year + 1, help="結束年度（預設明年）")
    args = parser.parse_args(argv)

    data = write_calendar_data(args.output, args.start_year, args.end_year)
    print(f"✅ 已匯出 {data['startYear']}-{data['endYear']} 共 {len(data['closedDays'])} 個平日休市日: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
