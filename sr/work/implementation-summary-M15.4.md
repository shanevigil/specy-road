# Implementation summary: M15.4 — parallel PR-mode leaves reconcile bookkeeping by rule

Branch `feature/rm-parallel-pr-leaves-reconcile-bookkeeping-by-rule`, base `cb279e0586b0c2d576f7484bf53bb237aea70bca`
(rework for reviewer `gpt-6.1-sol` R1–R4 on top of the prior `8574f287` / `cb279e05` hand-off).

## What changed (prior work, unchanged intent)

- **A1–A4** as in the previous summary: `reconcile-branch`, pickup register digest, docs, and tests
  (`tests/test_reconcile_branch.py`, `tests/test_pickup_register_digest.py` for acceptance scenarios).

## Rework (R1–R4)

- **R1 — fetch before merge.** `reconcile_branch` checks `git_ok` on `git fetch` and exits 1 with a named
  error before reading a possibly stale `remote/ib` ref. No merge or push on fetch failure.
- **R2 — push when already merged.** When the integration tip is already contained locally (for example after
  a merge commit succeeded but `git push` was rejected), reconcile still runs the upstream push path instead
  of returning 0 early.
- **R3 — abort after pushed pickup.** `_remove_registry_row_and_push` regenerates tracked generated files
  via `regenerated_tracked_paths` and commits them with the registry row removal (explicit paths, same as
  register). Lazy import avoids a register ↔ pickup_helpers ↔ self_heal import cycle.
- **R4 — failed-pickup self-heal.** `attempt_self_cleanup` uses the same regeneration and explicit-path
  commit before pushing the integration branch.

## Probes

- `reconcile_branch` with broken fetch URL and valid push URL, stale `origin/dev`, integration advanced on remote: exit 1, HEAD and remote feature ref unchanged (R1 class: failed fetch).
- `reconcile_branch` with pre-receive hook rejecting `feature/rm-two` push, then hook removed and command retried: first exit 1 after local merge; second exit 0 with `origin/feature/rm-two` at the merge commit (R2 class: no-new-merge path without push).
- Public CLI pickup → `abort-task-pickup`: `digest --check` on local `main` and on detached worktree at `origin/main` both pass (R3 class: pushed abort without digest regeneration).
- Public CLI `do-next-available-task` with bare hook rejecting the first push to `main` only: exit 1; local and remote `main` pass `digest --check`; remote registry empty (R4 class: self-heal push without digest regeneration).
- Lazy import sites in `abort_task_pickup._remove_registry_row_and_push` and `attempt_self_cleanup`: module import graph loads without cycle (register ↔ self_heal).
- Reviewer focused pytest importer set (209 tests), `file-limits`, dogfood `validate`: pass.

## Touch zones (final)

Same as the brief, plus `specy_road/bundled_scripts/do_next_task_self_heal.py` (R4 regeneration in self-heal commit).

## Added

### Helpers / modules
- none (this round extends existing helpers).

### Branches / guards
- `reconcile_branch`: fetch-failure guard before `base_ref` / merge (R1).
- `reconcile_branch`: upstream push on already-contained integration ref (R2).
- `abort_task_pickup._remove_registry_row_and_push`: regenerate tracked generated files in abort commit (R3).
- `attempt_self_cleanup`: regenerate tracked generated files in self-heal commit (R4).
- Lazy imports of `regenerated_tracked_paths` in abort and self-heal to break the import cycle.

### Mocks
- none.

### Tests
- `test_reconcile_refuses_when_fetch_fails_and_leaves_head`: R1 stale tracking ref + unavailable fetch.
- `test_reconcile_retries_push_when_merge_is_already_committed`: R2 rejected-first-push then retry updates upstream.
- `test_abort_after_pushed_pickup_regenerates_the_digest_on_integration`: R3 pushed abort leaves digest current locally and at `origin/main`.
- `test_failed_pickup_self_heal_leaves_integration_digest_current`: R4 one-time registration push rejection; self-heal digest on integration.
- `_digest_check_at_origin_main` helper in `test_pickup_register_digest.py`: detached worktree at `origin/main` for remote snapshot `digest --check`.
