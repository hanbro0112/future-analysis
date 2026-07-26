# 只支援 linux base shell (windows 可以用 git bash)
# windows 安裝 gh cli 發 pr: winget install --id GitHub.cli
# windows 安裝 gcloud cli: (New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe") & $env:Temp\GoogleCloudSDKInstaller.exe
    

ROOT_DIR := justfile_directory()


dev:
    cd skills && pnpm install
    docker compose up -d
    cd apps && uv sync && uv run main

tmp:
    cd apps && uv sync --package price-analyzer && uv run --package price-analyzer python -m price-analyzer.main
    cd apps && uv sync --package price-broadcaster && uv run --package price-broadcaster python -m price-broadcaster.main
    cd apps && uv sync --package price-listener && uv run --package price-listener python -m price-listener.main

init:
    node --version
    npm --version
    pnpm --version
    just --version
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    npm install -g firebase-tools
