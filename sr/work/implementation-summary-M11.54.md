# Implementation summary — M11.54 (`parallel-test-suite`)

## Scope

Parallelize the toolkit test gate: development dependency, CI, maintainer docs, and `sr/roadmap/git-workflow.yaml` `land_check_cmd`.

## Touch zones (confirmed)

`pyproject.toml`, `.github/workflows/validate.yml`, `sr/roadmap/git-workflow.yaml`, `docs/git-workflow.md`, `docs/contributor-guide.md`, `CLAUDE.md`, `tests/` — no zones added or removed. Review fix also edits `tests/test_contract_citations.py` (cwd-relative template path).

## Acceptance

- **A1:** Added `pytest-xdist>=3.0` to `[project.optional-dependencies] dev`. CI step runs `pytest -n auto`. Full suite: `3169 passed, 2 skipped` with `-n auto` (~3.6 min) and serially (~21 min); no order-dependent failures observed.
- **A2:** Expanded `docs/git-workflow.md` `land_check_cmd` with parallel-safe criteria, recommendation, and YAML example. Contributor guide quickstart and Local CI parity use `pytest -n auto` (with `-q` where the block already used quiet). `CLAUDE.md` common commands use `pytest -n auto`.
- **A3:** `sr/roadmap/git-workflow.yaml` sets `land_check_cmd: python -m pytest -n auto -p no:cacheprovider ../tests` so finish's cwd (`sr/`) collects git-root tests. From `sr/`: 3171 collected, 3169 passed, 2 skipped.

## Verifiers run

- `pytest -n auto -q` (git root) → exit 0
- `pytest -q` (serial, git root) → exit 0
- `python -m pytest -n auto -p no:cacheprovider ../tests` (cwd `sr/`, before template-path fix) → exit 1
- `python -m pytest -n auto -p no:cacheprovider ../tests` (cwd `sr/`, after fix) → exit 0
- `specy-road file-limits` → exit 0

## Added

- Path via `__file__` in `test_shipped_planning_templates_cite_nothing_by_themselves`: the nested land-check cwd is `sr/`, so a cwd-relative `specy_road/templates/...` missed the shipped templates.
