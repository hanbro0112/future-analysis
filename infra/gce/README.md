# GCE 部署 — 一次性建置步驟

`price-listener` / `price-analyzer` / `price-broadcaster` 三個服務改跑在同一台 GCE VM 上，
用 Docker Compose 管理，`caddy` 負責 TLS 終止並反代到 `price-broadcaster`。
建置與部署由 [`.github/workflows/deploy-apps-gce.yml`](../../.github/workflows/deploy-apps-gce.yml)
透過 `gcloud compute ssh`（IAP Tunnel，不開放 22 對外）觸發。

以下步驟只需要在第一次建置環境時執行一次，之後改版只要跑 GitHub Actions workflow。

## 0. 前置變數

```bash
export PROJECT_ID="你的 GCP 專案 ID"          # 與 deploy-apps.yml 用的 GCP_PROJECT_ID 相同
export REGION="asia-east1"
export ZONE="asia-east1-b"
export VM_NAME="future-analysis-vm"
export VM_SA="future-analysis-gce@${PROJECT_ID}.iam.gserviceaccount.com"
export DEPLOY_SA="現有 GitHub Actions WIF 用的 secrets.GCP_SERVICE_ACCOUNT"

gcloud config set project "$PROJECT_ID"
```

## 1. 啟用必要 API

```bash
gcloud services enable \
  compute.googleapis.com \
  iap.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com
```

## 2. 建立 VM 專用 Service Account

VM 上的服務靠這個帳號的 ADC 存取 Pub/Sub、Firestore、Secret Manager、Artifact Registry，
不需要金鑰檔。

> Pub/Sub 使用 `roles/pubsub.editor`：服務啟動時會 `get_topic` / `get_subscription`，
> 不存在就自動建立。`pubsub.publisher` 只有發布權限、`pubsub.subscriber` 沒有 topic 的讀取與建立權限，
> 搭配起來 `price-listener` 與 `price-analyzer` 會在啟動時 PermissionDenied。

```bash
gcloud iam service-accounts create future-analysis-gce \
  --display-name="future-analysis GCE VM"

for ROLE in \
  roles/secretmanager.secretAccessor \
  roles/artifactregistry.reader \
  roles/pubsub.editor \
  roles/datastore.user
do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${VM_SA}" \
    --role="$ROLE"
done
```

## 3. 建立 Cloudflare Origin CA 憑證的 Secret Manager 項目

1. 到 Cloudflare Dashboard → 該網域 → **SSL/TLS → Origin Server → Create Certificate**
   （Key type 選 RSA 即可，Hostnames 填 `ws.txfutures.com`，有效期選最長 15 年）
2. 建立後會拿到 Origin Certificate（PEM）與 Private Key 兩段文字，分別存成密鑰：

```bash
gcloud secrets create cf-origin-cert --replication-policy=automatic
gcloud secrets create cf-origin-key --replication-policy=automatic

# 貼上 Cloudflare 給的 Origin Certificate 內容，Ctrl+D 結束輸入
gcloud secrets versions add cf-origin-cert --data-file=-
# 貼上 Cloudflare 給的 Private Key 內容，Ctrl+D 結束輸入
gcloud secrets versions add cf-origin-key --data-file=-
```

> 既有的 `shioaji-api-key` / `shioaji-secret-key` / `shioaji-ca-password` / `shioaji-ca-cert`
> 三個服務會直接沿用，不用重建。

## 4. 防火牆規則

```bash
# Caddy 對外只開 443
gcloud compute firewall-rules create allow-https-caddy \
  --network=default \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:443 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=future-analysis-gce

# SSH 只允許透過 IAP（35.235.240.0/20 是 Google IAP 的固定來源範圍）
gcloud compute firewall-rules create allow-iap-ssh \
  --network=default \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20 \
  --target-tags=future-analysis-gce
```

## 5. 開啟 OS Login，並授權部署身分

```bash
gcloud compute project-info add-metadata --metadata enable-oslogin=TRUE

# 讓現有 GitHub Actions 部署身分可以用 IAP Tunnel SSH 進這台 VM
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/iap.tunnelResourceAccessor"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${DEPLOY_SA}" \
  --role="roles/compute.osAdminLogin"
```

## 6. 建立 VM

```bash
gcloud compute instances create "$VM_NAME" \
  --zone="$ZONE" \
  --machine-type=e2-small \
  --image-family=debian-13 \
  --image-project=debian-cloud \
  --boot-disk-size=20GB \
  --boot-disk-type=pd-balanced \
  --service-account="$VM_SA" \
  --scopes=cloud-platform \
  --tags=future-analysis-gce \
  --metadata-from-file=startup-script=infra/gce/startup-script.sh
```

啟動完成後（約 1-2 分鐘），確認外部 IP：

```bash
gcloud compute instances describe "$VM_NAME" --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

## 7. 設定 Cloudflare DNS

在 Cloudflare DNS 新增一筆 **A 記錄**（Proxy status 開啟橘色雲朵）：

```
ws.txfutures.com  A  <VM 外部 IP>  Proxied
```

並到 **SSL/TLS → Overview** 把加密模式設為 **Full (strict)**。

## 8. 第一次部署

到 GitHub Actions 手動觸發 `Deploy Apps to GCE` workflow。
三個服務固定一起建置與部署（VM 上的 compose 共用同一個映像標籤，無法只部署其中一個）。
完成後可用以下方式驗證：

```bash
# 健康檢查（經 Cloudflare）
curl https://ws.txfutures.com/health

# 查看 VM 上容器狀態
gcloud compute ssh --tunnel-through-iap --zone="$ZONE" "$VM_NAME" \
  --command="cd /opt/future-analysis && sudo docker compose ps"
```

確認 GCE 版本運作穩定後，再把前端建置用的 `NEXT_PUBLIC_WS_URL` GitHub Secret
改成 `wss://ws.txfutures.com`，重新跑 `Deploy Web to Cloudflare Pages` 切換流量。
在那之前 `deploy-apps.yml`（Cloud Run）維持不動，兩者並存互不影響。

## 部署注意事項

### 避開交易時段部署

三個服務在啟用窗口內（開盤前 5 分鐘到收盤後緩衝）會持續運作，部署會重啟它們，代價如下：

- `price-listener` 重啟期間來源停止發布，這段時間的 tick **會遺失**。
- `price-analyzer`、`price-broadcaster` 重啟期間的 tick 會留在 Pub/Sub，重啟後補送，不會遺失。
- 重啟那一分鐘的分鐘文件會被覆蓋成只含重啟後的資料（Firestore 是覆蓋寫入），該分鐘的 OHLC 與成交量不完整。
- 多空比等分析視窗（1／5／30 分鐘）與當日成交量均值會重新累積。

建議在 **13:50 到 14:55 之間**（日盤收盤與夜盤預熱之間），或**週末與休市日**部署。

### 服務重啟時的收尾

`docker compose up -d` 重建容器時會先送 SIGTERM，listener 與 analyzer 設定了 30 秒停機寬限期
（compose 預設只有 10 秒）：listener 要登出 Shioaji，沒登出會佔住連線數；analyzer 要把未完成的資料 flush 到 Firestore。

### 修改 Caddyfile

`Caddyfile` 是 bind mount，內容變更時 compose 不會自動重建容器。部署後需要在 VM 上手動套用：

```bash
gcloud compute ssh --tunnel-through-iap --zone="$ZONE" "$VM_NAME" \
  --command="cd /opt/future-analysis && sudo docker compose restart caddy"
```
