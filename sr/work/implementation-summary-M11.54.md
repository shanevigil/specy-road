# Implementation summary — M11.54 (`parallel-test-suite`)

## Scope

Parallelize the toolkit test gate: development dependency, CI, maintainer docs, and `sr/roadmap/git-workflow.yaml` `land_check_cmd`.

## Touch zones (confirmed)

`pyproject.toml`, `.github/workflows/validate.yml`, `sr/roadmap/git-workflow.yaml`, `docs/git-workflow.md`, `docs/contributor-guide.md`, `CLAUDE.md`, `tests/` — no additions or removals; all changes stayed in the first six paths (no test code changes required).

## Acceptance

- **A1:** Added `pytest-xdist>=3.0` to `[project.optional-dependencies] dev`. CI step runs `pytest -n auto`. Full suite: `3169 passed, 2 skipped` with `-n auto` (~3.6 min) and serially (~21 min); no order-dependent failures observed.
- **A2:** Expanded `docs/git-workflow.md` `land_check_cmd` with parallel-safe criteria, recommendation, and YAML example. Contributor guide quickstart and Local CI parity use `pytest -n auto` (with `-q` where the block already used quiet). `CLAUDE.md` common commands use `pytest -n auto`.
- **A3:** `sr/roadmap/git-workflow.yaml` sets `land_check_cmd: pytest -n auto`.

## Verifiers run

- `pytest -n auto -q` → exit 0
- `pytest -q` (serial) → exit 0
- `specy-road file-limits` → exit 0

## Added

none
