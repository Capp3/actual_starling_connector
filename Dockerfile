FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    DATABASE_PATH=/data/sync.db \
    ACTUAL_DATA_DIR=/data/actual

WORKDIR /app

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /data/actual \
    && chown -R app:app /data

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY docker-entrypoint.sh /docker-entrypoint.sh

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && chown -R app:app /app \
    && chmod +x /docker-entrypoint.sh

# Entrypoint runs as root to chown bind-mounted /data, then drops to app.
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["main"]
