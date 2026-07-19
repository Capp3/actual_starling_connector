# Operations

## Logs

Structured JSON on stdout. Useful events include `startup`, `scheduler_start`, `sync_cycle_*`, `sync_channel_*`, and `sync_once_complete`. Secrets are not logged.

## Schedule

`SYNC_INTERVAL_MINUTES` controls the loop. The first cycle runs **immediately** on start. For a single cycle without the scheduler, use:

```bash
just sync-once
# or
uv run main --once
# or
docker compose run --rm sync main --once
```

## State and volumes

| Path | Role |
|------|------|
| `DATABASE_PATH` | SQLite checkpoints (per holder type) |
| `ACTUAL_DATA_DIR` | actualpy budget cache |

Under Compose, both live on the `./data` bind mount (`/data/...` in the container). Keep that volume if you restart or recreate the service.

## Encrypted budgets

Set `ACTUAL_ENCRYPTION_PASSWORD` when the Actual budget file uses end-to-end encryption. This is **not** the same as `ACTUAL_SYNC_PASSWORD`.

## Cloudflare Access

If Actual sits behind Cloudflare Access:

- Point `ACTUAL_SERVER_URL` at an **internal** URL that bypasses Access, **or**
- Set both `ACTUAL_CF_ACCESS_CLIENT_ID` and `ACTUAL_CF_ACCESS_CLIENT_SECRET` (service token headers).

## Secrets

Prefer `*_FILE` Docker secrets for tokens and passwords. Avoid committing `.env`.

## Failure behaviour

- Per-channel failures are logged; other channels continue.  
- Checkpoints advance only after a successful channel import.  
- The scheduler continues after a failed cycle.  
- The process raises only if **all** enabled channels fail in a cycle.
