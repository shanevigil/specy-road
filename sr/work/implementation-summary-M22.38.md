# Implementation summary: M22.38 — doctor --fix never removes a claim that may belong to another clone

Branch `feature/rm-doctor-fix-keeps-other-clones-claims`. Base `69385552aa01502b48b49947900477651e9b1132`.

## Summary

`doctor --fix` was offering to delete every registry row whose branch is in neither this clone nor the remote. That row is another clone's live claim until that clone pushes. The row stays in the report, `--fix` leaves it, and the report names `specy-road registry-prune --remove <CODENAME>` plus what to confirm first. A row whose leaf is Complete is still removed through `registry-prune --remove`.

## Changes

- `specy_road/bundled_scripts/doctor.py`: a no-branch row is listed with `remove` unset. Its reason is advisory (another clone's claim looks the same until it pushes), says to confirm that clone no longer holds the claim, names `specy-road registry-prune --remove <codename>`, and ends with `so --fix leaves it`. The registry section heading names the same command. A Complete leaf is classified first, so it is still removed when its branch is also gone. The module docstring, the command description and `--fix` help say the same.
- `tests/test_doctor.py`: the existing dry-run and `--fix --yes` CLI tests cover both rows. `ghost` (no branch) stays in the registry and the report names `registry-prune`. `settled` (leaf Complete) is still removed.
- `CHANGELOG.md`: one `[Unreleased]` Fixed entry. The fix round adds that the same rule is in the git-workflow doctor section, the `doctor` usage line, and the finish stub.
- Fix round 1 (block on current operator text, `gpt-5.6-sol-high`): one rule everywhere that text is current. `--fix` leaves a registry row whose branch is in neither this clone nor the remote and names `specy-road registry-prune --remove <CODENAME>` after the confirm-the-other-clone check; a Complete leaf's row is still removed. Applied in `docs/git-workflow.md` (the registry bullet, the `--fix` paragraph, and the example comment), `specy_road/cli_usage.py`, and `specy_road/templates/specyrd/commands/specyrd-finish.md`. Merged `origin/WIP/improvements-0-3-1` first, with no conflicts.

## Touch zones (final)

- `specy_road/bundled_scripts/doctor.py`
- `tests/test_doctor.py`
- `CHANGELOG.md`

No zone added. The review required `docs/git-workflow.md`, which is outside these zones; the same false sentence was in the usage line and the finish stub, so those two were corrected with it. Call sites outside the zones do not assert that `--fix` deletes a no-branch registry row.

## Verification

- `python -m pytest -n 4 -p no:cacheprovider -q tests/test_doctor.py tests/test_doctor_live.py tests/test_gate_config_agree.py tests/test_nested_unpushed_report.py tests/test_worker_resume_permissions.py` — 115 passed (re-run after the fix round).
- `ruff check specy_road tests scripts` — clean. This round did not change `doctor.py`, so no function grew past its complexity at the merge base.
- `specy-road file-limits` — exit 0 (`OK: file limits satisfied`; existing hard-alert warnings on unrelated files).

## Probes

- `docs/git-workflow.md` doctor section — the blocked text said `--fix` removes listed registry rows through `registry-prune --remove`; the bullet, the `--fix` paragraph, and the example comment now leave a no-branch row and still remove a Complete one.
- `specy_road/cli_usage.py` `doctor` lines — `(--fix removes them` covered the no-branch row in that list; it now says `--fix` leaves those rows for `registry-prune --remove` and removes the rest.
- `specy_road/templates/specyrd/commands/specyrd-finish.md` — `--fix` removes them followed a list that included no-branch rows; it now excepts that row.
- `docs/dev-workflow.md`, the other `docs/orchestration-*.md` pages, `suggested_prompts/`, and `README.md` — no current sentence that says `doctor --fix` removes a no-branch registry row.
- `CHANGELOG.md` released note that `doctor --fix` for registry rows takes the repository lock — past tense, still true for a Complete row; left as history.
- `docs/design-notes/` and `sr/docs/research/` — historical notes that doctor lists registry rows, not that `--fix` removes a no-branch one; left as history.
- `specy_road/bundled_scripts/doctor.py` docstring, description, `--fix` help, and the registry report — already state the leave rule; unchanged this round.

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

- none (extended `test_dry_run_lists_every_kind_and_changes_nothing` and `test_fix_removes_what_it_listed_and_reports_each` so both row kinds stay covered through `doctor.main`; the fix round added no test)
