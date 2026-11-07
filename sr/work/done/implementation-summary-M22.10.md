# M22.10 — reconcile-branch keeps a local-only claim, and a checkout failure after landing does not undo the bookkeeping

## Touch zones

The listed zones were accurate. Nothing outside them needed a change: callers that unpack `(ok, err)` still treat a true first value as success, and the CLI prints the checkout warning in `finish_modes`.

Final list: `specy_road/reconcile_branch.py`, `specy_road/finish_pr_merge.py`, `specy_road/finish_modes.py`, `specy_road/finish_land_local.py`, `specy_road/finish_land_integration.py`, `tests/test_reconcile_branch.py`, `tests/test_finish_merge_failure_undo.py`, `docs/git-workflow-parallel-prs.md`, `docs/git-workflow.md`, `CHANGELOG.md`.

`reconcile_branch.py` already passed `drop_row=False` while the leaf still holds its claim. The drop happened in `_registry_from`, which checked the integration ref's registry out byte for byte.

## What changed

A claim made with `do-next-available-task --local` is only on the feature branch. When reconcile-branch keeps that row and the integration ref's registry lacks the codename, the merged registry is the integration registry plus the leaf's row from `HEAD`. The file is written with `write_registry`. When the ref already has the row, or there is no row on `HEAD` to add, the ref's blob is still checked out byte for byte so its comments survive. A finished leaf still drops its row.

When the integration merge succeeded (and, in push mode, the push) and only the final `git checkout <feature>` fails, both landing paths return success with one warning. `finish_modes` prints that warning on stderr, reports the landing as done, and does not run `undo_bookkeeping`, on the first finish and on a retry. The warning names `git checkout <feature>` and does not say to run finish again. A checkout failure after a failed merge or a failed push still returns that failure, so bookkeeping is undone as before.

`docs/git-workflow-parallel-prs.md` and `docs/git-workflow.md` each gained one line. `CHANGELOG.md` `[Unreleased]` `Fixed` records both.

## Added

### Helpers

- `_head_row` — the leaf's registry row at `HEAD`, so a local-only claim can be copied when the integration ref lacks it.
- `_checkout_feature_after_landing` — checks the feature branch out after the landing attempt; a failure after success is a warning, and a failure after a failed merge or push stays that failure.
- `_pushed_app` — an `init project` checkout with its integration branch on a bare origin, so the reconcile test can run a real `--local` pickup.
- `_feature_checkout_hook` — a `post-checkout` hook that exits 1 only when switching to the feature branch.
- `_set_land` — commits `land: local` on the finish fixture.
- `_clash` — a non-bookkeeping conflict so the integration merge fails while the checkout hook is also installed.
- `_separated` — runs finish with stdout and stderr apart, so the test can see the one stderr warning.
- `_node_status` — the leaf's status on an integration ref, to show the completion landed.

### Branches or guards

- `_registry_from` `keep_local_row` — when the integration registry lacks this codename, append the `HEAD` row and write the file; otherwise keep the previous checkout-or-drop behaviour.
- `_checkout_feature_after_landing` returns the merge or push error when `landed` is false — a checkout failure after that failure does not become a successful landing.
- `finish_modes` prints `err_msg` on stderr only when the landing returned success — the checkout warning is not undo advice, on the first finish and on a retry.

### Mocks

none

### Tests

- `test_reconcile_keeps_a_local_only_claim_when_the_remote_moves` — after `--local` pickup and an independent commit on the remote integration branch, the merged registry is that ref's row plus the leaf's row, and finish's registry lookup finds it.
- `test_feature_checkout_failure_keeps_a_landed_finish` — `land: local`, push, and a failed merge, each with a post-checkout hook that exits 1 on the feature branch. The first two exit 0 with one checkout warning, the completion on the integration branch, and the bookkeeping commit kept. The merge-failure row undoes the bookkeeping.
