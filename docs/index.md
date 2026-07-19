# actual-starling-sync

Self-hosted worker that syncs **settled** Starling Bank transactions into a self-hosted [Actual Budget](https://actualbudget.org/) instance on a schedule.

One process can sync **personal** and/or **joint** Starling account holders into separate Actual accounts, each with its own checkpoint.

## What it does

1. Polls the Starling Customer API for feed items since the last successful sync  
2. Maps settled transactions into Actual (idempotent via Starling feed item UIDs)  
3. Persists per-holder progress in SQLite  
4. Repeats on `SYNC_INTERVAL_MINUTES` (or exits after one cycle with `--once`)

## Quick links

| Topic | Page |
|-------|------|
| Install locally or with Docker | [Installation](installation.md) |
| Env vars and channel pairs | [Configuration](configuration.md) |
| Logs, state, Cloudflare Access | [Operations](operations.md) |
| Live success-criteria checklist | [Acceptance](acceptance.md) |
| Lint, tests, docs recipes | [Development](development.md) |

Full variable comments live in [`env.example`](https://github.com/Capp3/actual_starling_connector/blob/main/env.example) at the repo root.
