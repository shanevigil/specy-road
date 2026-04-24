# specy-road (local agent guide)

This repo is the **specy-road toolkit** (Python package + validators + optional PM UI). Consumer application repos use `specy-road init project` for their own `roadmap/`, `constitution/`, and `shared/`.

## Start here (required load order)

Read [`AGENTS.md`](AGENTS.md) first.

For toolkit work, keep context small:

- [`constitution/purpose.md`](constitution/purpose.md)
- [`constitution/principles.md`](constitution/principles.md)
- [`constraints/README.md`](constraints/README.md)
- **Dogfood test fixture:** [`tests/fixtures/specy_road_dogfood/roadmap/`](tests/fixtures/specy_road_dogfood/roadmap/) — validation/sample data only, not the canonical toolkit product roadmap
- **[Feature sheets under `planning/`](tests/fixtures/specy_road_dogfood/planning/README.md)** (flat `planning/*.md` in the dogfood fixture) when validating or updating fixture data
- [`tests/fixtures/specy_road_dogfood/shared/README.md`](tests/fixtures/specy_road_dogfood/shared/README.md), then cited contracts only, when working on fixture behavior

## Roadmap model

- **Dogfood fixture graph:** `manifest.json` + JSON chunks under `roadmap/` inside the fixture tree.
- **Fixture registry:** `roadmap/registry.yaml` in that same tree; use it only for fixture/sample coordination.
- **Generated fixture index:** `roadmap.md` next to the graph (`specy-road export --repo-root tests/fixtures/specy_road_dogfood`).
- **Toolkit product roadmap:** intentionally not defined yet.

Brief:

```bash
specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md --repo-root tests/fixtures/specy_road_dogfood
```

## Non-negotiables

- **Docs win** — prefer tracked repo docs over chat.
- **No scope creep** — smallest change that satisfies the task.
- **Reuse** — extend `specy_road/bundled_scripts/` and tests before adding new entrypoints.
- **Roadmap-linked fixture work** — [`docs/git-workflow.md`](docs/git-workflow.md) and registry under the dogfood path only when the task is specifically about the fixture.

## Maintainer hygiene

- **Adoption prompts** — [`suggested_prompts/`](suggested_prompts/) copy-paste prompts must stay aligned with real formats (templates under `specy_road/templates/project/`, JSON schemas, validators, `docs/roadmap-authoring.md`). When you make a **significant** change to roadmap/graph shape, registry rules, `init project` layout, or other specy-road formats that those prompts describe, update the affected `suggested_prompts/*.md` in the same change set or immediately after.

- **Release / tag parity** — Before any promotion PR to `main` (`release: v…`), bump [`pyproject.toml`](pyproject.toml) `project.version`, add or extend the matching `## [v…]` section in [`CHANGELOG.md`](CHANGELOG.md), and keep any maintainer-facing text that cites the current toolkit version in sync. The tag that CI creates must match that `project.version` (see [`scripts/check_release_version.py`](scripts/check_release_version.py) in [`.github/workflows/release-publish.yml`](.github/workflows/release-publish.yml)). `specyrd init` stubs and `.specyrd/manifest.json` (`specyrd_version`) read runtime `specy_road.__version__` (checkout prefers `pyproject.toml`; wheel installs use package metadata). If they look wrong, fix `project.version` or reinstall, not template placeholders.

## Common commands (maintainers)

```bash
specy-road validate --repo-root tests/fixtures/specy_road_dogfood
specy-road export --check --repo-root tests/fixtures/specy_road_dogfood
specy-road file-limits
pytest
```

**PM Gantt UI** ([`gui/pm-gantt/`](gui/pm-gantt/)): after changing React/TypeScript, from that directory run `npm ci && npm run lint && npm test && npm run build` (same sequence as [`.github/workflows/validate.yml`](.github/workflows/validate.yml); see [`docs/setup.md`](docs/setup.md#dependency-and-security-checks)). Lint uses **ESLint 10** with [`@eslint-react/eslint-plugin`](https://www.npmjs.com/package/@eslint-react/eslint-plugin) in [`gui/pm-gantt/eslint.config.js`](gui/pm-gantt/eslint.config.js) — not `eslint-plugin-react-hooks` (incompatible peers with ESLint 10).

## Where to look

- [`AGENTS.md`](AGENTS.md) — entry and coordination
- [`README.md`](README.md) — install (`pip install` vs editable), `init project`, layout
- [`docs/git-workflow.md`](docs/git-workflow.md) — branches and registry
- [`docs/toolkit-development.md`](docs/toolkit-development.md#maintainer-workflow-vs-consumer-workflow) — maintainer workflow, including the `WIP/improvements-x-y-z` batch line

## Repository git workflow policy (current)

- **Working integration branch:** `dev`
- **Release branch:** `main` (promotion only)
- **Default branch:** `main` (protected)

### Branching model

- Use `WIP/improvements-x-y-z` as the temporary batch branch for collecting
  the next set of improvements toward release or release-candidate `x.y.z`.
  Keep individual changes on short-lived topic branches, then merge them into
  the WIP branch for integration before promoting through `dev`.
- **Topic branch base:** When that batch line is active, **start new topic
  branches from the WIP** (`git checkout WIP/improvements-x-y-z`, `git pull`,
  then `git checkout -b feature/<slug>` and so on) so each branch includes the
  same integration and docs that the rest of the batch is built on. When there
  is no active WIP for your work, start from `dev` instead. This is also stated
  in `AGENTS.md` under Coordination.
- Do day-to-day work on short-lived topic branches, for example:
  - `feature/<slug>` for net-new features
  - `chore/<slug>` for maintenance/tooling/refactors
  - `fix/<slug>` or `hotfix/<slug>` for bug fixes/patches
  - `docs/<slug>` for documentation-only updates
- Prefer opening PRs from topic branches into `dev`, or into the WIP when that
  is the agreed integration line for the current release train.
- Avoid direct commits to `dev` or `main` unless explicitly requested by a maintainer for one-off repository administration.

### Promotion model

- Normal flow is: `topic branch` -> PR -> `dev`.
- Promotion flow is: `dev` -> PR -> `main`.
- Treat `main` as release-facing: it should move via promotion PRs, not via routine feature commits.

### Release tag requirement for `main`

- A PR targeting `main` must declare exactly one release marker:
  - PR title contains `release: x.x.x`, or
  - PR has label `release:x.x.x`
- Tag format is strict semantic version `x.x.x`.
- Meaning:
  - first `x`: major/breaking or major directional shift
  - second `x`: planned improvements/features
  - third `x`: patches/hotfixes
- The `Main Release Tag Gate` workflow validates the marker, and a post-merge automation step creates the matching tag on the merged `main` commit.
