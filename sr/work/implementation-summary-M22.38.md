# Implementation summary: M22.38 — doctor --fix never removes a claim that may belong to another clone

Branch `feature/rm-doctor-fix-keeps-other-clones-claims`. Base `69385552aa01502b48b49947900477651e9b1132`.

## Summary

`doctor --fix` was offering to delete every registry row whose branch is in neither this clone nor the remote. That row is another clone's live claim until that clone pushes. The row stays in the report, `--fix` leaves it, and the report names `specy-road registry-prune --remove <CODENAME>` plus what to confirm first. A row whose leaf is Complete is still removed through `registry-prune --remove`.

## Changes

- `specy_road/bundled_scripts/doctor.py`: a no-branch row is listed with `remove` unset. Its reason is advisory (another clone's claim looks the same until it pushes), says to confirm that clone no longer holds the claim, names `specy-road registry-prune --remove <codename>`, and ends with `so --fix leaves it`. The registry section heading names the same command. A Complete leaf is classified first, so it is still removed when its branch is also gone. The module docstring, the command description and `--fix` help say the same.
- `tests/test_doctor.py`: the existing dry-run and `--fix --yes` CLI tests cover both rows. `ghost` (no branch) stays in the registry and the report names `registry-prune`. `settled` (leaf Complete) is still removed.
- `CHANGELOG.md`: one `[Unreleased]` Fixed entry.

## Touch zones (final)

- `specy_road/bundled_scripts/doctor.py`
- `tests/test_doctor.py`
- `CHANGELOG.md`

No zone added or removed. Call sites outside the zones (`tests/test_doctor_live.py`, `tests/test_gate_config_agree.py`, `tests/test_nested_unpushed_report.py`, `tests/test_worker_resume_permissions.py`) do not assert that `--fix` deletes a no-branch registry row. `docs/git-workflow.md` still describes `--fix` as removing listed registry rows; that sentence was already broader than the rows `--fix` deletes (it already leaves some listed worktrees), and A2 is met by the doctor report naming `registry-prune`.

## Verification

- `python -m pytest -n 4 -p no:cacheprovider -q tests/test_doctor.py tests/test_doctor_live.py tests/test_gate_config_agree.py tests/test_nested_unpushed_report.py tests/test_worker_resume_permissions.py` — 115 passed.
- `ruff check specy_road/bundled_scripts/doctor.py tests/test_doctor.py` — clean.
- `specy-road file-limits` — exit 0 (`OK: file limits satisfied`; existing hard-alert warnings on unrelated files).

## Walkthrough

1. Dry-run `specy-road doctor` on a repo with a registry row whose branch is in neither this clone nor the remote. The registry section lists it as advisory, says to confirm the other clone no longer holds the claim, and names `specy-road registry-prune --remove <CODENAME>`.
2. `specy-road doctor --fix --yes` prints `[kept]` for that row and leaves it in the registry. A row whose leaf is Complete still prints `[ok] removed registry row`.

## Added

### Helpers

- none

### Branches or guards

- `_registry_findings` checks a Complete codename before a no-branch one, and a no-branch row gets `remove=None` — `--fix` must not delete a claim another clone may hold, and a Complete leaf is still removed when its branch is also missing.

### Mocks

- none

### Tests

- none (extended `test_dry_run_lists_every_kind_and_changes_nothing` and `test_fix_removes_what_it_listed_and_reports_each` so both row kinds stay covered through `doctor.main`)
