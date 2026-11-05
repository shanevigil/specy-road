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
    that checkout must be clean (tracked files): a dirty one is refused, naming it, before anything merges. A
    clean one is checked that it is still at `<old>`, then fast-forwarded to the merge so its working tree
    follows the ref.
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
- **A4:** `nested_repos.py` is now 307 lines and the new `nested_repos_land.py` is 224 lines.
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
