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

For roadmap-linked implementation in this repo, read [`docs/git-workflow.md`](docs/git-workflow.md) and register in [`tests/fixtures/specy_road_dogfood/roadmap/registry.yaml`](tests/fixtures/specy_road_dogfood/roadmap/registry.yaml) (first commit on `feature/rm-<codename>`).

If this repository ran **`specyrd init`**, you may have slash-command stubs under `.cursor/commands/`, `.claude/commands/`, or a custom directory — they delegate to `specy-road` / bundled scripts.
