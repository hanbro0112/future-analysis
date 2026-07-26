FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 複製整個 apps workspace（需要 libs/pubsub、libs/firestore-writer 等共用套件與 workspace lock 檔）
COPY . .

RUN uv sync --frozen --no-dev --package price-broadcaster

FROM python:3.14-slim

WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080
CMD ["python", "-m", "price-broadcaster.main"]
