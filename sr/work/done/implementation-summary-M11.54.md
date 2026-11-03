# Implementation summary — M11.54 (`parallel-test-suite`)

## Scope

Parallelize the toolkit test gate: development dependency, CI, maintainer docs, and `sr/roadmap/git-workflow.yaml` `land_check_cmd`.

## Touch zones (confirmed)

`pyproject.toml`, `.github/workflows/validate.yml`, `sr/roadmap/git-workflow.yaml`, `docs/git-workflow.md`, `docs/contributor-guide.md`, `CLAUDE.md`, `tests/`, `requirements-ci.in`, `requirements-ci.txt`. Review later added the lock files so CI's frozen install includes xdist. `requirements-ci.in` stays `-e .[dev]` (CI deps are declared in the `dev` extra); `pip-compile requirements-ci.in -o requirements-ci.txt` on Python 3.12 pinned `pytest-xdist==3.8.0` and `execnet==2.1.2`.

## Acceptance

- **A1:** Added `pytest-xdist>=3.0` to `[project.optional-dependencies] dev`. CI step runs `pytest -n auto`. Frozen lock now includes `pytest-xdist==3.8.0` and `execnet==2.1.2`. Full suite: `3169 passed, 2 skipped` with `-n auto` (~3.6 min) and serially (~21 min); no order-dependent failures observed. A fresh Python 3.12 venv `pip install -r requirements-ci.txt` ran `pytest -n auto --collect-only` (3171 collected) and `pytest -n auto` on one test (pass).
- **A2:** Expanded `docs/git-workflow.md` `land_check_cmd` with parallel-safe criteria, recommendation, and YAML example. Contributor guide quickstart and Local CI parity use `pytest -n auto` (with `-q` where the block already used quiet). `CLAUDE.md` common commands use `pytest -n auto`.
- **A3:** `sr/roadmap/git-workflow.yaml` sets `land_check_cmd: python -m pytest -n auto -p no:cacheprovider ../tests` so finish's cwd (`sr/`) collects git-root tests. From `sr/`: 3171 collected, 3169 passed, 2 skipped.

## Verifiers run

- `pytest -n auto -q` (git root) → exit 0
- `pytest -q` (serial, git root) → exit 0
- `python -m pytest -n auto -p no:cacheprovider ../tests` (cwd `sr/`, before template-path fix) → exit 1
- `python -m pytest -n auto -p no:cacheprovider ../tests` (cwd `sr/`, after fix) → exit 0
- `pip-compile requirements-ci.in -o requirements-ci.txt` (Python 3.12) → exit 0
- fresh venv `pip install -r requirements-ci.txt` then `pytest -n auto --collect-only -q` → exit 0, 3171 collected
- same venv `pytest -n auto -q tests/test_contract_citations.py::test_shipped_planning_templates_cite_nothing_by_themselves` → exit 0
- `specy-road file-limits` → exit 0

## Added

- Path via `__file__` in `test_shipped_planning_templates_cite_nothing_by_themselves`: the nested land-check cwd is `sr/`, so a cwd-relative `specy_road/templates/...` missed the shipped templates.
