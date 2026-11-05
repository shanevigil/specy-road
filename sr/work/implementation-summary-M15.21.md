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
  returns the same project-relative path in the working directory's worktree, if that directory exists. It
  prints nothing. If the working directory is in another repository, outside git, or in the same worktree, the
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
  bounded by the main checkout's git root and the target by the leaf worktree. A missing source, or a target
  that already exists, stops with the usual "worktree stays" note. Then `exclude_links` appends an anchored
  `/<git-root-relative path>` line, if not already there, to the file `git rev-parse --git-path info/exclude`
  names. Git keeps that file in the common git dir, so it is shared by every worktree and the main checkout.
  There the line matches the real, already-ignored directory.
- `worker delegate`'s clean-tree check also skips `??` entries that are declared link paths
  (`linked_status_paths`), so a symlink made by hand in an existing worktree does not block a launch.
- `doctor` lists links (`; link a, b`, only when set) and reports a missing or out-of-bounds link source as an
  error, as it does for copy sources.
- Test: `.gitignore` holds `node_modules/` and `.venv/` (directory-only patterns). After setup,
  `git status --porcelain --untracked-files=all` is empty in both the worktree and the main checkout.

## A3: docs

New `docs/orchestration-worktrees.md`. It covers root resolution, where `env_setup` lives
(`roadmap/git-workflow.yaml` at the project root), the command and link forms, why links go in
`info/exclude` (common dir), and that copying environments is out of scope.

## Verification

- Targeted pytest (16 files, `-n 4`): 190 passed.
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
- `worktree_env.linked_status_paths`: link paths as `git status` names them, for the delegate guard.
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
  - `test_delegate_ignores_a_declared_link_made_by_hand`: the clean-tree guard, which needs no exclude line.
