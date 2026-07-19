install:
    uv lock --upgrade
    uv sync --group dev --frozen

install-uv:
    curl -LsSf https://astral.sh/uv/install.sh | sh

lint:
    uv run ruff format src tests
    uv run ruff check --fix src tests
    uv run mypy src

lint-ci:
    uv run ruff format --check src tests
    uv run ruff check --no-fix src tests
    uv run mypy src

test:
    uv run pytest

cov:
    uv run pytest --cov=actual_starling_connector --cov-report=term-missing --cov-fail-under=95

sync-once:
    uv run main --once

docker-build:
    docker compose build

docker-up:
    docker compose up -d

docker-down:
    docker compose down

docs-serve:
    uvx mkdocs serve

docs-build:
    uvx mkdocs build --strict
