#!/usr/bin/env bash
# GCE VM 開機腳本，透過 instance metadata 在每次開機時執行（已安裝的項目會略過，可重複執行）：
# 安裝 Docker Engine + Compose plugin、gcloud CLI，並設定 Artifact Registry 認證。
set -euo pipefail

# 開機初期常有其他 apt 程序（如 Ops Agent）佔用 dpkg lock，改為等待最多 5 分鐘而非直接失敗
apt-get() { command apt-get -o DPkg::Lock::Timeout=300 "$@"; }

if ! command -v docker &>/dev/null; then
  apt-get update
  apt-get install -y ca-certificates curl gnupg
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

if ! command -v gcloud &>/dev/null; then
  install -m 0755 -d /usr/share/keyrings
  curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
  echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
    > /etc/apt/sources.list.d/google-cloud-sdk.list
  apt-get update
  apt-get install -y google-cloud-cli
fi

gcloud auth configure-docker asia-east1-docker.pkg.dev --quiet

mkdir -p /opt/future-analysis
