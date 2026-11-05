# Implementation summary: M13.8

## Scope (split maintainer 2026-11-04, WIP 25ffc3d1)

This leaf now covers **A1** (behaviour-change catalogue), **A2** (`version_pin` move + validate re-export), and **A3** (pickup `--base` stale-registration pattern + `docs/roadmap-authoring.md` rewrite). Project-text **validate notices** moved to **M13.14**.

## Touch zones

`specy_road/behaviour_changes.py`, `specy_road/version_pin.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `tests/`, `docs/roadmap-authoring.md`.

## Removed for M13.14

Deleted `specy_road/agent_text_report.py` and its `validate_at` hook; removed lint tests from `tests/test_behaviour_changes.py`. **M13.14** can reuse the full lint implementation from commit **`aba60158`** on this branch history (`warn_contradicted_instructions`, mandate cues, per-line directives).

## What remains

- **`behaviour_changes.py`:** five-entry `CATALOGUE` with `contradicts` / `current` / mandate cues (for M13.14 to consume).
- **`version_pin.py`:** `pinned_version`, `warn_if_pin_differs`; re-exported from `validate_roadmap`.
- **`docs/roadmap-authoring.md`:** integration-branch registration before feature branch (400 lines).

## Verification

- `python -m pytest -n 4 -q tests/test_behaviour_changes.py tests/test_validate_roadmap.py tests/test_validate_stale_commands.py` — 44 passed
- `ruff check specy_road tests scripts` — OK
- `specy-road file-limits` — OK

## Added

### Helpers
- none (this scope change removes code)

### Branches and guards
- none

### Mocks
- none

### Tests
- `test_every_entry_names_a_registered_command_and_flag` — A1
- `test_toolkit_docs_and_templates_do_not_say_the_first_commit_registers_the_work` — A3 pattern scan
