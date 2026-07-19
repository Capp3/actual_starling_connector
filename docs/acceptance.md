# Acceptance

Operator-run verification of the product [success criteria](https://github.com/Capp3/actual_starling_connector/blob/main/brief.md). Uses a real `.env` (never commit secrets). **Not** run in CI.

## Checklist source of truth

Tick boxes and sign off in the repo-root file:

**[`ACCEPTANCE.md`](https://github.com/Capp3/actual_starling_connector/blob/main/ACCEPTANCE.md)**

That file covers:

1. Connect Actual ↔ Starling (`just sync-once` / Compose one-shot)  
2. New settled transactions import  
3. Repeat sync produces no duplicates  
4. Temporary failure recovery (optional live; covered by unit tests)  
5. Deploy = env vars + Docker Compose  

## Minimal path

```bash
cp env.example .env   # fill secrets
just sync-once
just sync-once        # second run — expect no duplicates
just docker-up        # optional scheduled proof
```

Then complete the sign-off table in `ACCEPTANCE.md`.
