# Implementation summary for M3.14

## Summary

A leaf whose planning sheet is still the toolkit's placeholder text is now caught whether or not the node has `acceptance`. M3.1's guard (`planning_sheet_bootstrap.placeholder_sheet`) only skipped such a leaf at pickup when it also had no acceptance.

- **A1:** `finish-this-task` refuses before any bookkeeping when the leaf's sheet still has scaffold-planning's `## Intent` / `## Approach` body or brainstorm promote's "Rewrite this section…" line. The error names the sheet and the section. `--allow-scaffold-planning` is the explicit opt-out, like `mark-implementation-reviewed --allow-missing-summary`. The check runs just before the implementation-review gate, so the opt-out only gets past this gate.
- **A2:** `do-next-available-task` prints `warning: picked <ID>, but <sheet> still has … placeholder under ## <section>` once a leaf is chosen and before it is claimed. This happens even when the node has acceptance, and also when `--allow-unauthored` picked a leaf with none. There is no separate `do-next-task` command: the CLI maps `do-next-available-task` to `do_next_task.py`, and `grind-session --step pickup` calls that CLI, so it gets the warning too.
- **A3:** `specy-road validate` prints one `notice:` line on stdout counting Complete structural leaves whose sheet is still the scaffold, plus a pointer to `--all`. `--all` lists each one with its reason. It goes to stdout, not stderr, so `validate --strict`, which counts stderr lines, does not fail on it. It prints from `validate`'s `main()` only, not from `validate_at`, so `edit-node`, pickup and the other in-process `validate_at` callers stay quiet.

## Changes

- `specy_road/planning_scaffold_check.py` (new): `scaffold_sheet`, `scaffold_planning_or_exit`, `warn_scaffold_at_pickup`, `notice_complete_scaffold`. It reuses `planning_sheet_bootstrap`'s `_section_bodies`, `_scaffold_bodies` and `PROMOTE_PLACEHOLDER` rather than re-deriving the scaffold text. Those are private names, and `planning_sheet_bootstrap.py` is outside the touch zones, so it could not be made to delegate here.
- `specy_road/bundled_scripts/finish_task_args.py`: adds the `--allow-scaffold-planning` flag.
- `specy_road/bundled_scripts/finish_task.py`: calls `scaffold_planning_or_exit` in `_resolve_main_context`, before `_impl_review_or_exit`.
- `specy_road/bundled_scripts/do_next_task.py`: calls `warn_scaffold_at_pickup` in `_pick_node`. The file was at 399 of its 400-line cap, so a two-line comment in `_validate_or_exit` became one line with the same meaning.
- `specy_road/bundled_scripts/validate_roadmap.py`: calls `notice_complete_scaffold` in `main()` and extends the `--all` help text.
- `docs/dev-workflow.md`: adds a paragraph after "Unauthored leaves are skipped" and a precondition in the `finish-this-task` step list.
- Touch zones are confirmed accurate. `finish_implementation_check.py` and `do_next_available.py` needed no change. `docs/git-workflow.md` documents the parallel empty-implementation gate but is outside the zones, so it is not updated.

**Note for whoever finishes this leaf:** M3.14's own sheet (`sr/planning/M3.14_…md`) is still the scaffold and is outside this leaf's touch zones. Under this change, finishing M3.14 is refused until someone writes that sheet or passes `--allow-scaffold-planning`.

## Verification

- `python -m pytest -q`: 2379 passed, 2 skipped.
- `python -m pytest -q tests/test_finish_scaffold_planning.py tests/test_unauthored_leaf_guard.py`: 24 passed.
- `specy-road file-limits`: OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `ruff check` on the changed files: passed.
- `python scripts/check_test_private_imports.py`: 0 new. The one stale baseline entry predates this change.
- `python scripts/check_clones.py --pylint <uv-provided pylint>`: 0 new. pylint is not installed in the repo's env, and the one stale baseline entry predates this change.

## Walkthrough

1. `specy_road/planning_scaffold_check.py`: `scaffold_sheet` is the acceptance-independent detector; the other three functions are its three callers' outputs.
2. `tests/test_finish_scaffold_planning.py`: runs finish on a real repo with a scaffold or promote sheet, with and without the flag. HEAD is unchanged in every case.
3. `tests/test_unauthored_leaf_guard.py`: covers the `scaffold_sheet` cases next to `placeholder_sheet`'s, the pickup warning, and the validate notice through `main()`.

## Added

### Helpers
- `planning_scaffold_check.scaffold_sheet`: the acceptance-independent "is this sheet still the scaffold" check that all three criteria need; `placeholder_sheet` answers a different question (it also requires no acceptance).
- `planning_scaffold_check.scaffold_planning_or_exit`: A1's refusal, kept beside `implementation_or_exit`'s shape so `finish_task.py` gains one call.
- `planning_scaffold_check.warn_scaffold_at_pickup`: A2's pickup warning.
- `planning_scaffold_check.notice_complete_scaffold`: A3's stdout notice and `--all` listing.

### Branches and guards
- `except (OSError, ValueError)` in `scaffold_sheet`: a sheet missing on disk (`OSError`) or a node with no `planning_dir` (`ValueError` from `normalize_planning_dir`) is not this check's finding. `test_missing_sheet_is_not_reported_here` reaches both.
- `--allow-scaffold-planning` flag: the opt-out A1 requires.
- `show_all` branch in `notice_complete_scaffold`: A3's `--all` listing.

### Mocks
- `monkeypatch.setattr("sys.argv", ...)` in `test_validate_notes_complete_leaves_still_on_the_scaffold`: drives `validate`'s `main()`, which parses `sys.argv`.

### Tests
- `tests/test_finish_scaffold_planning.py::test_finish_refuses_an_unwritten_sheet_unless_allowed` (scaffold and promote, with and without the flag): A1's refusal names the sheet, the opt-out passes it, and no bookkeeping happens.
- `tests/test_finish_scaffold_planning.py::test_a_written_sheet_is_not_refused`: a filled sheet does not trip A1.
- `tests/test_unauthored_leaf_guard.py::test_validate_notes_complete_leaves_still_on_the_scaffold` (with and without `--all`): A3.
- Extended, not new: `test_promote_skeleton_is_a_placeholder`, `test_a_leftover_scaffold_approach_is_a_placeholder`, `test_filled_sheet_or_acceptance_is_not_a_placeholder`, `test_missing_sheet_is_not_reported_here` (each `scaffold_sheet` reason, and its `None` cases); `test_filled_sheet_or_acceptance_is_picked_as_before` (A2 warning with acceptance); `test_pickup_skips_an_unauthored_leaf_and_says_why` (no warning when the picked sheet is written).
