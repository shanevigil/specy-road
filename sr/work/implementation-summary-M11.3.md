# Implementation summary: M11.3 — specy-road's own runtime directories never fail the clean-tree checks

Branch `feature/rm-runtime-dirs-not-dirty`, base `189f36c9`.

## What was wrong

Delegation's uncommitted-work check (`worker_ops._launch_locked` via `worker_reconcile._bookkeeping`) and
reconcile's breach list already left out `work/reviews/`, `work/.workers/`, `work/.sessions/` and
`work/.worktrees/`, but kept that list privately as `_STATE_DIRS`. The executor and reviewer
clean-tree preconditions rendered by `role_prompt_rca` excluded only `work/reviews/`, so in a fresh
clone or linked worktree whose committed `.gitignore` predated the rule (the rc2 field case), the
`work/.workers/` and `work/.sessions/` files specy-road itself writes made the precondition list
changes the agent did not make. `init project`, `refresh-stubs` and `apply_agent_ignores` already
ignore those paths in new and refreshed projects; nothing proved it.

## What changed

- `specy_road/agent_ignores.py`: one shared constant `RUNTIME_WORK_DIRS` (reviews, sessions,
  workers, worktrees). `GITIGNORE_LINES` is built from it, same entries in the same order, so the
  managed block adopters already have is byte-identical.
- `specy_road/worker_reconcile.py`: `_bookkeeping` reads `RUNTIME_WORK_DIRS` instead of its private
  copy; `worker_ops` imports `_bookkeeping` and needed no change.
- `specy_road/bundled_scripts/role_prompt_rca.py`: `dirty_check` (executor, rca and other roles) and
  `reviewer_precondition` add one `:(top,exclude)` pathspec per runtime dir, prefixed for the nested
  layout, and the prose that lists what the command leaves out names them.
- `docs/git-workflow.md`: the `track_worker_logs` paragraph says the checks leave the runtime
  directories out in any checkout, so a fresh clone starts clean even where the rule is missing.
- `tests/test_runtime_dirs_not_dirty.py` (new).

The commands keep the rule that any other change, tracked or untracked, stops the agent.

## Acceptance

- **A1** — pass. `test_the_rendered_precondition_passes_over_runtime_state_in_every_lane` renders the
  executor and reviewer prompts against a repo whose `.gitignore` has only `work/reviews/`, runs the
  exact `git status` command each prompt gives, in the main checkout, a `git worktree add` lane and
  a `git clone` lane, with all four runtime dirs populated: empty output; one stray `notes.md`:
  listed. Red without the `role_prompt_rca` change in all three lanes (see `--red-green`).
  Delegation's check is covered by the A3 test.
- **A2** — pass. `test_init_project_makes_git_ignore_the_runtime_dirs` runs `init project` in a fresh
  git repo and asserts `git check-ignore` for each runtime path;
  `test_refreshing_an_old_scaffold_makes_git_ignore_the_runtime_dirs` applies the managed block
  (what `refresh-stubs` and `init` run) to the old scaffold and asserts the same.
- **A3** — pass. `test_delegate_in_a_fresh_clone_passes_over_runtime_state_but_not_an_unrelated_file`
  clones the old-scaffold repo, populates the runtime dirs, shows `delegate` refuses while an
  unrelated untracked file exists, succeeds once it is gone, and that afterwards the executor's
  rendered check is empty over the brief delegation wrote plus the runtime state, and non-empty
  again with the unrelated file.

## Touch zones

As listed: `specy_road/bundled_scripts/role_prompt_rca.py`, `specy_road/worker_reconcile.py`,
`specy_road/agent_ignores.py`, `docs/git-workflow.md`, `tests/`. Not edited though listed:
`specy_road/worker_ops.py` (shares `_bookkeeping`), `specy_road/templates/project/` (its
`.gitignore` already carries the four directories).

## Verification

- `uvx ruff@0.17.3 check specy_road tests scripts` = 0
- `specy-road file-limits` = 0
- `python scripts/check_test_private_imports.py` = 0 (0 new)
- `python -m pytest tests/test_runtime_dirs_not_dirty.py tests/test_agent_ignores.py tests/test_worker_cli_fixes.py tests/test_worker_cli.py tests/test_worker_reconcile_contract.py tests/test_models_and_prompt.py tests/test_init_project_gitignore.py tests/test_project_layouts.py -q` = 0 (139 passed)
- `python -m pytest -q` = 0 (3006 passed, 2 skipped)
- Red-green: `python -m pytest tests/test_runtime_dirs_not_dirty.py::test_the_rendered_precondition_passes_over_runtime_state_in_every_lane -q` = 1 with `role_prompt_rca.py` at `189f36c9`, 0 with the change.

## Added

- `RUNTIME_WORK_DIRS` constant (`agent_ignores.py`): the one list the gitignore block, reconcile and the prompts share, so the three cannot drift again.
- `runtime_excludes(prefix)` helper (`role_prompt_rca.py`): renders the pathspecs once for `dirty_check` and `reviewer_precondition`.
- `runtime_dirs_prose(prefix)` helper (`role_prompt_rca.py`): names the directories in both preconditions' prose without repeating the list.
- Branches or guards: none.
- Mocks: none; every test runs real git and the fake harness script from `tests/test_worker_cli.py`.
- `test_executor_and_reviewer_checks_exclude_every_runtime_dir`: the command string carries each dir, prefixed and unprefixed.
- `test_the_rendered_precondition_passes_over_runtime_state_in_every_lane` (main, worktree, clone): A1 end to end against the rendered prompts.
- `test_delegate_in_a_fresh_clone_passes_over_runtime_state_but_not_an_unrelated_file`: A3.
- `test_init_project_makes_git_ignore_the_runtime_dirs`: A2 for `init project`.
- `test_refreshing_an_old_scaffold_makes_git_ignore_the_runtime_dirs`: A2 for a refreshed old scaffold.
- Fixture helpers `_porcelain`, `_touch`, `_old_scaffold`, `RUNTIME_FILES` in the new test file: run a prompt's shell command, create a file, build the pre-rule repo.
