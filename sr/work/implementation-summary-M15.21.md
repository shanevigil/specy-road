# Implementation summary: M15.21

Linked worktrees: commands resolve the enclosing worktree, and `env_setup` handles symlinked environments.

## Final touch zones

As widened by the coordinator (WIP 17af42ad): `specy_road/runtime_paths.py`, `specy_road/worker_ops_launch.py`,
`specy_road/worktree_env.py`, `docs/orchestration-worktrees.md`, `tests/`,
`specy_road/templates/project/schemas/git-workflow.schema.json`, `specy_road/bundled_scripts/doctor_env_setup.py`,
`specy_road/worker_ops_message.py`. All changes fall inside these zones.

Not changed (outside the zones, so a follow-up):
- `sr/schemas/git-workflow.schema.json`: this checkout's own copy of the schema. It does not have `link` yet.
- `docs/git-workflow.md`: its "Worktree environment (`env_setup`)" section still describes `{cmd, copy}` only.
  The new `docs/orchestration-worktrees.md` covers `link`.

## A1: the enclosing worktree wins

- `runtime_paths.project_root`: when `SPECY_ROAD_REPO_ROOT` is set, `enclosing_worktree_root` asks git
  (`rev-parse --path-format=absolute --show-toplevel --git-common-dir`) for the worktree top and common dir of
  both the working directory and the named path. If they are different worktrees with the same common dir, it
  returns the same project-relative path in the working directory's worktree, even when that directory is
  missing there (rework R4: the command then fails on that path; it is never sent back to the main checkout).
  It prints nothing. If the working directory is in another repository, outside git, or in the same worktree, the
  named path is returned as before.
- `worker delegate` (`worker_ops_launch.worker_env`) sets `SPECY_ROAD_REPO_ROOT` in the harness environment to
  the worker's project root (`<worktree>/<prefix>`). It uses the `Launch.env` overlay, which the wrapper
  applies over `harness_env`. `worker message` and `resume` (`worker_ops_message._send`) set it the same way,
  so a resumed turn keeps it.
- Test: `ready` runs in a linked worktree with no `--repo-root`, the variable naming the main checkout, and cwd
  in the worktree. It writes a valid READY at the worktree's HEAD. Red-green: without the `runtime_paths`
  change this test fails (exit 1), because it resolves the main checkout on `dev`.

## A2: `env_setup.link`

- Schema: `env_setup.link` is an array of `envSetupPath`.
- `worktree_env.link_into` symlinks each path from the main checkout's project root to the same
  project-relative path in the new worktree. The steps run in order: copy, then link, then cmd. The source is
  bounded by the main checkout's git root. The target (`link_target`) has its parent resolved and bounded by the
  leaf worktree, so a symlinked directory on the way cannot carry the link out (rework R1); its final component
  is not followed, so an existing or dangling link there is still refused. A missing source, or a target
  that already exists, stops with the usual "worktree stays" note. Then `exclude_links` appends an anchored
  `/<git-root-relative path>` line (`exclude_pattern` escapes `\ * ? [` and trailing spaces, rework R2), if
  not already there, to the file `git rev-parse --git-path info/exclude`
  names. Git keeps that file in the common git dir, so it is shared by every worktree and the main checkout.
  There the line matches the real, already-ignored directory.
- `worker delegate`'s clean-tree check also skips a `??` entry that is a declared link path **and** a symlink
  resolving to that path in the main checkout (`linked_status_paths`, rework R3), so a symlink made by hand in an
  existing worktree does not block a launch, while an ordinary file or directory of that name still does.
- `doctor` lists links (`; link a, b`, only when set) and reports a missing or out-of-bounds link source as an
  error, as it does for copy sources.
- Test: `.gitignore` holds `node_modules/` and `.venv/` (directory-only patterns). After setup,
  `git status --porcelain --untracked-files=all` is empty in both the worktree and the main checkout.

## A3: docs

New `docs/orchestration-worktrees.md`. It covers root resolution, where `env_setup` lives
(`roadmap/git-workflow.yaml` at the project root), the command and link forms, why links go in
`info/exclude` (common dir), and that copying environments is out of scope.

## Rework (review by `gpt-6.1-sol` of 063ec92a)

- R1 (class: a write through a symlinked path component): `link_target` resolves the parent before bounding.
- R2 (class: a literal name written as a git pattern): `exclude_pattern` escapes pattern syntax; a name with a
  newline is refused, since no exclude line can hold it.
- R3 (class: an exemption decided by name, not by what is on disk): the exemption needs a symlink to the source.
- R4 (class: falling back to the named checkout): the enclosing worktree's path is returned even when missing.
- R5 (class: assertions on how often a mock was called): `len(launches) == 1` is now an active worker record
  (`active_for_node`); `[launch] = launches` in the delegate-env test is now `launches[-1]`.
- Red-green: the four new regression tests fail (4 failed) with `worktree_env.py` and `runtime_paths.py` at
  063ec92a, and pass with the fix.

## Probes

- Link target with `assets` symlinked out of the worktree: refused, nothing written outside (test).
- Copy targets: already bounded by a full `resolve()` (`bounded_path`), so a symlinked parent or final component
  pointing out is refused; unchanged.
- Link and copy sources: bounded by a full `resolve()` against the main checkout's git root; unchanged.
- Link target `x/..` and the worktree top itself: refused by `link_target`.
- `mkdir` of the link's parents: runs only after the resolved parent is bounded.
- Exclude lines for `env[1]` and `a*b?`: status clean after setup, and `env1` / `aXbY` still untracked (test).
- Other places writing a git pattern in this change: none besides `exclude_pattern`.
- `git status` path quoting for odd names: `status_entries` uses `-z`, so the compared path is literal.
- Delegate with an ordinary file named `node_modules` declared under `link`: refused, no worker record, file kept (test).
- Delegate with a hand-made symlink to the main checkout's `node_modules`: still accepted (existing test).
- Other exemptions in the clean-tree check (`_bookkeeping`, `in_nested`): not part of this change; unchanged.
- `worker_turn_check` (`status_entries` after a turn, outside the zones): does not use the link exemption; unchanged.
- `enclosing_worktree_root` with the project directory missing in the lane: returns the lane path (test).
- Its other `return named` branches (cwd outside git, named path missing or outside git, same worktree, other
  common dir): the cases A1 says keep today's behaviour; unchanged.
- Other mock call counts in `tests/test_linked_worktrees_root.py`: the `[launch] = launches` unpack; replaced.

## Verification

- Full suite `pytest -n 4`: 4035 passed (after the rework).
- Targeted pytest (16 files, `-n 4`): 190 passed (first round).
- `specy-road file-limits`: OK.
- `ruff check` on the changed Python files: clean. `setup_worktree_env` and `report_env_setup` went over the
  C901 limit; I split out `link_into` and `_missing_sources` to bring them back under it.

## Added

- `runtime_paths._worktree_and_common_dir`: one git call for a checkout's worktree top and common git dir (A1).
- `runtime_paths.enclosing_worktree_root`: the A1 rule (same common dir, different worktree → the enclosing one).
- Branch in `project_root`: the env-var value goes through `enclosing_worktree_root`.
- `worker_ops_launch.worker_env`: adds `SPECY_ROAD_REPO_ROOT=<worker project root>` to a `Launch.env` (A1, delegate).
- Call in `worker_ops_message._send`: resumed turns get the same variable as the first turn.
- Guard in `_launch_locked`'s clean-tree check: `??` entries that are declared link paths are not dirty (A2).
- `worktree_env.link_paths`: reads `env_setup.link`.
- `worktree_env.linked_status_paths`: link paths as `git status` names them, for the delegate guard; only those
  that are symlinks resolving to their main-checkout source (rework R3).
- `worktree_env.link_target`: the link's place in the leaf, parent resolved and bounded, final component not
  followed; refuses `..`, the worktree top and newlines (rework R1, R2).
- `worktree_env.exclude_pattern`: escapes gitignore pattern syntax in an exclude line (rework R2).
- `worktree_env.exclude_links`: appends anchored exclude lines to the common `info/exclude` (A2).
- `worktree_env.link_into`: makes the symlinks, with bound/missing/exists guards (A2). It was split out of
  `setup_worktree_env` for C901.
- `bounded_path(verb=...)`: so a link refusal says "cannot link", not "cannot copy".
- `doctor_env_setup._missing_sources`: copy and link source checks, split out of `report_env_setup` for C901.
- Doctor output: a `; link …` line segment, and missing link sources reported as errors.
- Schema: `env_setup.link` property.
- Mocks: `_capture_spawn` in the new tests replaces `worker_ops_launch.spawn` and `acquire_lease`, so delegate's
  launch is captured without starting a harness or touching a remote.
- Tests (`tests/test_linked_worktrees_root.py`):
  - `test_ready_in_a_linked_worktree_with_the_variable_naming_the_main_checkout`: A1's required test.
  - `test_the_enclosing_worktree_is_resolved_silently`: a nested path is kept, nothing is printed, and the main
    checkout is unchanged.
  - `test_a_working_directory_in_another_repository_keeps_the_variable`: today's behaviour outside the repository.
  - `test_delegate_sets_the_variable_to_the_workers_worktree`: delegate's environment.
  - `test_link_symlinks_the_environments_and_leaves_the_worktree_clean`: A2's required clean-status test.
  - `test_link_refuses_a_missing_source_and_a_path_past_the_git_root`: link guards.
  - `test_doctor_lists_the_links_and_a_missing_source`: doctor reporting.
  - `test_delegate_ignores_a_declared_link_made_by_hand`: the clean-tree guard, which needs no exclude line;
    now asserts an active worker record instead of a spawn count (rework R5).
  - `test_delegate_refuses_an_ordinary_file_with_a_declared_link_name`: rework R3, through delegate.
  - `test_a_project_missing_from_the_enclosing_worktree_is_not_redirected_to_the_main_checkout`: rework R4.
  - `test_link_refuses_a_parent_that_is_a_symlink_out_of_the_worktree`: rework R1, no external write.
  - `test_link_excludes_a_name_with_pattern_characters_literally`: rework R2, clean status and exact-name match.
