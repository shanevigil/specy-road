# Implementation summary: M14.4.1

Per nested repository, land by push, locally or by hand, and base worktrees on the remote or local tip.

## Touch zones (final)

Unchanged from the brief: `specy_road/nested_repos.py`, `specy_road/nested_repos_land.py` (new),
`specy_road/templates/project/schemas/git-workflow.schema.json`, `docs/git-workflow.md`, `tests/`.
No caller outside the zones changed: `finish_land_integration.py`, `doctor.py`, `session_plan_*` still
import `land_nested_branches` / `unpushed_branches` / `describe_unpushed` / `report_unpushed` from
`nested_repos`, which re-exports them.

## Acceptance

- **A1:** The object form of a `nested_repos` item accepts `land` (`push` | `local` | `manual`) and `base`
  (`remote` | `local`), plus `refuse_behind_remote` (boolean), which A3 needs ("refusing ... only if the
  entry says so"). The schema documents all three. `NestedRepo` gains `land="push"`, `base="remote"` and
  `refuse_behind=False`, read in `nested_repos()`. The defaults match today's behaviour.
- **A2:**
  - `land: local` (`_land_one_locally`) fetches and pushes nothing. It merges in the same detached temporary
    worktree, based on the local integration branch. It then moves the ref with
    `update-ref refs/heads/<ib> <merge> <old>`, which fails if the branch moved. Where `<ib>` is checked out,
    that checkout must be clean (tracked files): a dirty one is refused, naming it, before anything merges. The
    clean-checkout handling was rewritten in fix round 1 (see below).
  - `land: manual` lands nothing when the branch is in neither the local nor the remote-tracking `<ib>`.
    `land_nested_branches` returns not-ok with one `git -C <repo> merge --no-ff <feature>` line per such
    repository and "re-run finish-this-task after merging". Finish's existing `merge_landing_failed` then
    exits 1 before the main repository moves. A re-run after the merge passes.
  - Push mode is unchanged: the code is the same, with the temporary-worktree merge factored into
    `_merge_in_temp_tree`.
  - Tests assert that the nested remote does not move in both modes.
- **A3:** `base: local` makes `_source_and_tip` use `refs/heads/<ib>` (via the new `nested_base_ref`). A
  missing local branch is refused. With `refuse_behind_remote: true`, a local branch that its remote-tracking
  one is ahead of is refused. `_merge_base` uses the same ref, so with `base: local`, reconcile, the
  implementation gate and `review-packet` do not count local-only integration commits as the leaf's changes.
  A test shows a local-only commit is in the worktree.
- **A4:** `nested_repos.py` is now 313 lines and the new `nested_repos_land.py` is 250 lines (after fix round 1).
  `specy-road file-limits` passes.

## Design notes

- To avoid a circular import, `nested_repos.py` imports the re-exports at its end. `nested_repos_land.py`
  imports `nested_repos` names inside its functions (and `NestedRepo` under `TYPE_CHECKING`), so either
  module can be imported first.
- In `auto` mode, a manual stop falls back to the PR tail like any other landing failure. That fallback is
  `finish_modes.py`, outside the zones, and is unchanged.
- `doctor`'s unpushed report will list a `land: local` integration branch's local merges. It is advisory
  and unchanged (per-repo policy is out of scope).

## Verification

- `python -m pytest -q tests/test_nested_repo_land_modes.py`: 11 passed.
- `python -m pytest -q -n 4 tests/test_nested_repo_finish.py tests/test_nested_repo_worktrees.py tests/test_nested_unpushed_report.py tests/test_worktree_prune.py tests/test_nested_repo_land_modes.py tests/test_finish_merge_mode.py tests/test_doctor.py tests/test_schema_revision.py`: 121 passed.
- `python -m pytest -q -n 4` (full suite): 3990 passed.
- `specy-road file-limits`: OK.
- `ruff check` on the changed Python files: clean.

## Fix round 1 (Sol: R1 P1, R2 P2)

Merged `origin/WIP/improvements-0-3-1` first (clean merge).

- **R1:** the landing is bound to the named ref `refs/heads/<ib>` and its original tip `<old>`:
  - Before moving anything, if `<ib>` was checked out somewhere, that checkout's
    `git symbolic-ref -q HEAD` must still be `refs/heads/<ib>`. If it detached or now points at another
    branch, even at the same commit, landing is refused and nothing moves.
  - The ref moves with `git update-ref refs/heads/<ib> <merge> <old>` (compare-and-swap), so the old
    `merge --ff-only` in whatever branch the checkout held is gone.
  - The checkout is then updated with `git read-tree -m -u <old> <merge>`. This runs only after
    re-checking that the checkout still has `<ib>`. If the update fails, the ref is put back with
    `update-ref refs/heads/<ib> <old> <merge>` (another compare-and-swap) and landing is refused.
  - Success is reported only after `git merge-base --is-ancestor <merge> refs/heads/<ib>` passes.
  - Regression test (`test_land_local_refuses_when_the_checkout_leaves_the_integration_branch_during_the_merge`,
    two cases: another branch at the same commit, and detached). It goes through
    `land_merge_feature_into_integration`, with a real `pre-merge-commit` hook that switches the checkout
    during the temporary merge. It asserts not-ok, `dev` unchanged, the switched-to branch unchanged, and
    neither the nested nor the main remote pushed.
- **R2:** every path in a printed command goes through `shlex.quote`:
  - the manual merge command (the leaf branch name is quoted too);
  - the `git -C <repo> worktree remove <dest>` hint in `add_nested_worktrees`, which also now names the
    actual destination instead of `<path>`.

  Regression test (`test_the_printed_manual_command_runs_for_a_path_with_spaces`): the project is built under
  `parent with spaces`, and the test runs the printed line through the shell. It asserts exit 0, that the
  leaf branch is in `dev`, and that a re-run of landing then succeeds.
- **Red-green:** with HEAD's (pre-fix) `nested_repos_land.py` swapped in, the three new tests fail (exit 1).
  With the fix they pass.
- **Lint:** the checkout update moved into `_follow_in_checkout`, which keeps `_land_one_locally` under
  ruff's C901 limit.

## Fix round 1: audit

### Printed commands (nested_repos_land.py, nested_repos.py)

- `nested_repos_land.land_nested_branches` (manual):
  `git -C <shlex.quote(repo)> merge --no-ff <shlex.quote(branch)>`, followed by a `#` comment that the
  shell ignores. Copy-runnable; the test above runs it.
- `nested_repos.add_nested_worktrees` (refusal):
  `git -C <shlex.quote(src)> worktree remove <shlex.quote(dest)>`. Copy-runnable when `dest` is a
  worktree; otherwise the message's alternative applies ("or delete the directory").
- `nested_repos.announce_nested_worktrees`: names `specy-road worker delegate` as the follow-up. It contains
  no path to quote, but it is not a complete command: delegate needs the node id and `--model`, which this
  function is not given. Unchanged, since it predates this leaf.
- No other message in either file prints a command. The rest are prose such as "commit or stash them
  there, then re-run" and "fix integration_branch/remote ... in roadmap/git-workflow.yaml", or `[ok]` lines.
  `report_unpushed` and `describe_unpushed` print only facts.

### Every point where landing reports success, and the ref check that guards it

- `land_nested_branches`, repository without the leaf branch (`continue`): `git show-ref --verify
  refs/heads/<feature>` fails (`_has_branch`), so there is nothing to land.
- `land: manual`, skipped as merged (`continue`): `git merge-base --is-ancestor <feature> refs/heads/<ib>`
  or `... refs/remotes/<remote>/<ib>` (`_merged_somewhere`). Otherwise it returns not-ok with the command.
- `land: push`, already merged (`_land_one` returns `None` early): after `git fetch <remote>`,
  `git merge-base --is-ancestor <feature> refs/remotes/<remote>/<ib>`.
- `land: push`, landed (`[ok] ... pushed to <remote>`): the exit code of
  `git push <remote> HEAD:refs/heads/<ib>` from the merge made on the fetched `refs/remotes/<remote>/<ib>`.
  The remote refuses a non-fast-forward. This code is unchanged from before this leaf (push behaviour is
  out of scope).
- `land: local`, already merged (`_land_one_locally` returns `None` early):
  `git merge-base --is-ancestor <feature> refs/heads/<ib>`.
- `land: local`, landed (`[ok] ... into local <ib>`), guarded in order by:
  - `symbolic-ref -q HEAD == refs/heads/<ib>` in the checkout that held `<ib>` (if any);
  - `git update-ref refs/heads/<ib> <merge> <old>` (compare-and-swap);
  - the same `symbolic-ref` re-check, plus `read-tree -m -u <old> <merge>` in that checkout, with the ref
    put back on failure;
  - finally `git merge-base --is-ancestor <merge> refs/heads/<ib>`.
- `land_nested_branches` returns `(True, "")` only when every configured repository reached one of the
  outcomes above and no manual repository is pending.

## Added

- `NestedRepo.land`, `.base`, `.refuse_behind` fields: A1, per-entry modes with defaults matching today.
- `nested_repos.nested_base_ref()`: one place that picks the local or remote integration ref, for worktree tips and merge bases (A3).
- `_source_and_tip` guard: base local with no local `<ib>` is refused (no silent fall back to the remote).
- `_source_and_tip` guard: `refuse_behind_remote` refuses a local `<ib>` that is behind its remote-tracking one (A3).
- End-of-module re-export in `nested_repos.py`: existing callers keep importing landing/unpushed names from there (A4).
- `specy_road/nested_repos_land.py`: new module; landing and unpushed functions moved verbatim, plus the new modes (A4).
- `nested_repos_land._merge_in_temp_tree()`: shared temporary detached worktree merge for push and local.
- `nested_repos_land._land_one_locally()`: `land: local` (A2).
- Its guards: no local `<ib>`; already merged (skip); `<ib>` checked out dirty (refuse); checkout moved during the merge (refuse); `update-ref` with old value (CAS).
- `nested_repos_land._checked_out_in()`: find the worktree holding `<ib>`, so its checkout is checked and moved with the ref.
- `nested_repos_land._merged_somewhere()`: the manual-mode "already merged" check against the local or remote-tracking `<ib>`.
- Branch in `land_nested_branches`: `land: manual` collects the merge commands and returns not-ok (A2).
- Schema: `land`, `base`, `refuse_behind_remote` on the object item; the `nested_repos` description is updated.
- Docs: the `land`/`base`/`refuse_behind_remote` section, a "never push" example, and the finish bullet reworded.
- `tests/test_nested_repo_land_modes.py`, 11 tests:
  - schema accepts and refuses values;
  - defaults;
  - local, branch checked out: no push, and the checkout moves;
  - local, branch not checked out: the ref moves (`update-ref`);
  - local, dirty checkout refused, nothing moves;
  - manual: stops with the command and no push, then passes after a manual merge;
  - finish exits 1 with the manual message;
  - base local contains a local-only commit;
  - base remote starts at the remote tip;
  - base local behind its remote: refused only with the flag (2 cases).
- Mocks: none.
- Fix round 1 `nested_repos_land._follow_in_checkout()`: updates the holding checkout's files after the ref
  moves, only while it still has `<ib>`, and puts the ref back by compare-and-swap on failure (R1).
- Fix round 1 guard: refuse when the checkout that held `<ib>` switched branch or detached during the merge (R1).
- Fix round 1 guard: after the move, `merge-base --is-ancestor <merge> refs/heads/<ib>` before success (R1).
- Fix round 1 `shlex.quote` on the manual merge command and the worktree-remove hint (R2).
- Fix round 1 tests:
  - `test_land_local_refuses_when_the_checkout_leaves_the_integration_branch_during_the_merge`
    (2 cases, real hook; R1);
  - `test_the_printed_manual_command_runs_for_a_path_with_spaces` (runs the printed command; R2).
