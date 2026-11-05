# 交易日曆與服務生命週期模組

台指期交易日、交易時段判斷（含國定假日），以及「每分鐘判斷是否啟用」的 session 迴圈。
`price-listener` / `price-analyzer` / `price-broadcaster` 共用，取代各服務自己複製的判斷邏輯。

## 交易時段規則

- 交易日 = 週一到週五且非休市日
- 日盤：交易日 08:45-13:45
- 夜盤：交易日 15:00 至次日 05:00；凌晨 00:00-05:00 是否開盤取決於「前一天」是否為交易日
  （週五夜盤延續到週六凌晨，週日沒有夜盤所以週一凌晨不開，假日前一個交易日的夜盤照常）
- 結束時間含該分鐘整分鐘（13:45 代表到 13:45:59）

## 休市日來源

1. [`holidays`](https://pypi.org/project/holidays/) 套件的台灣日曆（國定假日、補假、春節等）
2. [`overrides.toml`](src/trading_calendar/overrides.toml) 例外檔：補足與期交所實際休市日的差異、颱風等臨時休市日

> 每年年初請對照期交所公告確認一次，必要時升級 `holidays` 套件（`uv lock --upgrade-package holidays`）
> 或在例外檔補日期。例外檔讀取失敗時會忽略例外並印出錯誤：把休市日當成交易日只是空轉，
> 反過來把交易日當成休市日會漏資料。

## 前端休市日資料

前端（`web/app/lib/tradingCalendar.ts`）沒有 `holidays` 套件，改讀這裡匯出的靜態 JSON，
判斷順序與 `is_trading_day` 相同（含例外檔）。每年年初、升級 `holidays` 或調整 `overrides.toml` 後重新匯出：

```bash
cd apps/libs/trading-calendar
uv run python -m trading_calendar.export_calendar --output ../../../web/app/lib/tradingCalendar.data.json
```

- 預設匯出「去年到明年」三年，可用 `--start-year` / `--end-year` 指定
- `web` 的部署流程（`deploy-web.yml`）建置前會自動重新匯出，本機也可在 `web/` 執行 `npm run export:calendar`
- 提交進 repo 的 JSON 是本機開發與測試使用的快照，部署以流程中重新匯出的結果為準

## 使用方式

```python
from datetime import timedelta
from threading import Event

from trading_calendar import ActiveWindow, ShouldContinue, run_session_loop

# 開盤前 5 分鐘就緒、收盤後 1 分鐘才收尾
WINDOW = ActiveWindow(warmup=timedelta(minutes=5), grace=timedelta(minutes=1))


def run_session(should_continue: ShouldContinue) -> None:
    ...  # 建立連線、開始工作；should_continue() 為 False 時完成收尾並返回


stop_event = Event()
run_session_loop("my-service", run_session, WINDOW.contains, stop_event)
```

- 待機時每分鐘檢查一次，進入啟用窗口就呼叫 `run_session`，窗口結束後 `run_session` 收尾返回，再回到待機
- `run_session` 拋出例外代表本次失敗，窗口內的下一輪會重新開始
- 設定 `stop_event`（例如收到 SIGTERM）會結束整個迴圈
- 判斷窗口本身出錯時保守視為啟用，避免漏掉整個時段
