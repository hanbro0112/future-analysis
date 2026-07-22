# Functions - 定時任務 Cloud Functions

由 Cloud Scheduler + Cloud Functions (2nd gen) 執行，

## 功能

| Function 名稱 | 檔案 | 說明 | 排程 |
| --- | --- | --- | --- |
| `daily_report` | `daily_report.py` | 使用 Gemini API 分析台股/美股，寫入 Firestore `daily_reports/{YYYYMMDD}` | 每天 08:00（僅交易日執行，週末由程式內部判斷跳過） |
| `chip_report` | `chip_report.py` | 抓取台指籌碼快訊 PDF，提取圖表上傳 Cloud Storage `chip-reports/{YYYYMMDD}/` | 每交易日 15:21 |

兩個 function 都是 HTTP-triggered，`main.py` 匯入兩者供 `gcloud functions deploy --entry-point` 使用。

## 環境變數

```bash
GCP_PROJECT_ID=demo-project
GEMINI_API_KEY=your-gemini-api-key   # daily_report 需要
```

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

# 用 functions-framework 本地啟動 HTTP server 測試
uv run functions-framework --target=daily_report --debug
uv run functions-framework --target=chip_report --debug
```

## 部署（GitHub Action，推薦）

[.github/workflows/deploy-functions.yml](../../.github/workflows/deploy-functions.yml)
在 GitHub Actions 頁面手動觸發（`workflow_dispatch`），可選擇部署
`both` / `daily-report` / `chip-report`。流程：

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
> Registry API，且 Cloud Functions 支援的 Python runtime 版本與
> `pyproject.toml` 的 `requires-python` 相容（目前設定為 `>=3.14`，若部署
> 環境的 runtime 版本不到 3.14，需要調降此設定）。

## 手動部署（gcloud CLI，備用／除錯用）

> ⚠️ 以下指令不會由 Claude 自動執行，僅供參考，邏輯與上方 GitHub Action 相同。

### 1. 部署 Cloud Functions

```bash
cd apps/functions

gcloud functions deploy daily-report \
  --gen2 \
  --runtime=python313 \
  --region=asia-east1 \
  --source=. \
  --entry-point=daily_report \
  --trigger-http \
  --no-allow-unauthenticated \
  --set-env-vars=GCP_PROJECT_ID=your-project-id \
  --set-secrets=GEMINI_API_KEY=gemini-api-key:latest

gcloud functions deploy chip-report \
  --gen2 \
  --runtime=python313 \
  --region=asia-east1 \
  --source=. \
  --entry-point=chip_report \
  --trigger-http \
  --no-allow-unauthenticated \
  --set-env-vars=GCP_PROJECT_ID=your-project-id
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
```

### 3. 建立 Cloud Scheduler 排程（OIDC 觸發）

```bash
DAILY_REPORT_URL=$(gcloud functions describe daily-report --gen2 --region=asia-east1 --format='value(serviceConfig.uri)')
CHIP_REPORT_URL=$(gcloud functions describe chip-report --gen2 --region=asia-east1 --format='value(serviceConfig.uri)')

gcloud scheduler jobs create http daily-report-job \
  --location=asia-east1 \
  --schedule="0 8 * * 1-5" \
  --time-zone="Asia/Taipei" \
  --uri="$DAILY_REPORT_URL" \
  --http-method=POST \
  --oidc-service-account-email="scheduler-invoker@your-project-id.iam.gserviceaccount.com"

gcloud scheduler jobs create http chip-report-job \
  --location=asia-east1 \
  --schedule="21 15 * * 1-5" \
  --time-zone="Asia/Taipei" \
  --uri="$CHIP_REPORT_URL" \
  --http-method=POST \
  --oidc-service-account-email="scheduler-invoker@your-project-id.iam.gserviceaccount.com"
```

Cron 排程已用 `1-5`（週一至週五）排除週末，`daily_report` 內部仍保留
`is_trading_day` 判斷作為第二層保護；國定假日目前沒有排除，與拆分前行為一致。

## 相關文件

- [README_CHIP_REPORT.md](README_CHIP_REPORT.md) - 籌碼快訊裁切座標調整說明
