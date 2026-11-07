# Implementation summary: M22.12 — gate-without-remote-head

## Summary

With `refs/remotes/<remote>/HEAD` missing, `integration_name` still returns no branch. The error tells the developer to run `git remote set-head <remote> <name>` and notes that `--auto` fails when the remote's HEAD is unborn. `<name>` is a real branch only when exactly one remote-tracking ref, other than one whose tip is HEAD's commit, has a readable committed `roadmap/git-workflow.yaml` whose `integration_branch` equals that ref's own name. An empty or missing value does not count as `main`. With none or several, the error names no branch and says to use the remote's real default branch. A malformed or non-mapping config, or a failed ref listing, is not treated as naming itself and does not raise. The sentence is text; the gate does not read policy from it.

When `validate`'s registry check treats the review switch as on only because the policy source cannot be read (the working tree leaves the switch off and `policy_source` errors), the error says the policy source could not be read and includes that same set-head command, instead of saying `require_implementation_review_before_finish` is true.

## Changes

Touch zones, confirmed against the call sites: `specy_road/review_policy_ref.py`, `tests/test_review_policy_ref_no_remote_head.py`, `docs/orchestration.md`, `CHANGELOG.md`, `specy_road/bundled_scripts/validate_roadmap_checks.py`. Callers outside those zones print `policy_source`'s error as returned, so they stay unchanged. The 0.2.x upgrade note in `docs/whats-new.md` is outside this leaf's zones and outside A4.

## Verification

- `pytest tests/test_review_policy_ref_no_remote_head.py` plus the existing set-head coverage in `tests/test_prerelease_review.py`, `tests/test_gate_config_agree.py`, `tests/test_review_round6_policy.py` and `tests/test_roster_source.py` (27 passed).
- `ruff check` on the edited Python, `specy-road file-limits`, the private-import check and the clone check.

## Walkthrough

1. A bare remote with an unborn `master` HEAD, `main` pushed, no set-head, and the checkout one commit ahead of that push: the error names `git remote set-head origin main`. Running that command makes `policy_source` return `refs/remotes/origin/main` with no error.
2. A pushed feature commit whose workflow names that feature branch is not the name in the hint.
3. A candidate whose workflow is malformed YAML, non-mapping YAML, or has no `integration_branch` fails closed and the hint names no branch.
4. `validate` with the working-tree switch off, `origin/HEAD` missing, and a registry row without `implementation_review` reports that the policy source could not be read and prints the set-head command.

## Added

### Helpers

- `_hint_branch` — the one remote-tracking branch the hint may name, excluding a ref at HEAD's commit; none when the count is not one or the listing fails
- `_missing_anchor_message` — the fail-closed error, with the set-head command and the `--auto` caveat
- `_unread_policy_source` — the policy-source error when the working tree leaves the review switch off, so validate can tell fail-closed from a switch that is on
- `_drop_origin_head` — test setup; deleting a remote HEAD that was never recorded is not a failure
- `_unborn_remote` — the shared bare-remote setup: unborn `master`, the branch pushed, the checkout one commit ahead
- `_hint_args` — the set-head command the error tells the developer to run, apart from the `--auto` caveat
- `_closed` — `integration_name` and `policy_source` both fail closed with the same error and no traceback

### Branches or guards

- `_hint_branch` returns none when HEAD cannot be resolved or `for-each-ref` fails, so a failed listing names no branch and does not raise
- a ref is skipped when its tip is HEAD's commit, it is `<remote>/HEAD`, or `integration_branch` is missing, empty, or not that ref's own name
- `_missing_anchor_message` prints `<name>` and "the remote's real default branch" when the hint names no branch
- the registry check uses the unread-policy wording only when that policy-source error is set

### Mocks

- none

### Tests

- `test_unborn_remote_head_fails_closed_and_the_hint_names_main` — the rc4 bare remote fails closed, the hint names main, and running it reads policy from `origin/main`
- `test_a_pushed_feature_commit_that_names_itself_is_not_the_hint` — a pushed feature commit that names itself is not the hint
- `test_an_unreadable_or_unnamed_candidate_names_no_branch` — malformed YAML, non-mapping YAML, and a missing `integration_branch` name no branch and do not traceback
- `test_validate_names_the_unreadable_policy_source` — validate says the policy source could not be read and prints the same set-head command
