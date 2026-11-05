# Implementation summary: M14.2 — doctor never offers to remove a live leaf's worktree or branch

## What changed

- **A3 (room):** `specy_road/bundled_scripts/doctor.py` is down from 399 to 303 lines. `_worktrees`, `_worktree_reason`, `_ignored_note`, `_keep_detached` and `_remove_worktree` moved to the new module `specy_road/doctor_worktrees.py`, and `_worktree_findings` moved there as `worktree_findings`. `Finding`, `merged_how`, `_all_upstream`, `_PROBE_IDENT`, `SAME_PATCH` and `TEMP_WORKTREES` moved with them so the new module does not import from `doctor.py`, which would be circular. `doctor.py` re-imports them, so `doctor.SAME_PATCH`, `doctor.TEMP_WORKTREES` and `doctor.merged_how` still work for callers and tests.
- **A1 (live):** `live_holders()` maps each branch that something holds to a `live: …` text:
  - a worker record that is not terminal: `live: worker <W> (<state>)`
  - a registry entry, local or on the integration branch, whose leaf is not Complete: `live: claimed by <node>`
  - an open milestone rollup: `live: open rollup of <id>`

  The result is stored on `_Ctx.held`. A held branch is listed with `, so --fix leaves it` and no fix (`remove=None`), both in the branch section and for its worktree. A claimed, non-Complete branch is still left out of the branch section, as before.
- **A2 (own commits):** `has_own_commits()` decides from the local branch's reflog: true if there is an entry after creation, or if the tip is not the creation commit. A remote-tracking ref uses its local branch's reflog. With no reflog, the branch counts as having commits only if its tip is not on the integration branch's first-parent line. `_branch_reason` reports a merged branch with no commits of its own as `<why>, no commits yet`, with no fix. `merged_local` is now a `dict[str, bool]` (branch → has own commits), and the worktree section reports `branch X has no commits yet`, with no fix.
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
- `doctor_worktrees.has_own_commits`: the reflog/first-parent "commit of its own" test (A2).
- `doctor_worktrees.live_holders`: builds the branch → `live: …` map from workers, open claims and open rollups (A1).
- `_Ctx.held` field: carries that map to the branch and worktree sections (A1).
- Branch in `_branch_reason`: merged with no commits of its own → `no commits yet`, with a `False` verdict (A2).
- Guard in `_branch_findings`: a held branch, or one with no commits yet, is listed with `remove=None` (A1, A2).
- Branches in `_worktree_reason`: held branch → live reason, branch with no commits → `has no commits yet`, both not fixable. It now returns `(reason, fixable)` (A1, A2).
- Guard in `worktree_findings`: a finding that is not fixable gets `, so --fix leaves it` and no remove (A1, A2).
- Test `test_a_claimed_worktree_on_a_fresh_branch_is_live_and_fix_leaves_it`: the A2-required claimed fresh worktree, and A1 for claims.
- Test `test_an_unclaimed_branch_with_no_commits_is_never_merged`: A2 for a branch and worktree with no commits, plus `has_own_commits` on both cases. It also checks that a merged unclaimed branch with commits is still deleted (out-of-scope behaviour unchanged).
- Test `test_a_worker_held_branch_is_live_until_the_worker_is_terminal`: A1 for worker records (running is kept; terminated is offered again). It adds `work/.workers/` to `.git/info/exclude`, as a consumer's ignore of `work/` would, so registry-prune sees a clean tree.
- Mocks: none.
