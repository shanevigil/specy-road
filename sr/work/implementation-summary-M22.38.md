# Implementation summary: M22.38 — doctor --fix never removes a claim that may belong to another clone

Branch `feature/rm-doctor-fix-keeps-other-clones-claims`. Base `69385552aa01502b48b49947900477651e9b1132`.

## Summary

`doctor --fix` was offering to delete every registry row whose branch is in neither this clone nor the remote. That row is another clone's live claim until that clone pushes. The row stays in the report, `--fix` leaves it, and the report names `specy-road registry-prune --remove <CODENAME>` plus what to confirm first. A row whose leaf is Complete is still removed through `registry-prune --remove`.

## Changes

- `specy_road/bundled_scripts/doctor.py`: a no-branch row is listed with `remove` unset. Its reason is advisory (another clone's claim looks the same until it pushes), says to confirm that clone no longer holds the claim, names `specy-road registry-prune --remove <codename>`, and ends with `so --fix leaves it`. The registry section heading names the same command. A Complete leaf is classified first, so it is still removed when its branch is also gone. The module docstring, the command description and `--fix` help say the same.
- `tests/test_doctor.py`: the existing dry-run and `--fix --yes` CLI tests cover both rows. `ghost` (no branch) stays in the registry and the report names `registry-prune`. `settled` (leaf Complete) is still removed.
- `CHANGELOG.md`: one `[Unreleased]` Fixed entry. The fix round adds that the same rule is in the git-workflow doctor section, the `doctor` usage line, and the finish stub.
- Fix round 1 (block on current operator text, `gpt-5.6-sol-high`): one rule everywhere that text is current. `--fix` leaves a registry row whose branch is in neither this clone nor the remote and whose leaf is not Complete, and names `specy-road registry-prune --remove <CODENAME>` after the confirm-the-other-clone check. A Complete leaf's row is still removed.
- Fix round 2 (block on a Complete row whose branch is gone, `gpt-5.6-sol-high`): the report says that branch is listed above only when the branch is in this clone or on the remote. `_COMPLETE_REASON` picks the sentence. A Complete row is still removed. The same limit is in the module docstring, `--fix` help, `docs/git-workflow.md`, the usage line, and the finish stub. `test_fix_removes_what_it_listed_and_reports_each` adds a Complete row `buried` with no branch and asserts `--fix --yes` removes it and does not say the branch is listed above. Merged `origin/WIP/improvements-0-3-1` first, with no conflicts.

## Touch zones (final)

- `specy_road/bundled_scripts/doctor.py`
- `tests/test_doctor.py`
- `CHANGELOG.md`

No zone added. The review required `docs/git-workflow.md`, which is outside these zones; the same false sentence was in the usage line and the finish stub, so those two were corrected with it. Call sites outside the zones do not assert that `--fix` deletes a no-branch registry row.

## Verification

- `python -m pytest -n 4 -p no:cacheprovider -q tests/test_doctor.py tests/test_doctor_live.py tests/test_gate_config_agree.py tests/test_nested_unpushed_report.py tests/test_worker_resume_permissions.py tests/test_cli_help_text.py` — 190 passed after fix round 2.
- `ruff check specy_road tests scripts` — clean. `_registry_findings` McCabe stays 7, the same as `origin/WIP/improvements-0-3-1`. No function in `doctor.py` is more complex than at that merge base.
- `specy-road file-limits` — exit 0 (`OK: file limits satisfied`; existing hard-alert warnings on unrelated files).

## Probes

- `_registry_findings` — a Complete codename in `detect_stale_claims` (no local or remote branch) uses "leaf Complete" and is still removed; one whose branch exists uses "listed above". McCabe 7, same as the merge base.
- `docs/git-workflow.md` doctor bullet and `--fix` paragraph — a Complete row whose branch is gone is not documented as listed above, and is still removed; a non-Complete no-branch row is left.
- `specy_road/cli_usage.py`, the finish stub, and `--fix` help — they said every no-branch row is left; they now leave only a non-Complete one.
- `tests/test_doctor.py` settled line — still expects "listed above" because `feature/rm-settled` exists; `buried` covers the gone branch.
- `CHANGELOG.md` released lock note, `docs/design-notes/`, `sr/docs/research/`, and other "listed above" sentences (finish step 5, refresh-stubs) — not this report; left as history.
- `docs/git-workflow.md` doctor section (round 1) — the blocked text said `--fix` removes listed registry rows through `registry-prune --remove`; the bullet, the `--fix` paragraph, and the example comment now leave a non-Complete no-branch row and still remove a Complete one.
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

- `_COMPLETE_REASON` — the two Complete-row sentences, so "listed above" is chosen by whether the branch exists without a new branch in `_registry_findings`.

### Branches or guards

- `_registry_findings` checks a Complete codename before a no-branch one, and a no-branch row gets `remove=None` — `--fix` must not delete a claim another clone may hold, and a Complete leaf is still removed when its branch is also missing.

### Mocks

- none

### Tests

- none (extended `test_fix_removes_what_it_listed_and_reports_each` so a Complete row with no branch is removed through `doctor.main` and is not reported as listed above)
