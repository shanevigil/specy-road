# Implementation summary: M11.64 — abort-task-pickup treats untracked files the way pickup does

## What changed

`abort-task-pickup` used to refuse on every porcelain entry except an allow-list
of specy-road bookkeeping paths (this leaf's brief/prompt/summary/session file,
and another leaf's brief/summary/prompt/reviews/runtime dirs). Any other
untracked file, such as a coordinator's notes under `work/`, made it refuse with
"working tree is not clean (commit, stash, or discard changes first)". Pickup
refuses on nothing under `work/`, so the two commands disagreed over the same
tree, and the error suggested a stash, which the project rules forbid.

Now (`specy_road/bundled_scripts/abort_task_pickup.py`):

- The check reads `git status --porcelain --untracked-files=no`: **untracked
  files never block** (anywhere — they survive the branch switch abort makes;
  this accepts everything pickup accepts). **Tracked changes block**, staged or
  unstaged, including under `work/`: the checkout would carry them to the
  integration branch or stop on them, and the `--local` reset would discard them.
- The refusal names each blocking path with why: `src/app.py (unstaged edit)`,
  `x (staged edit, unstaged edit)`, `y (unmerged (conflict))`, and says which
  branch abort checks out. It suggests commit or discard, never stash.
- Because untracked files no longer block up front, git itself can refuse the
  checkout when an untracked file sits where the integration branch tracks one.
  `_checkout_base` turns that into a clean exit 1 with a hint (git's own message,
  printed above it, names the paths) instead of a `CalledProcessError` traceback.
  It replaces the bare `git checkout <base>` in `_sync_integration_branch_ff` and
  `_drop_local_registration`.

Order of operations is unchanged: the check still runs before any git state
changes (before fetch and the base-held-elsewhere check).

## Interpretation note

A1 says "refuses only on tracked changes". Pickup's own rule (`except_work=True`
in `repo_ops`) ignores *all* of `work/`, tracked or not, but refuses untracked
files outside `work/`. I followed A1: untracked files outside `work/` are also
accepted (git protects them on checkout), and a tracked change under `work/`
still blocks (abort's checkout/reset would carry or discard it, and abort then
deletes this leaf's brief). If the maintainer wants pickup's rule verbatim
instead, that is a one-line pathspec change in `_tracked_changes`.

## Touch zones (final)

Confirmed as listed: `specy_road/bundled_scripts/abort_task_pickup.py`, `tests/`
(`tests/test_abort_task_pickup.py`, `tests/test_prerelease_apps.py`). No new
module; the file went from 372 to 363 lines.

## Verification

- `python -m pytest tests/test_abort_task_pickup.py tests/test_prerelease_apps.py tests/test_prerelease_s5.py tests/test_cli.py tests/test_lean_gates.py -q` — 45 passed, 2 skipped
- `python scripts/check_test_private_imports.py` — 0 new
- `specy-road file-limits` — OK
- `python -m pytest -n auto -q` — full suite, three runs. First: 1 failed (`test_lean_gates.py::test_private_imports_pass_on_committed_baseline`, my new tests named private helpers; fixed by testing through `main()`). Second and third: 3320 passed, 2 skipped, 1 failed — `tests/test_worker_queue_message.py::test_message_while_running_queues_and_delivers` (`'running' == 'idle'`: it reads the record right after the second completion event, before the state flips). Unrelated and pre-existing: it fails the same way under `-n auto tests/test_worker_*.py` with the **base** `abort_task_pickup.py`, passed in the first full run, and passes 3/3 alone. Not touched here; it is outside this leaf.
- `python -m pytest -n auto -q tests/test_worker_*.py` — 205 passed with the fix
- Red-green: with the old `abort_task_pickup.py`, the extended e2e test
  `tests/test_prerelease_apps.py -k abort_of_a_local` fails with exactly the field
  error (`working tree is not clean ... ?? work/coordinator-notes.md`); with the
  fix it passes.

## Added

- `_STAGED` / `_UNSTAGED` maps: porcelain status letters to the reason shown per blocking path (A1 "names … why").
- `_why_blocking(xy)`: one reason string per porcelain entry, conflicts called out as unmerged.
- `_tracked_changes()`: the new clean-tree rule, tracked changes only (replaces `_dirty_entries`, `_OTHER_BOOKKEEPING` and `_pickup_artifact_rel_paths`, now unneeded and removed).
- `_assert_no_tracked_changes(base)`: the refusal, naming paths, reasons and the branch abort would check out; no stash advice (replaces `_assert_working_tree_clean`).
- `_checkout_base(base)` guard: clean exit 1 when git refuses the checkout over an untracked file the base tracks, which can now reach that point.
- Test helpers `_git`, `_repo(tmp_path)` (a real git repo with one tracked file, so the rule runs against real `git status`) and `_refusal` (runs `main`, asserts exit 1, returns stderr). All new tests go through `main()` and public names only, because `tests/test_lean_gates.py` fails on new private references and its baseline may not be widened.
- `_PastTheCheck` test exception: raised from a mocked `git_run` at `fetch` to prove `main` got past the clean-tree check without touching a remote.
- `test_abort_refuses_tracked_change_naming_path_and_why`: tracked change refuses, names `src/app.py (unstaged edit)`, then `(staged edit, unstaged edit)`; no stash advice.
- `test_untracked_files_do_not_block_abort`: untracked coordinator notes and pickup's brief under `work/`, plus an untracked file outside it, let `main` reach `git fetch`; the notes are still there. Replaces `test_pickup_artifacts_do_not_block_abort` and `test_dirty_entries_filters_only_the_listed_untracked_paths`, whose functions were removed (the latter asserted the old behaviour A1 changes: `?? work/notes.txt` blocking).
- `test_tracked_change_under_work_still_blocks`: a staged new file under `work/` still blocks.
- `test_abort_names_a_conflicted_path`: a real merge conflict is reported as `unmerged (conflict)`.
- `test_refused_checkout_of_the_base_exits_with_a_message`: `git_run` mocked to fail on `checkout`; asserts exit 1 and the hint.
- `tests/test_prerelease_apps.py`: the e2e local-pickup abort now also has an untracked `work/coordinator-notes.md` and asserts it survives the abort.
- Removed the `_dirty_entries` mocks from the four existing `main` tests in `tests/test_abort_task_pickup.py`: they either exit before the check or already mock `git_capture` to an empty status.

## Outside the touch zones (not changed)

`constraints/test-private-imports-baseline.txt` now has two stale entries
(`abort_task_pickup._dirty_entries`, `abort_task_pickup._pickup_artifact_rel_paths`).
Stale entries are reported, not failed, by `scripts/check_test_private_imports.py`;
pruning them is a one-line follow-up for whoever owns `constraints/`.
