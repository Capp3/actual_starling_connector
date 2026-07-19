# Development

## Tooling

```bash
just install          # uv sync --group dev
just lint             # ruff format/fix + mypy
just test             # pytest
just cov              # pytest + coverage (fail under 95%)
just lint-ci          # check-only (CI-friendly)
```

App dependencies stay in `pyproject.toml` / `uv.lock`. MkDocs is **not** an app dependency.

## Documentation site

This site is MkDocs with the built-in **readthedocs** theme.

```bash
just docs-serve       # uvx mkdocs serve
just docs-build       # uvx mkdocs build --strict
```

- Config: `mkdocs.yml` at the repo root  
- Pages: `docs/*.md`  
- CI: `.github/workflows/docs.yml` installs **uv**, creates a venv, `uv pip install mkdocs` (no `requirements.txt`), builds with `--strict`, and deploys to **GitHub Pages** on pushes to `main`

### Enable GitHub Pages (one-time)

In the GitHub repo: **Settings → Pages → Build and deployment → Source: GitHub Actions**.

Published URL: [https://capp3.github.io/actual_starling_connector/](https://capp3.github.io/actual_starling_connector/)

## CI jobs

| Workflow | Purpose |
|----------|---------|
| `ci.yml` | `lint-ci` + `cov` (app tests) |
| `docs.yml` | MkDocs build; deploy Pages on `main` |

## External references

- Starling API: https://developer.starlingbank.com/docs  
- Actual Budget: https://actualbudget.org/docs/  
- This connector talks to Actual via [actualpy](https://github.com/bvanelli/actualpy) (not the Node API client)  
