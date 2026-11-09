# Developing the specy-road toolkit

This guide is for **maintainers and contributors** working on the `specy-road` package, validators, and optional PM UI in **this** repository. It does **not** apply to application repositories that use `specy-road init project`.

The dogfood tree under [`tests/fixtures/specy_road_dogfood/`](../tests/fixtures/specy_road_dogfood/) is the repository's **test-fixture roadmap**: it keeps validators, exports, briefs, and GUI flows exercised against a consumer-shaped project. It is not the canonical product roadmap for the `specy-road` toolkit; the toolkit's own product roadmap lives under `sr/` on the `WIP/improvements-x-y-z` line, is stripped before promotion, and is not in the tree on `main`.

To participate in development, contact the **repository owner** (or maintainers) before investing significant time; they can confirm priorities and access.

## Environment

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-ci.txt
```

`requirements-ci.txt` is a compiled lock matching CI; regenerate with `pip-compile` — see [supply-chain-security.md](supply-chain-security.md). The short [requirements.txt](../requirements.txt) at the repo root mirrors core runtime deps from `pyproject.toml` for reference only.

## Validate and test (dogfood fixture)

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

Use `playground/` when you want to pretend this clone contains a separate consumer app. Keep the dogfood fixture for tests and sample data.

## Optional: pre-commit

`pip install pre-commit && pre-commit install` — runs part of CI (roadmap validate, export `--check`, file limits), not supply-chain audits or `pytest`. See [contributor-guide.md](contributor-guide.md#pre-commit-hook).

## Maintainer workflow vs consumer workflow

**Application repositories** set `integration_branch` and `remote` in `roadmap/git-workflow.yaml` after `specy-road init project`; the CLI and PM Gantt read that file unless overridden by flags or environment variables (see [git-workflow.md](git-workflow.md)). Examples elsewhere that mention `main` or `dev` are illustrative—not a default for your repo.

**This toolkit repository** has its own branch policy, stated only here (the agent entry [AGENTS.md](../AGENTS.md) and the Cursor rule `.cursor/rules/030-git-workflow-management.mdc` link to it). It is **not** the workflow contract for other repos using specy-road; those stay configurable via `roadmap/git-workflow.yaml`.

- **Branches:** `dev` is the working integration branch; `main` is the default, protected, release-facing branch and moves only by promotion PR.
- **Batch line:** a temporary `WIP/improvements-x-y-z` branch collects the next set of improvements toward release or release candidate `x.y.z`. Each logical change lives on its own short-lived topic branch and is merged into the WIP for integration, then promoted through `dev`.
- **Topic branch base:** when a WIP line is active for your work, start the topic branch from it (`git fetch`, `git checkout WIP/improvements-x-y-z`, `git pull`, then `git checkout -b feature/<slug>`), not from `dev` in isolation, so the branch already holds the batch's integration and docs. With no active WIP, branch from `dev`.
- **Topic branch names:** `feature/<slug>` (new features), `chore/<slug>` (maintenance, tooling, refactors), `fix/<slug>` or `hotfix/<slug>` (patches), `docs/<slug>` (documentation only); the enforced regex is in [contributor-guide.md](contributor-guide.md#branch-naming-convention-enforced).
- **Promotion:** topic branch → `dev` (or the WIP when it is the agreed integration line) → PR → `main`. Avoid direct commits to `dev` or `main` unless a maintainer asks for one-off repository administration.
- **PR requirement:** a PR is **required only for promotion to `main`**. A solo maintainer may merge topic branches into the WIP line, and the WIP line into `dev`, directly, after running the full gate suite locally (`pytest`, `specy-road validate`/`export --check` on the dogfood fixture, `specy-road file-limits`). With **multiple developers**, prefer a PR into `dev` (and review on the WIP) so changes are visible before they land.
- **Release marker:** a PR to `main` carries exactly one marker, title `release: vX.Y.Z[-rcN]` or label `release:vX.Y.Z[-rcN]` (leading `v` mandatory), checked by [`main-release-tag-gate.yml`](../.github/workflows/main-release-tag-gate.yml), which tags the merge commit; [`release-publish.yml`](../.github/workflows/release-publish.yml) publishes it. Release branch names, the marker and every release step are in [release-runbook.md](release-runbook.md); version numbers are human-owned ([AGENTS.md](../AGENTS.md#version-numbers-human-owned)).

## See also

- [AGENTS.md](../AGENTS.md) — contributor load order and coordination
- [dev-workflow.md](dev-workflow.md) — executing roadmap items (consumer repos)
- [git-workflow.md](git-workflow.md) — consumer git contract
