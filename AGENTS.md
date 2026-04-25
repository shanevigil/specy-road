# AGENTS — specy-road toolkit repository

**This file is for contributors working on the `specy-road` package.** If you are building an **application** with specy-road, use the `AGENTS.md` created by `specy-road init project` in your repo instead.

Root `constitution/` here describes the **toolkit**; consumer application repos get their own scaffold from `specy-road init project` (see [`specy_road/templates/project/`](specy_road/templates/project/)).

## Load order (keep context small)

1. [`constitution/purpose.md`](constitution/purpose.md) — if present at repo root; else see template under [`specy_road/templates/project/`](specy_road/templates/project/)
2. [`constitution/principles.md`](constitution/principles.md)
3. [`constraints/README.md`](constraints/README.md) — limits for **this** repo (package + tests)
4. [`docs/supply-chain-security.md`](docs/supply-chain-security.md) — dependency verification policy and CI mapping
5. Dogfood test-fixture graph — [`tests/fixtures/specy_road_dogfood/roadmap/`](tests/fixtures/specy_road_dogfood/roadmap/) (`manifest.json` + chunk files) for validation, fixtures, and CLI dogfooding only
6. **[Flat `planning/*.md` feature sheets](tests/fixtures/specy_road_dogfood/planning/README.md)** under the dogfood test fixture when validating or updating fixture data
7. [`shared/README.md`](tests/fixtures/specy_road_dogfood/shared/README.md) in the fixture, then only cited contracts, when working on fixture behavior

Focused brief (against the dogfood test fixture):

```bash
specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md --repo-root tests/fixtures/specy_road_dogfood
```

## Coordination

The dogfood tree is a **test-fixture roadmap**, not the canonical product roadmap for the `specy-road` toolkit. Do not register ordinary toolkit implementation work in [`tests/fixtures/specy_road_dogfood/roadmap/registry.yaml`](tests/fixtures/specy_road_dogfood/roadmap/registry.yaml) unless the work is specifically exercising or updating the fixture.

**Toolkit branch base:** `dev` is the day-to-day integration branch. When maintainers are batching work on an active `WIP/improvements-x-y-z` line toward a release or release candidate, **create your short-lived topic branch from that WIP branch** (sync with `git fetch` first, check out the WIP, `git pull`, then `git checkout -b feature/<slug>` or equivalent)—not from `dev` in isolation, so the branch already contains WIP-only integration and docs. If there is no such active WIP for your change, branch from `dev`. The same policy is spelled out in [`docs/toolkit-development.md`](docs/toolkit-development.md#maintainer-workflow-vs-consumer-workflow), `CLAUDE.md` (Repository git workflow), and (for Cursor) [`.cursor/rules/030-git-workflow-management.mdc`](.cursor/rules/030-git-workflow-management.mdc).

For the consumer-repo contract and registry, read [`docs/git-workflow.md`](docs/git-workflow.md). A first-class roadmap for the toolkit itself is intentionally not defined here yet.

If this repository ran **`specyrd init`**, you may have slash-command stubs under `.cursor/commands/`, `.claude/commands/`, or a custom directory — they delegate to `specy-road` / bundled scripts.

## Cutting a release

When the user asks to publish (RC or final), follow [`docs/release-runbook.md`](docs/release-runbook.md) verbatim. Do **not** improvise. Two examples:

- *"Publish v0.2.0-rc1 to TestPyPI"* → runbook §A (RC flow). Tag form `v0.2.0-rc1`; pyproject `0.2.0rc1`; routes to TestPyPI.
- *"Publish v0.2.0 to PyPI"* → runbook §B (final flow). Tag form `v0.2.0`; pyproject `0.2.0`; routes to PyPI; back-merge to `dev` is mandatory.

The user owns two steps explicitly (runbook §2 matrix): the **manual tag re-push** that fires `release-publish.yml` (footgun ④ — GitHub policy), and the **final live-on-(Test)PyPI confirmation**. The agent prints the exact commands and waits.
