# Acceptance checklist

Operator-run verification of the [brief success criteria](brief.md#success-criteria). Uses a real `.env` (never commit secrets). Not run in CI.

## Prerequisites

- [ ] `.env` configured from `env.example` (at least one Starling/Actual channel pair)
- [ ] Actual server reachable (internal URL or Cloudflare Access service token)
- [ ] Starling PAT(s) match the channel(s) you enabled

## 1. Connect Actual ↔ Starling

- [ ] `just sync-once` completes without error (or `uv run main --once`)
- [ ] Logs show `startup` with expected `sync_channels` and `sync_once_complete` / `sync_channel_finish`
- [ ] Target Actual account(s) exist and match `ACTUAL_*_ACCOUNT_ID`

Docker equivalent:

```bash
docker compose run --rm sync main --once
```

## 2. New transactions import

- [ ] After a successful `--once`, Actual shows Starling transactions (settled) on the mapped account(s)
- [ ] Optional: wait for a new settled Starling tx, run `--once` again, confirm it appears

## 3. Repeated syncs produce no duplicates

- [ ] Run `just sync-once` a second time immediately
- [ ] Logs show import with `unchanged` / skips (or `imported=0` if nothing new)
- [ ] Actual account does not gain duplicate rows for the same Starling feed items

## 4. Temporary failure recovery

Covered primarily by unit tests (channel/cycle errors do not corrupt checkpoints; scheduler continues). Live optional:

- [ ] With Compose running (`just docker-up`), briefly break network or Actual URL, observe `sync_channel_failed` / cycle error logs
- [ ] Restore connectivity; next cycle succeeds and checkpoint advances

## 5. Deploy = env + Docker Compose

- [ ] Fresh clone (or clean machine): `cp env.example .env`, fill secrets, `docker compose up -d --build`
- [ ] Container stays up (`restart: unless-stopped`); logs show `scheduler_start` and periodic sync
- [ ] `./data` persists `sync.db` and Actual cache across restarts

## Sign-off

| Criterion | Pass? | Notes |
|-----------|-------|-------|
| Connect Starling → Actual | | |
| Imports new transactions | | |
| No duplicates on repeat | | |
| Recovers from temp failures | | |
| Env + Compose deploy | | |

Date / environment: _______________________
