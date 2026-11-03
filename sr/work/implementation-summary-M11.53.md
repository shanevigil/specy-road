# Implementation summary: M11.53 `pickup-into-worktree`

## What changed

- **A1** — `do-next-available-task --worktree` (new flag in `do_next_task_args.py`). Run in the main checkout on the integration branch, it syncs, registers, commits and pushes the claim exactly as the default path does. Then, instead of `git checkout -b`, it creates the leaf's branch with `git worktree add -b feature/rm-<codename> work/.worktrees/<codename> <base>` (or `git worktree add <path> <branch>` when the branch already exists, the resume case). The main checkout stays on the integration branch. The brief is copied into the worktree's `work/`, and the prompt and `on_complete` session file are written there, because the leaf's agent and `finish-this-task` run in that worktree. The F-014 rollback is unchanged: the worktree step is passed to `push_and_branch_with_self_heal` as the create/adopt callbacks, so a failed `worktree add` still strips the claim. A path already at `work/.worktrees/<codename>` is refused before anything is claimed.
- **A2** — pickup run inside a linked worktree is refused at the start of `main`, before validation or sync, unless `--local` is given without `--worktree`. The message names `--worktree` from the main checkout and the `--local` alternative. `--local` inside a worktree behaves as before.
- **Docs** — `docs/git-workflow.md` has a "Worktree flow" paragraph after the default-path coordination contract, covering `--worktree`, the refusal inside a linked worktree and the `--local` alternative. The "While working" bullet on worktrees points to it.

`do_next_task.py` was at 397 of 400 lines, so the checkout callbacks moved into `do_next_task_pickup_helpers.branch_fns`, which serves both modes. The module-level `_checkout_new_branch` / `_checkout_existing_branch` and one section banner are gone. Behaviour without `--worktree` is the same (the same `checkout -b` / `checkout` git calls). `test_pickup_git_order_after_sync` still pins that.

## Touch zones (confirmed)

`specy_road/bundled_scripts/do_next_task.py`, `specy_road/bundled_scripts/do_next_task_args.py`, `specy_road/bundled_scripts/do_next_task_pickup_helpers.py`, `tests/`, `docs/git-workflow.md`. Nothing outside them was needed. Linked-worktree detection reuses `specy_road.worker_adapters.linked_worktree`, and the worktree's project root reuses `runtime_paths.project_prefix`.

## Verification

- `python -m pytest -q tests/test_pickup_worktree.py`: 4 passed
- `python -m pytest -q -n 8 -p no:cacheprovider`: 3211 passed, 2 skipped (serial run exceeds 10 min)
- `specy-road file-limits`: OK
- `python scripts/check_test_private_imports.py`: 0 new

## Added

- `do_next_task_args.py` `--worktree` flag: the A1 mode.
- `do_next_task_pickup_helpers.refuse_linked_worktree`: the A2 guard. A pushing pickup inside a linked worktree exits with a message naming `--worktree` from the main checkout and `--local`.
- `do_next_task_pickup_helpers.leaf_worktree_path`: resolves `work/.worktrees/<codename>` and refuses an existing directory before the claim, so a predictable failure never goes through rollback.
- `do_next_task_pickup_helpers.branch_fns`: one source for the create/adopt callbacks. They do a checkout without a worktree and `git worktree add` with one. This replaces the two removed `do_next_task` functions and keeps that file under the 400-line limit.
- `do_next_task_pickup_helpers.worktree_work_dir`: the worktree's project root and `work/`, with the brief copied in, so the prompt, session file and brief sit where the leaf's agent runs.
- `do_next_task._finalize_pickup` `worktree` parameter and branch: routes the branch step and the prompt/session/footer paths to the worktree, and prints a `worktree:` line.
- `do_next_task._push_and_branch_with_self_heal` `worktree`/`base` parameters: pick the callbacks through `branch_fns`.
- `tests/test_pickup_worktree.py::test_worktree_pickup_claims_on_the_remote_and_leaves_the_main_checkout_alone`: A1 end to end with a bare origin. Checks that the main checkout stays on `main`, the claim is on `main` and `origin/main`, the worktree holds the feature branch, and the brief and session file are in the worktree.
- `tests/test_pickup_worktree.py::test_worktree_pickup_refuses_an_existing_directory_before_claiming`: the pre-claim refusal leaves nothing claimed.
- `tests/test_pickup_worktree.py::test_pickup_inside_a_linked_worktree_names_worktree_from_the_main_checkout`: A2, both with and without `--worktree`, with nothing claimed.
- `tests/test_pickup_worktree.py::test_local_pickup_inside_a_linked_worktree_is_not_refused_as_a_worktree`: `--local` keeps its old path through the guard.
- Mocks: none. The new tests reuse the real-git project helpers from `tests/test_baseline_gate_cli.py`.
