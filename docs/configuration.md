# Configuration

All runtime config is via environment variables (or Docker `*_FILE` secrets). Copy [`env.example`](https://github.com/Capp3/actual_starling_connector/blob/main/env.example) to `.env` and edit.

## Shared Actual (required)

| Variable | Purpose |
|----------|---------|
| `ACTUAL_SERVER_URL` | Actual server base URL |
| `ACTUAL_SYNC_PASSWORD` | Server password (**not** the file encryption password) |
| `ACTUAL_BUDGET_SYNC_ID` | Budget file sync ID |

## Sync channels (at least one full pair)

| Individual | Joint |
|------------|-------|
| `STARLING_INDIVIDUAL_ACCESS_TOKEN` | `STARLING_JOINT_ACCESS_TOKEN` |
| `ACTUAL_INDIVIDUAL_ACCOUNT_ID` | `ACTUAL_JOINT_ACCOUNT_ID` |

A channel is enabled only when **both** its token and Actual account id/name are set. Half-configured pairs fail validation at startup.

### Individual and joint in one process

Use **one container** (or one local process) with both channel pairs when you want personal and joint feeds:

1. Create a Starling PAT for the **individual** holder and one for the **joint** holder.  
2. Set both token + Actual account pairs.  
3. Checkpoints are stored per holder in the same SQLite file (`DATABASE_PATH`), so lookbacks stay independent.

If a channel fails (bad token, wrong holder type, Actual account missing), the other channel still syncs. The cycle only errors hard if every enabled channel fails.

## Common optionals

| Variable | Default / notes |
|----------|-----------------|
| `ACTUAL_ENCRYPTION_PASSWORD` | Required if the budget file is end-to-end encrypted |
| `SYNC_INTERVAL_MINUTES` | `60` — first tick runs immediately |
| `LOG_LEVEL` | `INFO` |
| `DATABASE_PATH` | `data/sync.db` (Compose: `/data/sync.db`) |
| `ACTUAL_DATA_DIR` | `data/actual` (Compose: `/data/actual`) |
| `TIMEZONE` | `UTC` |
| `ACTUAL_CF_ACCESS_CLIENT_ID` / `ACTUAL_CF_ACCESS_CLIENT_SECRET` | Cloudflare Access service token (both required together) |

## Docker secrets (`*_FILE`)

Prefer `NAME_FILE=/run/secrets/...` for tokens and passwords in Compose. When set, the file contents override the plain env var. See `env.example` for the full list.

## Legacy env keys

Older names such as `STARLING_ACCESS_TOKEN`, `STARLING_ACCOUNT_HOLDER_TYPE`, and `ACTUAL_ACCOUNT_ID` are **ignored**. Use the individual/joint pairs above.
