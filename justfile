# 只支援 linux base shell (windows 可以用 git bash)

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
