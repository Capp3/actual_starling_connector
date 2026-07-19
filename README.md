# actual-starling-sync

Self-hosted worker that syncs settled Starling Bank transactions into a self-hosted [Actual Budget](https://actualbudget.org/) instance on a schedule. One process can sync personal and/or joint Starling holders into separate Actual accounts.

**Documentation:** [https://capp3.github.io/actual_starling_connector/](https://capp3.github.io/actual_starling_connector/)  
(Local preview: `just docs-serve`)

## Quick start (Docker)

```bash
cp env.example .env   # fill secrets — see docs Configuration + env.example comments
just docker-up        # or: docker compose up -d --build
just sync-once        # optional one-shot: docker compose run --rm sync main --once
```

## Local run

```bash
just install
uv run main           # scheduler
just sync-once        # one cycle then exit
```

## Repository pointers

| Resource | Location |
|----------|----------|
| Full docs | [GitHub Pages](https://capp3.github.io/actual_starling_connector/) / `docs/` |
| Env reference | [`env.example`](env.example) |
| Acceptance checklist | [`ACCEPTANCE.md`](ACCEPTANCE.md) |
| Product brief | [`brief.md`](brief.md) |

## Development

```bash
just lint && just test   # or: just cov
just docs-build          # MkDocs --strict
```
