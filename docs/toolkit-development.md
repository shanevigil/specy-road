# Developing the specy-road toolkit

This guide is for **maintainers and contributors** working on the `specy-road` package, validators, and optional PM UI in **this** repository. It does **not** apply to application repositories that use `specy-road init project`.

To participate in development, contact the **repository owner** (or maintainers) before investing significant time; they can confirm priorities and access.

## Environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-ci.txt
```

`requirements-ci.txt` is a compiled lock matching CI; regenerate with `pip-compile` — see [supply-chain-security.md](supply-chain-security.md). The short [requirements.txt](../requirements.txt) at the repo root mirrors core runtime deps from `pyproject.toml` for reference only.

## Validate and test (dogfood)

```bash
specy-road validate --repo-root tests/fixtures/specy_road_dogfood
specy-road export --check --repo-root tests/fixtures/specy_road_dogfood
specy-road file-limits
pytest
# After changing gui/pm-gantt sources:
#   cd gui/pm-gantt && npm ci && npm run lint && npm test && npm run build
```

## Dependency and supply-chain

See [supply-chain-security.md](supply-chain-security.md). Quick checks: after `pip install -r requirements-ci.txt`, run `pip install pip-audit && pip-audit`; for the Gantt UI tree, `cd gui/pm-gantt && npm ci && npm audit --omit=dev`. More detail: [contributor-guide.md](contributor-guide.md#supply-chain--dependency-audits).

## `specy-road init project` in this repo

With no path, the CLI uses the git worktree root—in **this** repo that would scaffold into the toolkit tree. Prefer an explicit directory (for example `specy-road init project /tmp/specy-consumer-sandbox`) or the gitignored [playground/](../playground/README.md).

## Optional: pre-commit

`pip install pre-commit && pre-commit install` — runs part of CI (roadmap validate, export `--check`, file limits), not supply-chain audits or `pytest`. See [contributor-guide.md](contributor-guide.md#pre-commit-hook).

## Maintainer workflow vs consumer workflow

**Application repositories** set `integration_branch` and `remote` in `roadmap/git-workflow.yaml` after `specy-road init project`; the CLI and PM Gantt read that file unless overridden by flags or environment variables (see [git-workflow.md](git-workflow.md)). Examples elsewhere that mention `main` or `dev` are illustrative—not a default for your repo.

**This toolkit repository** uses its own policy for package work: topic branches merge to **`dev`**, and **`main`** is release-facing via promotion PRs auto-tagged by [`main-release-tag-gate.yml`](../.github/workflows/main-release-tag-gate.yml) and published by [`release-publish.yml`](../.github/workflows/release-publish.yml). The full branching, tagging, PR-conventions, and release process lives in [contributor-guide.md](contributor-guide.md#branching-tagging-and-release-process). That is **not** the workflow contract for other repos using specy-road; those stay configurable via `roadmap/git-workflow.yaml`.

## See also

- [AGENTS.md](../AGENTS.md) — contributor load order and coordination
- [dev-workflow.md](dev-workflow.md) — executing roadmap items (consumer repos)
- [git-workflow.md](git-workflow.md) — consumer git contract
