#!/usr/bin/env bash
# 在 GCE VM 上執行：向 Secret Manager 抓取最新機密、更新 docker image 並重啟服務。
# 由 GitHub Actions 透過 IAP SSH 呼叫，也可以在 VM 上手動執行來重新部署同一版本。
#
# 用法：deploy.sh <IMAGE_TAG>（IMAGE_TAG 通常是 git commit sha）
set -euo pipefail

APP_DIR="/opt/future-analysis"
IMAGE_TAG="${1:?請提供 image tag（git sha）}"

PROJECT_ID="$(curl -s -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/project/project-id')"

fetch_secret() {
  gcloud secrets versions access latest --secret="$1" --project="$PROJECT_ID"
}

mkdir -p "$APP_DIR/certs"

# 先用變數取值：heredoc 內的 $(...) 失敗不會讓 set -e 中止，會把空值寫進 .env 後繼續往下跑。
# 不要寫成 `local VAR=$(...)` 或 `export VAR=$(...)`，那會吃掉失敗狀態。
API_KEY="$(fetch_secret shioaji-api-key)"
SECRET_KEY="$(fetch_secret shioaji-secret-key)"
CA_PASSWORD="$(fetch_secret shioaji-ca-password)"

cat > "$APP_DIR/.env" <<ENV
GCP_PROJECT_ID=${PROJECT_ID}
PUBSUB_TOPIC_ID=price-updates
PUBSUB_SUBSCRIPTION_ID_ANALYZER=price-analyzer-subscription
PUBSUB_SUBSCRIPTION_ID_BROADCASTER=price-broadcaster-subscription
API_KEY=${API_KEY}
SECRET_KEY=${SECRET_KEY}
CA_PASSWORD=${CA_PASSWORD}
CA_CERT_PATH=/secrets/ca.pfx
REGION=asia-east1
REPOSITORY=apps
IMAGE_TAG=${IMAGE_TAG}
ENV
chmod 600 "$APP_DIR/.env"

# 憑證是二進位，必須用 --out-file；經 stdout 重導向會被當文字轉碼而損毀
gcloud secrets versions access latest --secret=shioaji-ca-cert \
  --project="$PROJECT_ID" --out-file="$APP_DIR/certs/ca.pfx"
fetch_secret cf-origin-cert > "$APP_DIR/certs/cf-origin.pem"
fetch_secret cf-origin-key > "$APP_DIR/certs/cf-origin.key"
chmod 600 "$APP_DIR/certs/"*

cd "$APP_DIR"
docker compose pull
docker compose up -d --remove-orphans
docker image prune -f
