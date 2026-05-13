# 只支援 linux base shell (windows 可以用 git bash)

ROOT_DIR := justfile_directory()


dev:
    cd skills && pnpm install
    docker compose up -d
    cd apps/price-listener && uv sync && uv run main

init:
    node --version
    npm --version
    pnpm --version
    just --version
    powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
    npm install -g firebase-tools
