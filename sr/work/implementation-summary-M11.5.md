# Implementation summary: M11.5 `pickup-claim-heuristic`

## What changed

- `specy_road/bundled_scripts/do_next_task_self_heal.py`
  - `claim_branch_found` replaces the inline pair of `rev-parse` calls in
    `detect_stale_claims`. It checks `refs/heads/<branch>` first and stops if
    that ref exists, and only then checks `refs/remotes/<remote>/<branch>`
    (`any()` over the two refs, so the check short-circuits).
  - `emit_stale_claim_warning` now takes `branch`, `remote` and `cause`. Its
    new `checked:` lines name both refs it tested and show that each was absent
    (A2). The `git checkout -b` hint uses the claim's real branch, not one
    rebuilt from the codename.
  - Each caller gets its own cause text. `SCAN_CAUSE` (pre-pickup scan) says a
    claim held by another clone whose branch is not pushed looks the same as a
    dead one, so confirm with the owner before removing it. `ROLLBACK_CAUSE`
    keeps the old failed-pickup wording; that path is where it was accurate.
  - `warn_unresolved_rollback`: after a failed pickup whose self-cleanup also
    failed, it prints the stale warning and fix lines only if
    `claim_branch_found` is false. If the branch exists it prints a one-line
    note that the claim is not stale and how to resume it (A1, A2).
- `specy_road/bundled_scripts/do_next_task_pickup_helpers.py`: the rollback
  path in `push_and_branch_with_self_heal` calls `warn_unresolved_rollback`.
  Before, it called `emit_stale_claim_warning` without checking any ref.

Before this change, `detect_stale_claims` already tested both refs, but nothing
gated the rollback path's warning, and no warning said what it had checked.
After it, both places that print the destructive advice test local first, then
remote, and print the advice only when both refs are absent.

## Touch zones (confirmed)

`specy_road/bundled_scripts/do_next_task_self_heal.py`,
`specy_road/bundled_scripts/do_next_task_pickup_helpers.py`, `tests/`.
`specy_road/bundled_scripts/do_next_task.py` needed no change: it only calls
`warn_about_stale_claims_before_pickup`, and that function keeps its signature.
`registry_prune` and `doctor` call `detect_stale_claims`, whose signature and
results are unchanged.

## Verification

- `pytest tests/test_do_next_task_self_heal.py tests/test_do_next_task_branch_resume.py tests/test_validate_self_heal.py`: 22 passed
- `specy-road file-limits`: OK
- full `pytest`: see the hand-off

## Added

- `SCAN_CAUSE`: the pre-pickup warning no longer claims a pickup failure it cannot know about, and it warns that an unpushed branch in another clone is invisible from here.
- `ROLLBACK_CAUSE`: keeps the original wording for the failed-pickup path, where it is accurate.
- `_branch_refs`: one place that spells the two refs, so the check and the warning's `checked:` lines cannot drift apart.
- `claim_branch_found`: the local-first, then-remote existence test (A1, A2), shared by the scan and the rollback path.
- `warn_unresolved_rollback`: gates the rollback path's fix lines on the branch being absent; if it exists, prints a non-destructive note instead (A1, A2).
- `emit_stale_claim_warning` `branch`/`remote`/`cause` keyword arguments: the warning says which refs were checked (A2).
- test `test_a_local_only_branch_is_not_stale_and_prints_nothing`: a local-only branch gives no stale result and no output (A3).
- test `test_a_remote_only_branch_is_not_stale`: the remote ref alone also counts as present.
- test `test_a_missing_branch_warns_and_names_both_refs_checked`: a missing branch warns, names both refs, and includes the fix lines and the confirm-first caveat (A3).
- test `test_a_failed_rollback_with_a_local_branch_gives_no_fix_lines`: the rollback path prints no destructive advice when the branch exists locally (A1).
- test `test_a_failed_rollback_with_no_branch_warns`: the rollback path still warns, with the rollback cause, when the branch is missing (A2).
- helper `_repo_with_branch` and constant `LIVE` in the test file: a real git repo with an optional local-only branch, for the tests above.
- mocks: none.
