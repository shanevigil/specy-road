# Implementation summary: M14.2 — doctor never offers to remove a live leaf's worktree or branch

## What changed

- **A3 (room):** `specy_road/bundled_scripts/doctor.py` is down from 399 to 303 lines. `_worktrees`, `_worktree_reason`, `_ignored_note`, `_keep_detached` and `_remove_worktree` moved to the new module `specy_road/doctor_worktrees.py`, and `_worktree_findings` moved there as `worktree_findings`. `Finding`, `merged_how`, `_all_upstream`, `_PROBE_IDENT`, `SAME_PATCH` and `TEMP_WORKTREES` moved with them so the new module does not import from `doctor.py`, which would be circular. `doctor.py` re-imports them, so `doctor.SAME_PATCH`, `doctor.TEMP_WORKTREES` and `doctor.merged_how` still work for callers and tests.
- **A1 (live):** `live_holders()` maps each branch that something holds to a `live: …` text:
  - a worker record that is not terminal: `live: worker <W> (<state>)`
  - a registry entry, local or on the integration branch, whose leaf is not Complete: `live: claimed by <node>`
  - an open milestone rollup: `live: open rollup of <id>`

  The result is stored on `_Ctx.held`. A held branch is listed with `, so --fix leaves it` and no fix (`remove=None`), both in the branch section and for its worktree. A claimed, non-Complete branch is still left out of the branch section, as before.
- **A2 (own commits):** replaced in fix round 1 by `own_commit_evidence()`; see that section below. (The round-0 `has_own_commits()` reflog-count and first-parent inference was removed.)
- **Interpretation:** a registry row whose leaf is Complete (fixture `settled`) is not an *open* claim, so it is still offered for removal as before. This matches the out-of-scope note.
- **Behaviour change in an existing test:** `wt-thing` sits on the fixture's claimed branch `feature/rm-thing` (M1.1, not Complete). It used to be listed as merged and removed by `--fix`. Under A1 it is now `live: claimed by M1.1` and kept. I updated `tests/test_doctor.py` to match, and no assertion was loosened.

## Touch zones (final)

`specy_road/bundled_scripts/doctor.py`, `specy_road/doctor_worktrees.py` (new), `tests/` (`tests/test_doctor.py`, new `tests/test_doctor_live.py`). The zones were accurate, and nothing outside them changed.

## Verification

- `python -m pytest -q -n 4 tests/test_doctor.py tests/test_doctor_live.py`: 19 passed
- full `python -m pytest -q -n 4`: 3991 passed
- `specy-road file-limits`: OK
- `ruff check` on the changed files: clean

## Added

- `specy_road/doctor_worktrees.py`: new module that holds the worktree findings, to keep `doctor.py` within 400 lines (A3).
- `doctor_worktrees.has_own_commits`: removed in fix round 1; replaced by `own_commit_evidence` (below).
- `doctor_worktrees.live_holders`: builds the branch → `live: …` map from workers, open claims and open rollups (A1).
- `_Ctx.held` field: carries that map to the branch and worktree sections (A1).
- Branch in `_branch_reason`: merged with no commits of its own → `no commits yet`, with a `False` verdict (A2).
- Guard in `_branch_findings`: a held branch, or one with no commits yet, is listed with `remove=None` (A1, A2).
- Branches in `_worktree_reason`: held branch → live reason, branch with no commits → `has no commits yet`, both not fixable. It now returns `(reason, fixable)` (A1, A2).
- Guard in `worktree_findings`: a finding that is not fixable gets `, so --fix leaves it` and no remove (A1, A2).
- Test `test_a_claimed_worktree_on_a_fresh_branch_is_live_and_fix_leaves_it`: the A2-required claimed fresh worktree, and A1 for claims.
- Test `test_an_unclaimed_branch_with_no_commits_is_never_merged`: A2 for a branch and worktree with no commits. It also checks that a merged unclaimed branch with commits is still deleted (out-of-scope behaviour unchanged).
- Test `test_a_worker_held_branch_is_live_until_the_worker_is_terminal`: A1 for worker records (running is kept; terminated is offered again). It adds `work/.workers/` to `.git/info/exclude`, as a consumer's ignore of `work/` would, so registry-prune sees a clean tree.
- Mocks: none.

## Fix round 1 (Sol F1–F5)

I merged `origin/WIP/improvements-0-3-1` first (`ad50bd02`). The fix is commit `533ca28b`.

The round-0 root cause: "has commits of its own" was inferred from reflog *counts* and from first-parent ancestry, and a remote ref borrowed its local namesake's reflog. The new design follows the coordinator's precedence:

1. **Liveness first (F1).**
   - `live_holders()` now returns two maps: one by branch and one by resolved worktree path. Its sources are workers that are not terminal, live sessions (`session_presence.list_sessions`), registry claims whose leaf isn't Complete, and open rollups.
   - `_worktree_reason` checks `_live_reason` before anything else, including `prunable` (directory missing). That check does not depend on `merged_local`. A live worktree gets its live reason and no fix.
   - Live worktrees are listed only when some other finding would have listed them: the directory is missing, the branch is merged, or the worktree is detached. A live worktree on an unmerged branch is not tidy-up material, so it stays silent.
   - Claimed, non-Complete branches are still left out of the branch section, as before (never offered). Branches held by a worker or session are listed with their live reason and no fix.
2. **Removal needs positive evidence (F2–F4).** `own_commit_evidence(root, ref, target)` returns `present`, `absent` or `ambiguous`, judged on that exact ref only:
   - **present:** either a merge commit on the target whose subject contains `Merge branch '<branch>'` (finish's subject) brought this tip in (the tip is an ancestor of a non-first parent and not of the first parent), or, for a local ref, its own reflog has a `commit…`, `merge …` or `cherry-pick` entry whose commit the tip contains.
   - **absent:** a local ref whose reflog has only `branch: Created from` and `Branch: renamed` entries, all at its tip. It is reported as `<why>, no commits yet`, with no fix.
   - **ambiguous:** everything else, such as an expired reflog, a fresh clone, a remote-tracking ref without a finish merge, or a reset. It is reported as `merged; no local evidence of own commits — remove by hand if intended`, with no fix.
   - **Patch-content merges (`SAME_PATCH`):** these are still removable without that evidence. Their tip is not contained in the target, so by construction they carry commits the target lacks by SHA but has by patch. Removing them loses nothing, and the rebased/squashed fixture rows keep their cleanup.
3. **F5:** `tests/test_doctor_live.py` defines public `run_doctor`, `has_ref` and `kept` helpers and imports only the public `doctor_repo` fixture.

**Accepted trade-off (F4, planner's decision):** "preserve cleanup" became "preserve reporting; cleanup is offered only with evidence". Here is what that means in practice:
- A real feature branch landed by fast-forward whose reflog has expired, or which exists only on the remote, is still reported as `merged`, but `--fix` no longer removes it; a human does.
- An unclaimed merged branch with intact commit evidence, or landed by finish's `Merge branch '…'` commit (the fixture's `--no-ff` merges), is removed exactly as before.
- Because a remote-tracking ref can only show evidence through a finish merge commit, a fresh pushed branch that nobody has merged is reported as `merged; no local evidence…`, not as "no commits yet". That wording is the coordinator's.

**Left unchanged (out of scope):** an unclaimed local branch that is *not* merged (`claim gone, not merged: N commit(s) …`) is still offered for deletion, as before this leaf. That includes F3's local branch with its unpushed commit. The F3 test asserts only the remote ref.

### Fix round 1: removal decision table

"Contained" means the tip is an ancestor of the integration branch. "Report" means listed without a fix; "fix offered" means listed with `--fix` removal; "skip" means not listed.

| live | dir | contained | evidence | ref | outcome | covered by |
|---|---|---|---|---|---|---|
| yes (claim) | present | yes | any | local branch + worktree | branch skip; worktree report `live: claimed by` | `test_a_claimed_worktree_on_a_fresh_branch_is_live_and_fix_leaves_it`, `test_doctor.py::test_dry_run…` (`wt-thing`) |
| yes (claim) | missing | yes | any | worktree | report `live: claimed by`, never `directory missing` | `test_f1_a_claimed_worktree_whose_directory_moved_is_live_not_missing` |
| yes (worker) | present | yes | present | local + remote + worktree | report `live: worker W (state)` for all three | `test_a_worker_held_branch_is_live_until_the_worker_is_terminal` |
| yes (worker/session, by path) | present/missing | n/a (detached) | n/a | worktree | report live reason | no dedicated test (same code path as the branch-held case) |
| yes | present | no | any | worktree | skip (not tidy material) | `test_doctor.py` (unmerged claimed branches are absent from output) |
| no | missing | any | any | worktree | fix offered (`directory missing`) | `test_doctor.py::test_fix_removes…` (`wt-missing`) |
| no | present | yes | present (commit reflog entry) | local | fix offered (`merged`) | `test_doctor.py::test_fix_removes…` (`rm-done`), `test_f4_…expired_reflog…` (before expiry) |
| no | present | yes | present (finish `Merge branch` commit) | remote | fix offered | `test_doctor.py::test_fix_removes…` (`origin feature/rm-gone`, `rm-done` on origin) |
| no | present | yes | absent (create only) | local + worktree | report `no commits yet` | `test_an_unclaimed_branch_with_no_commits_is_never_merged` |
| no | present | yes | absent (create + rename) | local + worktree | report `no commits yet` | `test_f2_a_fresh_branch_renamed_before_its_first_commit_has_no_commits` |
| no | — | yes | ambiguous (remote ref, no finish merge; local namesake ahead) | remote | report `merged; no local evidence…` | `test_f3_a_fresh_remote_branch_does_not_borrow_its_local_namesakes_commits` |
| no | — | yes | ambiguous (expired reflog) | local + remote | report `merged; no local evidence…` | `test_f4_a_fast_forwarded_commit_with_an_expired_reflog_is_merged_but_left` |
| no | — | yes | ambiguous (no local branch) | remote | report `merged; no local evidence…` | `test_f4_a_fast_forwarded_commit_with_no_local_branch_is_merged_but_left` |
| no | — | no, same patch | n/a (commits by construction) | local + remote | fix offered (`merged (same patch content)`) | `test_doctor.py::test_fix_removes…` (`rm-squash`, `rm-rebased`) |
| no | — | no | n/a | local + remote | fix offered (`claim gone, not merged`), as before; out of scope | `test_doctor.py::test_fix_removes…` (`rm-open`) |
| yes (worker), then terminal | present | yes | present | local + worktree | fix offered once the worker is terminal | `test_a_worker_held_branch_is_live_until_the_worker_is_terminal` |

### Added in fix round 1

- `doctor_worktrees.own_commit_evidence`: the present/absent/ambiguous evidence test on the exact ref (F2, F3, F4).
- `doctor_worktrees._finish_merge_brought`: finish-merge-commit evidence that works for remote refs too (F3, F4).
- `doctor_worktrees._is_ancestor`: a small `merge-base --is-ancestor` wrapper used by both evidence checks.
- `doctor_worktrees.NO_EVIDENCE`, `_COMMIT_ENTRIES`, `_NAMING_ENTRIES`: the report text and the reflog-subject classes (F2, F4).
- `doctor_worktrees._live_reason`, plus `live_holders` now covering sessions and worktree paths, and `_Ctx.held_paths`: liveness by branch or path, checked first (F1).
- `_MERGED_WORKTREE`, and `merged_local` now holding a verdict string (`merged`/`fresh`/`unproven`): the worktree text and fixability follow the branch's verdict.
- Branch in `_branch_reason`: the `unproven` verdict, reported without a fix (F4).
- Tests: `test_f1_…`, `test_f2_…`, `test_f3_…`, `test_f4_…expired_reflog…`, `test_f4_…no_local_branch…` (one per finding), and public test helpers `run_doctor`/`has_ref`/`kept` (F5).
- Mocks: none.

### Verification (targeted)

- `python -m pytest -q -n 4 tests/test_doctor.py tests/test_doctor_live.py tests/test_gate_config_agree.py tests/test_nested_unpushed_report.py tests/test_worktree_env_setup.py tests/test_doctor_version_skew.py`: 73 passed
- `specy-road file-limits`: OK (`doctor.py` 313 lines, `doctor_worktrees.py` about 225)
- `ruff check` on the changed files: clean
