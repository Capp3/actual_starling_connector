# Installation

## Prerequisites

- **Docker** (recommended), or **Python 3.12+** with [uv](https://docs.astral.sh/uv/) and [just](https://github.com/casey/just)
- Starling [personal access token(s)](https://developer.starlingbank.com/docs) — **one PAT per account holder** (individual vs joint are different holders)
- A running Actual server, budget sync ID, sync password, and target account id(s) or name(s)

## Configure environment

```bash
cp env.example .env
# edit .env — see Configuration and env.example
```

## Run with Docker Compose (recommended)

```bash
just docker-up        # or: docker compose up -d --build
just docker-down
```

Compose mounts `./data` → `/data`, sets `DATABASE_PATH=/data/sync.db` and `ACTUAL_DATA_DIR=/data/actual`, and uses `restart: unless-stopped` with a 60s stop grace period (SIGINT/SIGTERM).

One-shot sync inside the image:

```bash
docker compose run --rm sync main --once
```

## Run locally

```bash
just install          # uv sync (dev tools included)
uv run main           # long-running scheduler (Ctrl+C to stop)
just sync-once        # one sync cycle then exit (acceptance / cron)
```

## Next steps

- [Configuration](configuration.md) — channel pairs and optionals  
- [Operations](operations.md) — logs, volumes, troubleshooting  
- [Acceptance](acceptance.md) — prove the brief success criteria  
