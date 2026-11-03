# Implementation summary: `M11.40` — worker reconcile works on merged leaves and separates untracked files

Code commit: `2cca235f` on `feature/rm-reconcile-merged-and-untracked` (base `237da177`).

## What changed

### A1: a merged leaf, and `--dismiss`

- `specy_road/worker_reconcile.py` `_target(repo_root, rec)`: when `resolve_target` fails, the node exists and the registry has
  no claim with a branch for it (the leaf merged and finish released the claim), reconcile now builds a claim-less
  `ReviewTarget` from the roadmap node instead of raising. `ReviewTarget.touch_zones` already falls back to the node's
  `touch_zones` when there is no entry, so the zones come from the roadmap. An unknown node, or a claim whose branch is
  missing, still raises as before.
- With no claim there is no base, so `since` now falls back to `rec.started_head` after the checkpoint and `t.base`.
  Nothing changes for a claimed leaf, because `t.base` is set there.
- `build_prompt` refuses with the same "no registry claim" error, which would always count as a contract change. For a
  claim-less target, reconcile now passes `ref=<the worker's HEAD>`, so roster, role and eligibility checks still run.
  The brief comparison (`_brief_unchanged`) is unchanged.
- `dismiss(repo_root, worker_id, reason)`: under the workers lock it clears `needs_reconcile` and appends a `reconcile`
  event (an existing event type, so no schema change). The event's summary is `needs_reconcile dismissed: <reason>` and its
  detail is `{dismissed, was_flagged, needs_reconcile: false}`. A blank reason is refused. Re-exported from `worker_ops`.
- CLI: `worker reconcile W --dismiss REASON`. The op-id input is bound to the reason.
- `worker list` and `worker sync` read `rec.flags`, so a dismissed worker no longer shows the flag, and neither does a
  reconciled one (reconcile clears the flag when it passes). Nothing calls `reconcile` automatically, so a dismissal holds
  until someone runs `reconcile` again, which judges the tree afresh.

### A2: untracked files reported separately

- `_changed_since` now returns only what the branch's commits and the uncommitted tracked tree changed. A new `_untracked`
  helper lists untracked files (the same `ls-files --others --exclude-standard --full-name -- :(top)` call as before).
- The delta keeps `changed` and `outside_touch_zones` for tracked changes. It adds `untracked`,
  `untracked_outside_touch_zones` (excluding bookkeeping, matched the same way) and `claimed`. Only tracked paths outside
  the zones set `needs_reconcile`. Untracked ones are a warning in the text output
  (`warning: untracked, outside touch zones: <path>`) and in the event summary.
- The text output moved from `worker_cli.cmd_reconcile` into `worker_reconcile.reconcile_lines`. It also says when the
  leaf has no claim. This brings `bundled_scripts/worker_cli.py` from 401 lines (already over the cap at base, after
  the WIP merge) to 394.

### Existing tests updated for A2's behaviour change

These asserted that an untracked file outside the zones is a breach, or that `changed` includes untracked files. A2
reverses that on purpose. Where a test exists to check zone matching or breach detection, it now stages the file so the
same breach is still checked through a tracked change. Where it checks bookkeeping, it reads the new keys:

- `tests/test_worker_cli.py::test_reconcile_flags_a_touch_zone_breach`: `README.md` is committed with `work/notes.md`.
- `tests/test_worker_cli_fixes.py`: the two nested tests stage their files (`git add`).
- `tests/test_worker_state.py::test_a_leafs_own_worker_logs_neither_breach_zones_nor_block_redelegation`: reads `untracked`
  and `untracked_outside_touch_zones`. It cannot stage the file, because the test later deletes it and re-delegates.
- `tests/test_review_round6_evidence.py::test_uncommitted_rename_is_seen_by_reconcile`: `_changed_since` no longer
  includes the untracked side of a rename. A second assertion on `_untracked` was dropped, because the private-imports
  gate refuses a new private reference. The new tests cover untracked files through the public delta.

## Touch zones

Confirmed: `specy_road/worker_reconcile.py`, `specy_road/worker_ops.py`, `specy_road/bundled_scripts/worker_cli.py`, `tests/`.
I added no new module. These files are outside the zones and left unchanged, for the maintainer to follow up:

- `docs/orchestration-workers.md`: the `reconcile W` row (line 250) does not yet mention `--dismiss`, the claim-less
  fallback, or that untracked files are only a warning.
- `specy_road/cli_usage.py`: line 144 lists `reconcile W` without `--dismiss`.
- `specy_road/templates/specyrd/commands/specyrd-orchestrate.md`: could mention `--dismiss` after a human confirms.

A known limit: for a clone lane whose HEAD is not in the coordinator's object database, the claim-less prompt build still
fails, so reconcile still reports a contract change. `--dismiss` clears the flag in that case.

## Verification

- `python -m pytest -n auto -q tests/test_worker_reconcile_merged.py`: 6 passed.
- Red-green: the new test file run against `HEAD` before the fix (a throwaway worktree): 5 failed and 1 passed. The one that
  passes (an unknown node is still refused) guards behaviour that already existed.
- `python -m pytest -n auto -q` (full suite): 3535 passed, 2 skipped, 2 failed. The first was the private-imports gate,
  fixed afterwards (see above). The second, `test_worker_cli.py::test_sync_wait_ends_on_an_event_or_times_out_with_exit_2`,
  is a timing test that passed on a rerun and is not affected by this change.
- After the fix: `python -m pytest -n auto -q tests/test_lean_gates.py tests/test_review_round6_evidence.py tests/test_worker_cli.py tests/test_worker_reconcile_merged.py`: passed.
- Full suite re-run on the committed code: `python -m pytest -n auto -q`: 3537 passed, 2 skipped, exit 0.
- `specy-road file-limits`: OK. `ruff check` on the changed files: passed.

## Added

### Helpers
- `worker_reconcile._untracked(worktree)`: lists untracked files apart from the worker's tracked changes (A2).
- `worker_reconcile.dismiss(repo_root, worker_id, reason)`: clears `needs_reconcile` and records the reason as an event (A1).
- `worker_reconcile.reconcile_lines(o)`: the reconcile text output, moved out of the CLI for the file cap, plus the
  untracked warning lines and the no-claim note.
- `_outside(paths)` (a local inside `_reconcile_locked`): one zone and bookkeeping filter shared by tracked and untracked paths.
- `worker_ops` re-export of `dismiss`: the CLI calls `ops.*`.

### Branches and guards
- `_target`: falls back to a claim-less `ReviewTarget` when the node exists and no claim has a branch (A1). It still
  raises for an unknown node or a claim whose branch is missing.
- `since` falls back to `rec.started_head`: a claim-less target has no base.
- `ref=head_sha(wt)` for `build_prompt` when there is no claim: otherwise "no registry claim" would count as a contract change.
- `dismiss` refuses a blank reason: A1 requires the reason to be recorded.
- `untracked` is computed only when `since` is set, matching the old behaviour, which returned nothing without a `since`.
- CLI `--dismiss REASON` on `worker reconcile`, with the op-id input bound to the reason.
- New delta keys `untracked`, `untracked_outside_touch_zones` and `claimed`: A2's separate report, and A1's no-claim note.

### Mocks
- none

### Tests (`tests/test_worker_reconcile_merged.py`)
- `test_reconcile_of_a_merged_leaf_uses_the_nodes_touch_zones`: merged leaf, node's zones, breach flagged (A1).
- `test_reconcile_of_a_merged_leaf_with_only_in_zone_work_clears_the_flag`: a merged leaf does not count as a contract change, and the flag clears (A1).
- `test_reconcile_still_refuses_an_unknown_node`: the fallback does not hide a bad node id.
- `test_dismiss_clears_the_flag_records_the_reason_and_list_and_sync_stop_showing_it`: dismiss through the CLI, the event, and the list and sync JSON and text (A1).
- `test_dismiss_needs_a_reason`: a blank reason exits 1 and keeps the flag.
- `test_an_untracked_file_outside_the_zones_is_a_warning_not_a_breach`: separate report, the warning line, and the same file staged is a breach (A2).
