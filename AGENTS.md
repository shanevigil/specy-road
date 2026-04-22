# AGENTS — specy-road toolkit repository

**This file is for contributors working on the `specy-road` package.** If you are building an **application** with specy-road, use the `AGENTS.md` created by `specy-road init project` in your repo instead.

Root `constitution/` here describes the **toolkit**; consumer application repos get their own scaffold from `specy-road init project` (see [`specy_road/templates/project/`](specy_road/templates/project/)).

## Load order (keep context small)

1. [`constitution/purpose.md`](constitution/purpose.md) — if present at repo root; else see template under [`specy_road/templates/project/`](specy_road/templates/project/)
2. [`constitution/principles.md`](constitution/principles.md)
3. [`constraints/README.md`](constraints/README.md) — limits for **this** repo (package + tests)
4. [`docs/supply-chain-security.md`](docs/supply-chain-security.md) — dependency verification policy and CI mapping
5. Dogfood merged graph — [`tests/fixtures/specy_road_dogfood/roadmap/`](tests/fixtures/specy_road_dogfood/roadmap/) (`manifest.json` + chunk files) for maintainer validation only
6. **[Flat `planning/*.md` feature sheets](tests/fixtures/specy_road_dogfood/planning/README.md)** under the dogfood fixture when relevant (read ancestor sheets for context)
7. [`shared/README.md`](tests/fixtures/specy_road_dogfood/shared/README.md) in the fixture, then only cited contracts

Focused brief (against the dogfood tree):

```bash
specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md --repo-root tests/fixtures/specy_road_dogfood
```

## Coordination

For roadmap-linked implementation in this repo, read [`docs/git-workflow.md`](docs/git-workflow.md) and register in [`tests/fixtures/specy_road_dogfood/roadmap/registry.yaml`](tests/fixtures/specy_road_dogfood/roadmap/registry.yaml) (registration commit on the integration branch, then `feature/rm-<codename>`).

If this repository ran **`specyrd init`**, you may have slash-command stubs under `.cursor/commands/`, `.claude/commands/`, or a custom directory — they delegate to `specy-road` / bundled scripts.

## Cutting a release

When the user asks to publish (RC or final), follow [`docs/release-runbook.md`](docs/release-runbook.md) verbatim. Do **not** improvise. Two examples:

- *"Publish v0.2.0-rc1 to TestPyPI"* → runbook §A (RC flow). Tag form `v0.2.0-rc1`; pyproject `0.2.0rc1`; routes to TestPyPI.
- *"Publish v0.2.0 to PyPI"* → runbook §B (final flow). Tag form `v0.2.0`; pyproject `0.2.0`; routes to PyPI; back-merge to `dev` is mandatory.

The user owns two steps explicitly (runbook §2 matrix): the **manual tag re-push** that fires `release-publish.yml` (footgun ④ — GitHub policy), and the **final live-on-(Test)PyPI confirmation**. The agent prints the exact commands and waits.
