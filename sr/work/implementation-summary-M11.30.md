# Implementation summary: M11.30 — Leaf worktrees get the project's environment set up

Branch `feature/rm-worktree-env-setup`, base `94a6078b`, with `origin/WIP/improvements-0-3-1` merged at `10367ee6` (fast-forward). That merge added the touch zones `specy_road/worker_ops_launch.py` and `specy_road/bundled_scripts/doctor_env_setup.py`. Code commit `8e616b1c`.

## What changed

**A1: config, pickup, delegate.**

- **Config.** `roadmap/git-workflow.yaml` takes an optional `env_setup: {cmd, copy}`. The schema (`git-workflow.schema.json`, new `$defs/envSetupPath`) requires at least one key and rejects unknown keys. `cmd` is a non-empty string. Each `copy` item is either a path, copied to the same path, or `{from, to}`. Paths are project-relative and may not be absolute; `../` reaches the git root in the nested layout.
- **Logic.** New module `specy_road/worktree_env.py`:
  - `env_setup_config` reads the setting through `git_workflow_config.load_git_workflow_config`.
  - `setup_worktree_env(repo_root, leaf_root)` copies each item from the main checkout's project root, then runs `cmd` with the shell at the worktree's project root, capturing stdout and stderr together. It returns one line per step. At the first failure it raises `EnvSetupError`, whose message carries the exit code and output, says the worktree stays, and says the worktree is not set up again.
  - A missing copy source is a failure, so a pin file can never be skipped silently. That silent skip is the field bug A3 names.
- **Pickup.** `do_next_task_pickup_helpers.worktree_work_dir` runs only on the `--worktree` path, after `git worktree add`. It now calls `setup_worktree_env`, prints `env_setup: …` lines, and turns `EnvSetupError` into `SystemExit("error: …")`. The claim is already pushed by then, so the error says it stays.
- **Delegate.** `worker_ops_launch._launch_locked` notes whether `work/.worktrees/<codename>` existed before `_worktree_for`. It runs setup only when the returned tree is that path and the path did not exist before, meaning delegate created it.
  - A worker in the main checkout, an explicit `--worktree`, a chore's worktree, or an existing worktree is never set up.
  - Setup runs after the nested repositories' worktrees are added and before the uncommitted-work check. `EnvSetupError` becomes `WorkerError`, so nothing is launched.
  - `_worktree_for`'s signature and return value are unchanged.

**A2: doctor, docs, tests.**

- **Doctor.** New module `specy_road/bundled_scripts/doctor_env_setup.py`, whose `report_checkout(root)` runs before the listing:
  - It calls `report_gate_mismatch` exactly as before.
  - `report_env_setup` prints the configured copies and command, reports each copy source missing from the main checkout as an error, runs `cmd` in the main checkout's project root, and prints "succeeds" or the error with its output.
  - `report_python_mismatch` is the A3 check below.
  - An error makes doctor exit 1 after the listing, as a gate mismatch already did.
  - The main checkout is the first entry of `git worktree list`, plus the project prefix.
  - `doctor.py` was at 400 lines. Its `report_gate_mismatch` import and call became the `report_checkout` import and call, so it stays at 400.
- **Docs.** `docs/git-workflow.md` gains a quickstart pointer, a field paragraph and a new "Worktree environment (`env_setup`)" section. The section gives the uv workspace example (`uv sync --all-packages --all-groups --locked`) and warns that a plain `uv sync` in a workspace removes other members' packages. It also covers when setup runs, failures, which ignored files are needed, and what doctor reports.

**A3: copies and the Python check.** `copy` is part of A1 above. `doctor_env_setup.report_python_mismatch` reads the Python version from each worktree's `.venv/pyvenv.cfg`: `version_info` (uv, virtualenv) or `version` (venv), at the worktree's project root first, else its git root. It compares major.minor with the main checkout's `.venv` and prints a `warning:` for each linked worktree that differs. It is silent when the main checkout has no `.venv`. A mismatch is a warning and does not change the exit code.

## Known limits

- **Pickup order.** Pickup sets up the environment before nested repositories get their worktrees. In `do_next_task._finalize_pickup`, `worktree_work_dir` runs before `announce_nested_worktrees`, and `do_next_task.py` is outside the zones. A setup command that needs a nested repository therefore works through `worker delegate`, not pickup. The docs say so.
- **No retry.** A failed setup leaves the worktree in place, and a later delegate does not set it up again. The error and the docs say to finish the setup by hand or remove the worktree and delegate again. Removing the worktree automatically would also have to remove nested worktrees inside it.
- **Doctor changes the main checkout.** Doctor runs `cmd` in the main checkout, so it can change that checkout's environment (for example `uv sync`). The docs say it runs there.

## Touch zones (final)

- **Edited, in zones:** `specy_road/worker_ops_launch.py`, `specy_road/bundled_scripts/do_next_task_pickup_helpers.py`, `specy_road/bundled_scripts/doctor.py`, `specy_road/bundled_scripts/doctor_env_setup.py` (new), `specy_road/templates/project/schemas/git-workflow.schema.json`, `docs/git-workflow.md`, `tests/test_worktree_env_setup.py` (new).
- **New module outside the listed zones:** `specy_road/worktree_env.py`, added under the file-limits rule. The setting's reader would have gone in `specy_road/git_workflow_config.py`, which is at 395 of 400 lines; pickup, delegate and doctor all import it. Add it to this leaf's touch zones.
- **Listed but unchanged:** `specy_road/git_workflow_config.py`; the reader lives in `worktree_env.py` and calls `load_git_workflow_config`. `specy_road/worker_ops.py` is a re-exporting facade since M11.59.
- **Not changed:** `sr/schemas/git-workflow.schema.json`, the toolkit roadmap's own schema copy. It already differed from the template before this leaf. No `suggested_prompts/*.md` describes `git-workflow.yaml` fields.

## Verification

- `python -m pytest -n 4 -p no:cacheprovider tests/test_worktree_env_setup.py`: 15 passed.
- `python -m pytest -n 4 -p no:cacheprovider` over `tests/test_worktree_env_setup.py`, `test_doctor.py`, `test_doctor_version_skew.py`, `test_gate_config_agree.py`, `test_pickup_worktree.py`, `test_nested_repo_worktrees.py`, `test_nested_repo_finish.py`, `test_worker_cli.py`, `test_baseline_gate_cli.py`, `test_schema_revision.py` and `test_refresh_schemas.py`: 135 passed.
- `python -m pytest -n 4 -p no:cacheprovider` (full suite): 3673 passed, 2 skipped.
- `specy-road file-limits`: OK.

## Added

- `specy_road/worktree_env.py`: new module, so pickup, delegate and doctor share one reader and runner (`git_workflow_config.py` had no room).
- `worktree_env.EnvSetupError`: one failure type that pickup turns into `SystemExit` and delegate into `WorkerError`.
- `worktree_env.env_setup_config`: reads `env_setup`, giving `None` when it is unset or the config is unreadable, the same convention as the other optional fields.
- `worktree_env.copy_pairs`: turns a bare path or `{from, to}` into `(from, to)`; used by the setup and by doctor.
- `worktree_env.run_setup_cmd`: runs the shell command with stdout and stderr captured together, so a failure can quote the output (A1). Shared with doctor.
- `worktree_env.setup_worktree_env`: does the copies, then the command, in a new worktree (A1, A3).
- Guard in `setup_worktree_env`: a missing copy source fails instead of being skipped. A silently missing pin file is the field bug.
- Branch in `do_next_task_pickup_helpers.worktree_work_dir`: runs the setup for the pickup worktree and turns a failure into `SystemExit` (A1).
- Branch in `worker_ops_launch._launch_locked` (`default`, `fresh`): sets up only a worktree this delegate created (A1: "when delegate … creates it").
- `specy_road/bundled_scripts/doctor_env_setup.py`: new module for doctor's checkout checks (`doctor.py` is at the cap).
- `doctor_env_setup._worktree_tops`: lists worktree top directories, main checkout first, to find the main checkout and the linked worktrees.
- `doctor_env_setup.env_python`: reads the Python version from `.venv/pyvenv.cfg` (A3).
- `doctor_env_setup._minor`: major.minor, so patch releases do not warn.
- `doctor_env_setup.report_env_setup`: reports the setup and whether it succeeds in the main checkout (A2).
- `doctor_env_setup.report_python_mismatch`: warns on a worktree Python mismatch (A3).
- `doctor_env_setup.report_checkout`: the gate-mismatch check plus the two above, called once from `doctor.cmd_doctor`, which keeps `doctor.py` at 400 lines.
- Schema: `env_setup` property and `$defs/envSetupPath` (A1, A3).
- `tests/test_worktree_env_setup.py`, 15 tests:
  - Schema: forms accepted and rejected.
  - Pickup: success with both copy forms and the command; failure with its output; a missing copy source; no setting.
  - Delegate: success; failure that launches nothing, then no rerun on the existing worktree; no setting.
  - Doctor: success; failure plus a missing source; exit 1 through the CLI; no setting.
  - Python check: mismatch warns and the same minor does not, plus the `.venv` lookup order.
- Test helpers `_ignored_files`, `_cfg`, `_worker_repo`, `_delegate` and `_venv`: fixtures local to that file. Ignored files go in `.git/info/exclude`, which every linked worktree shares.
- Mocks: none. Tests run the real CLI, `worker delegate` with the existing fake harness, and real shell commands.
