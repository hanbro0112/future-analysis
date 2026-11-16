# Functions - 定時任務 Cloud Functions

由 Cloud Scheduler + Cloud Functions (2nd gen) 以 HTTP 觸發執行，不屬於 GCE 上的常駐服務。

## 功能

| Function 名稱 | 檔案 | 說明 | 排程 |
| --- | --- | --- | --- |
| `daily_report` | `daily_report.py` | 使用 Gemini API 分析台股/美股，寫入 Firestore `daily_reports/{YYYYMMDD}` | 每天 08:00（僅交易日執行，週末由程式內部判斷跳過） |
| `chip_report` | `chip_report.py` | 抓取台指籌碼快訊 PDF，提取圖表上傳 Cloud Storage `chip-reports/{YYYYMMDD}/` | 每交易日 15:21 |
| `crawl_ptt_chat` | `ptt_chat.py` | 抓取 PTT Stock 板盤中/盤後閒聊推文，寫入 Firestore `pttThreads`/`pttPosts` | 每分鐘（Cloud Scheduler 尚需手動建立，見下方部署說明） |
| `data_cleanup` | `data_cleanup.py` | 刪除「台北今天 − 3 個月」之前的 Firestore 舊資料，並確保每日刪除次數不超過預算（詳見下方「資料清理」） | 每天 06:00（含週末） |

四個 function 都是 HTTP-triggered，`main.py` 匯入供 `gcloud functions deploy --entry-point` 使用。

## 元件說明

| 檔案 | 功用 |
| --- | --- |
| `main.py` | Cloud Functions 進入點，匯出 `daily_report` / `chip_report` / `crawl_ptt_chat` 供部署指定 entry-point |
| `daily_report.py` | 呼叫 Gemini API 分析台股/美股市場，寫入 Firestore `daily_reports/{YYYYMMDD}`，內含 `is_trading_day` 交易日判斷 |
| `chip_report.py` | 抓取台指籌碼快訊 PDF、裁切散戶多空比圖表，上傳 Cloud Storage `chip-reports/{YYYYMMDD}/` |
| `README_CHIP_REPORT.md` | 籌碼快訊 PDF 裁切座標調整說明 |
| `ptt_chat.py` | 抓取 PTT Stock 板盤中/盤後閒聊推文，寫入 Firestore `pttThreads`/`pttPosts` |
| `README_PTT_CHAT.md` | PTT 閒聊功能說明、Firestore schema、部署方式 |
| `data_cleanup.py` | 刪除超過 3 個月的 Firestore 舊資料，以單一計數文件控管每日刪除預算 |

## 環境變數

```bash
GCP_PROJECT_ID=demo-project
GEMINI_API_KEY=your-gemini-api-key   # daily_report 需要
CLEANUP_DELETE_BUDGET=15000          # data_cleanup 每個配額日最多刪除筆數（預設 15000）
```

## 資料清理（data_cleanup）

**清理範圍**（日期早於「台北今天 − 3 個月」者，當天本身保留）：

| 路徑 | 說明 |
| --- | --- |
| `market/{code}/{YYYYMMDD}` | 分鐘 K（掃描 `market` 下所有商品，不寫死 MXF） |
| `market/{code}/{YYYYMMDD}_tick` | 秒級明細 |
| `daily_reports/{YYYYMMDD}` | 每日分析報告 |
| `pttPosts/{YYYYMMDD}_{session}` | PTT 閒聊推文 |

`pttThreads` 每個盤別只有一份文件，不在清理範圍。ID 格式無法解析成日期的集合 / 文件會被略過並記錄 log，不會刪除。

**刪除額度控管**：Firestore 免費層每日 20,000 次刪除，太平洋時間午夜重置。
每批（最多 500 筆）刪除前，先用 transaction 在單一文件 `_maintenance/data_cleanup`
預扣額度（欄位 `quota_date` 為太平洋時間日期、`deleted` 為當日已預扣筆數）：

- 額度用完即停止，由舊到新處理，剩下的舊資料隔天自動接續（第一次上線若有大量積壓，會分多天消化）。
- 先預扣再刪除；批次 commit 結果不明（例如逾時）時額度不退還，寧可少刪也不超額。
- 同一配額日內不論 Scheduler 重送或手動重複觸發，累計刪除都不會超過 `CLEANUP_DELETE_BUDGET`。
- 計數只涵蓋這支函式；`migrate.py` 等其他刪除不會被計入，若要手動大量刪除請自行留意額度。
- 批次刪除失敗會停止本次執行並回傳 HTTP 500。

**手動觸發**（需具備 invoker 權限）：加上 `?dry_run=true` 只統計不刪除、不寫入計數。回傳 JSON 包含
`cutoff`、`deleted`、`budget_exhausted`、`skipped_ids`、`error`。

排程時間選在台北 06:00（夜盤 05:00 收盤後、日盤開盤前），此時間換算為前一天太平洋時間
14:00 / 15:00，每天一次剛好落在不同的配額日。`--max-retry-attempts=0` 避免失敗時重打。

## 本地測試

```bash
cd apps/functions
uv sync

# 手動測試每日報告（不需等待排程）
uv run python test_daily_report.py
uv run python test_daily_report.py --date 2026-07-04
uv run python test_daily_report.py --skip-save

# 手動測試籌碼快訊
uv run python test_chip_report.py

# PTT 閒聊爬蟲：pytest 單元測試 + 手動觸發（詳見 README_PTT_CHAT.md）
uv run pytest test_ptt_chat.py
uv run python test_ptt_chat_manual.py

# 資料清理：pytest 單元測試
uv run pytest test_data_cleanup.py

# 用 functions-framework 本地啟動 HTTP server 測試
uv run functions-framework --target=daily_report --debug
uv run functions-framework --target=chip_report --debug
uv run functions-framework --target=crawl_ptt_chat --debug
uv run functions-framework --target=data_cleanup --debug
```

## 部署（GitHub Action，推薦）

[.github/workflows/deploy-cron-job.yml](../../.github/workflows/deploy-cron-job.yml)
在 GitHub Actions 頁面手動觸發（`workflow_dispatch`），可選擇部署
`all` / `daily-report` / `chip-report` / `ptt-chat` / `data-cleanup`。流程：

1. 用 `uv export` 產生 `apps/functions` 專用的 `requirements.txt`（排除
   workspace 內的本地套件 `firestore-writer`）
2. 用 `uv build` 把 `firestore-writer` 打成 wheel，vendor 進
   `apps/functions/vendor/`，並把該 wheel 路徑補進 `requirements.txt`
   最後一行（`gcloud functions deploy` 的 buildpack 只認得
   `requirements.txt`，不會解析 `pyproject.toml` 的 workspace 依賴）
3. 透過 Workload Identity Federation 登入 GCP，執行對應的
   `gcloud functions deploy`

以上產出的 `requirements.txt` / `vendor/` 只存在於 Action 當次的 runner
工作目錄，不會 commit 回 repo。

### 需要的 GitHub Secrets

| Secret | 說明 |
| --- | --- |
| `GCP_PROJECT_ID` | 目標 GCP 專案 ID |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | WIF provider 資源全名，例如 `projects/123/locations/global/workloadIdentityPools/xxx/providers/xxx` |
| `GCP_SERVICE_ACCOUNT` | 供 GitHub Actions 冒充的 service account email，需具備 Cloud Functions/Cloud Build 部署權限 |

> ⚠️ GCP 端的 WIF pool/provider 建立、上述 service account 建立與授權，
> 都需要你自行在有權限的環境執行（見下方 gcloud 指令），不會由 Claude 自動執行。
> 部署前也請確認 GCP 專案已啟用 Cloud Functions、Cloud Build、Artifact
> Registry API（目前部署使用 `python314` runtime，與
> `pyproject.toml` 的 `requires-python = ">=3.14"` 相容）。

## 手動部署（gcloud CLI，備用／除錯用）

> ⚠️ 以下指令不會由 Claude 自動執行，僅供參考，邏輯與上方 GitHub Action 相同。

### 1. 部署 Cloud Functions

```bash
cd apps/functions

gcloud functions deploy daily-report \
  --gen2 \
  --runtime=python314 \
  --region=asia-east1 \
  --source=. \
  --entry-point=daily_report \
  --trigger-http \
  --no-allow-unauthenticated \
  --set-env-vars=GCP_PROJECT_ID=your-project-id \
  --set-secrets=GEMINI_API_KEY=gemini-api-key:latest

gcloud functions deploy chip-report \
  --gen2 \
  --runtime=python314 \
  --region=asia-east1 \
  --source=. \
  --entry-point=chip_report \
  --trigger-http \
  --no-allow-unauthenticated \
  --set-env-vars=GCP_PROJECT_ID=your-project-id

gcloud functions deploy ptt-chat \
  --gen2 \
  --runtime=python314 \
  --region=asia-east1 \
  --source=. \
  --entry-point=crawl_ptt_chat \
  --trigger-http \
  --no-allow-unauthenticated \
  --set-env-vars=GCP_PROJECT_ID=your-project-id

gcloud functions deploy data-cleanup \
  --gen2 \
  --runtime=python314 \
  --region=asia-east1 \
  --source=. \
  --entry-point=data_cleanup \
  --trigger-http \
  --no-allow-unauthenticated \
  --set-env-vars=GCP_PROJECT_ID=your-project-id,CLEANUP_DELETE_BUDGET=15000 \
  --timeout=540s \
  --max-instances=1
```

### 2. 建立服務帳戶供 Cloud Scheduler 呼叫

```bash
gcloud iam service-accounts create scheduler-invoker \
  --display-name="Cloud Scheduler Function Invoker"

gcloud functions add-invoker-policy-binding daily-report \
  --region=asia-east1 \
  --member="serviceAccount:scheduler-invoker@your-project-id.iam.gserviceaccount.com"

gcloud functions add-invoker-policy-binding chip-report \
  --region=asia-east1 \
  --member="serviceAccount:scheduler-invoker@your-project-id.iam.gserviceaccount.com"

gcloud functions add-invoker-policy-binding ptt-chat \
  --region=asia-east1 \
  --member="serviceAccount:scheduler-invoker@your-project-id.iam.gserviceaccount.com"

gcloud functions add-invoker-policy-binding data-cleanup \
  --region=asia-east1 \
  --member="serviceAccount:scheduler-invoker@your-project-id.iam.gserviceaccount.com"
```

### 3. 建立 Cloud Scheduler 排程（OIDC 觸發）

```bash
DAILY_REPORT_URL=$(gcloud functions describe daily-report --gen2 --region=asia-east1 --format='value(serviceConfig.uri)')
CHIP_REPORT_URL=$(gcloud functions describe chip-report --gen2 --region=asia-east1 --format='value(serviceConfig.uri)')
PTT_CHAT_URL=$(gcloud functions describe ptt-chat --gen2 --region=asia-east1 --format='value(serviceConfig.uri)')
DATA_CLEANUP_URL=$(gcloud functions describe data-cleanup --gen2 --region=asia-east1 --format='value(serviceConfig.uri)')

gcloud scheduler jobs create http daily-report-job \
  --location=asia-east1 \
  --schedule="0 8 * * 1-5" \
  --time-zone="Asia/Taipei" \
  --uri="$DAILY_REPORT_URL" \
  --http-method=POST \
  --oidc-service-account-email="scheduler-invoker@your-project-id.iam.gserviceaccount.com" \
  --max-retry-attempts=3 \
  --min-backoff=300s

gcloud scheduler jobs create http chip-report-job \
  --location=asia-east1 \
  --schedule="21 15 * * 1-5" \
  --time-zone="Asia/Taipei" \
  --uri="$CHIP_REPORT_URL" \
  --http-method=POST \
  --oidc-service-account-email="scheduler-invoker@your-project-id.iam.gserviceaccount.com" \
  --max-retry-attempts=3 \
  --min-backoff=600s

gcloud scheduler jobs create http ptt-chat-job \
  --location=asia-east1 \
  --schedule="* * * * *" \
  --time-zone="Asia/Taipei" \
  --uri="$PTT_CHAT_URL" \
  --http-method=POST \
  --oidc-service-account-email="scheduler-invoker@your-project-id.iam.gserviceaccount.com" \
  --max-retry-attempts=1 \
  --min-backoff=30s

# 每天一次（含週末，讓積壓的舊資料能持續分天消化）；不重試、attempt-deadline 與函式 timeout 同為 540s
gcloud scheduler jobs create http data-cleanup-job \
  --location=asia-east1 \
  --schedule="0 6 * * *" \
  --time-zone="Asia/Taipei" \
  --uri="$DATA_CLEANUP_URL" \
  --http-method=POST \
  --oidc-service-account-email="scheduler-invoker@your-project-id.iam.gserviceaccount.com" \
  --attempt-deadline=540s \
  --max-retry-attempts=0
```

`ptt-chat-job` 沒有用 `1-5` 排除週末——PTT 板面本身沒有交易日限制，`ptt_chat.py`
內部的 `resolve_current_session`/`resolve_session_date` 已經處理假日延續盤後閒聊的邏輯，
排程本身不需要跳過假日。`--max-retry-attempts=1` 是因為每分鐘都會重新觸發，重試意義不大。

Cron 排程已用 `1-5`（週一至週五）排除週末，`daily_report` 內部仍保留
`is_trading_day` 判斷作為第二層保護；國定假日目前沒有排除，與拆分前行為一致。

`daily_report` 呼叫 Gemini API 只執行一次（不再內建指數退避重試），失敗時回傳
HTTP 500，改由上方 `daily-report-job` 的 `--max-retry-attempts` / `--min-backoff`
接手重試。

## 相關文件

- [README_CHIP_REPORT.md](README_CHIP_REPORT.md) - 籌碼快訊裁切座標調整說明
- [README_PTT_CHAT.md](README_PTT_CHAT.md) - PTT 閒聊功能說明、Firestore schema、部署方式
