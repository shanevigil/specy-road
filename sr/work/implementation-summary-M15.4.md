# Implementation summary: M15.4 — parallel PR-mode leaves reconcile bookkeeping by rule

Branch `feature/rm-parallel-pr-leaves-reconcile-bookkeeping-by-rule`, base `cb279e0586b0c2d576f7484bf53bb237aea70bca`
(plus WIP merge and reviewer rework rounds through `gpt-6.1-sol` R1–R4 and `gpt-6.1-sol-low` R1).

## What changed (prior work, unchanged intent)

- **A1–A4** as in the brief: `reconcile-branch`, pickup register digest, docs, and tests
  (`tests/test_reconcile_branch.py`, `tests/test_pickup_register_digest.py` for acceptance scenarios).

## Rework (`gpt-6.1-sol` R1–R4)

- **R1 — fetch before merge.** `reconcile_branch` checks `git_ok` on `git fetch` and exits 1 before merge when fetch fails.
- **R2 — push when already merged.** Upstream push runs even when the integration tip is already contained locally.
- **R3 — abort after pushed pickup.** Deregister commit regenerates tracked generated files (`regenerated_tracked_paths`).
- **R4 — failed-pickup self-heal.** Same regeneration on self-heal cleanup (lazy import avoids import cycle).

## Fix round (`gpt-6.1-sol-low` R1)

- **Integration ref after fetch.** After a successful `git fetch <remote> <ib>`, reconcile merges
  ``FETCH_HEAD`` (via ``_integration_sha_after_fetch``), not ``base_ref``'s remote-tracking or local
  branch, so a restricted ``remote.origin.fetch`` refspec cannot leave a stale ``origin/<ib>`` as the
  merge source while fetch still retrieved the current tip.

## Probes

- `reconcile_branch` with broken fetch URL and valid push URL, stale `origin/dev`, integration advanced on remote: exit 1, HEAD and remote feature ref unchanged (failed fetch).
- `reconcile_branch` with pre-receive hook rejecting feature push, then retry: upstream updated (no-new-merge push path).
- Public CLI pickup → `abort-task-pickup`: `digest --check` on local `main` and detached `origin/main` worktree (pushed abort digest).
- Public CLI `do-next-available-task` with first `main` push rejected: self-heal leaves remote digest current (failed-pickup cleanup digest).
- Lazy imports in abort / self-heal: no register ↔ self_heal import cycle.

## Fix round: probes

- Restricted `remote.origin.fetch` (feature branch only) with `origin/dev` pinned stale via `update-ref`, integration advanced on bare remote: reconcile exit 0, `HEAD^2` equals remote `dev` tip, new integration file present (stale-tracking-ref class; merge uses fetch tip not `base_ref`).
- `finish_pr_merge.pr_merge_integration_or_exit` still uses `base_ref` after fetch (finish preflight, not reconcile); unchanged — A1 is reconcile-only; same class noted for future alignment.
- Targeted pytest importer set (210 tests) and `file-limits`: pass.

## Touch zones (final)

Brief list plus `specy_road/bundled_scripts/do_next_task_self_heal.py` (R4).

## Added

### Helpers / modules
- `reconcile_branch._integration_sha_after_fetch`: reads the integration tip git stored in `FETCH_HEAD` after fetch (fix round).

### Branches / guards
- Merge uses `FETCH_HEAD` SHA after successful fetch, not `base_ref` (fix round sol-low R1).
- Prior round: fetch-failure guard, push on already-contained tip, abort/self-heal digest regeneration, lazy `regenerated_tracked_paths` imports.

### Mocks
- none.

### Tests
- `test_reconcile_merges_the_fetch_head_tip_when_tracking_ref_is_stale`: sol-low R1 restricted refspec + stale `origin/dev`.
- Prior round: fetch failure, push retry, pushed abort digest, self-heal digest, two-leaf reconcile scenarios, pickup digest, branch guards.
