# Implementation summary — M16.2.3: git queries and registry I/O go through one helper each

Branch `feature/rm-git-queries-and-registry-i-o-go-through-one-helper-each`, base `4c147385`, code commit `035ae978`.

## What changed

### A1 — git helpers in `git_subprocess`

`specy_road/git_subprocess.py` now provides:

- `git_root(start=None)`: moved from `runtime_paths`. It now reads bytes (through `git_path`) instead of stripped text, so a directory name with an edge space, a newline or non-UTF-8 bytes comes back unchanged. For an ordinary path the result is the same resolved path as before.
- `is_worktree_root(path, branch=None)`: `path` is a directory, `git_root(path) == path.resolve()`, and when `branch` is given it is the checked-out branch.
- `current_branch_name` is unchanged and now used everywhere.
- Bytes primitives taken from the private wrappers: `run_bytes` (with a `GitBytes` result whose `.checked(args, ok)` raises `GitError`), `git_bytes`, `git_out` and `git_path` (resolved).
- `git_run` (output passed through) and `git_capture` (raw stdout, raises), moved unchanged from `repo_ops`.

Private wrappers removed:

| Module | Removed | Replaced by |
|---|---|---|
| `worktree_delete_set` | `git_run`, `git_out`, `git_path`, `is_repo_top` | `run_bytes`, `git_out`, `git_path`, `is_worktree_root` (callers in `worktree_prune` switched) |
| `bundled_scripts/update_specy_road` | `_git_output`, `_git_succeeds`, `_git_toplevel`, `_remote_url`; `_working_tree_clean`'s own `subprocess.run`; the `subprocess.check_call` git calls | `git_root`, `git_text`, `git_checked`, `git_run` |
| `bundled_scripts/repo_ops` | `git_run`, `git_capture` | the same functions in `git_subprocess`. The six importers now import them from there; `repo_ops.current_branch` is unchanged (see "Left as is") |
| `ignore_report` | its own `subprocess.run` and `IgnoreCheckSkipped` | `run_bytes(..., env=scratch_git_env(_isolated), stdin=...).checked(args, ok)`; `attempt` catches `GitError` |
| `integrity` | `_git_bytes` | `git_bytes` (and in `red_green`, which imported the private one) |
| `pm_publish` | `_git_lines` | `(git_text(args, repo_root) or "").splitlines()`; the short-SHA read becomes `git_text(...) or None` |
| `runtime_paths` | `git_root`, `git_path` | moved to `git_subprocess`; `_worktree_and_common_dir` uses `git_root` |
| `nested_repos` | `is_repo_top` (a second copy) | `is_worktree_root` (callers in `nested_repos_land`, `sibling_repos`, `review_gate_ready`) |

These worktree-root checks now call `is_worktree_root`: `worker_ops_launch._check_tree`, `chore_cli.start`, `worktree_prune` (formerly `worktree_delete_set.is_repo_top`), `nested_repos`, `nested_repos_land`, `sibling_repos`, `review_gate_ready` and `role_prompt_cli.worktree_problem`. `session_overlap.edit_state` asks for the enclosing checkout, not a root check, so it calls `git_root`: a recorded worktree that is a subdirectory still resolves to its top, as before.

These inline `--show-toplevel` and `--show-current` calls were replaced with `git_root` or `current_branch_name`: `runtime_paths`, `worker_process`, `worker_ops_launch`, `review_delegate`, `review_write_check`, `session_presence`, `session_overlap`, `sibling_repos`, `doctor_worktrees`, `specyrd_init`, `nested_repos`, `review_gate_ready`, `worker_turn_check`, `update_specy_road`, `abort_task_pickup`, `review_packet`, `chore_cli` and `role_prompt_cli`. The modules that imported `git_root` from `runtime_paths` now import it from `git_subprocess`; those lines change only the import path.

### A2 — guard test

`tests/test_git_subprocess.py::test_only_git_subprocess_asks_git_for_the_root_or_the_branch` parses every `specy_road/**/*.py` except `git_subprocess.py`. It fails on any string constant that is exactly `--show-toplevel` or `--show-current`, which is how an argument to git is written. Prose such as `role_prompt_rca`'s `cd "$(git rev-parse --show-toplevel)"` is part of a longer string, so the test does not flag it. The test also asserts both cases on inline snippets.

Red at base: run against `4c147385`'s tree, the scan lists 19 modules (abort_task_pickup, chore_cli, review_packet, role_prompt_cli, update_specy_road, doctor_worktrees, nested_repos, review_delegate, review_gate_ready, review_write_check, runtime_paths, session_overlap, session_presence, sibling_repos, specyrd_init, worker_ops_launch, worker_process, worker_turn_check, worktree_delete_set). It lists none at `035ae978`.

### A3 — registry I/O

- The `_save_registry` copies in `finish_task`, `mark_implementation_reviewed` and `abort_task_pickup` are deleted. Each single caller now calls `write_registry(registry_path(ROOT), reg)`.
- The `REGISTRY_REL` copies in `pm_integration_registry`, `registry_remote_overlay_merge` and `review_target` are deleted; those modules import `registry_yaml.REGISTRY_REL`.
- `review_target`'s copy was a `str`, so it and `review_packet` (which imported it from `review_target`) now use `REGISTRY_REL.as_posix()`. The rendered text and the comparisons are unchanged.
- `tests/test_finish_bookkeeping_wiring.py` patched the removed `ft._save_registry`. It now patches `ft.write_registry`, which is the same seam one level down; its assertions are unchanged.

### A4 — parity harness

`tests/parity/` was not edited. It is part of the full suite, which passes.

### A5 — line change (informational)

- Package: +326 −374, net −48 (estimate −110). Most of the gap is docstrings on the moved bytes primitives, kept so the reason each one reads bytes is stated once.
- Tests: net +39.
- `scripts/lean_metrics.py --check` was not run. It runs the full suite three times with 4 workers (about 26 minutes) on a machine other sessions share. The metrics it reports were checked directly instead:
  - Lines over 100 characters: no changed file has more than at base.
  - Ruff quality families on the changed files: `ignore_report` N −1, `tests/helpers.py` PL −1, no rise anywhere.
  - Clone pairs: 9 current, 9 baselined, 0 new.
  - Private imports in tests: OK.
  - `ruff check specy_road tests scripts`: clean.

### A6 — upgrade keeps M22.25's environment and timeout

- `ignore_report._git` is the one place upgrade's ignore note calls git. It still passes `env=scratch_git_env(_isolated)` on every call, with the same 60 s bound (`DEFAULT_TIMEOUT`).
- `run_bytes` does not go through `git_subprocess.run`, so the `test_upgrade_preview` stubs that count `run` calls see the same sequence.
- No other upgrade git call changed. `upgrade.py` only takes `git_root` from its new module.
- These tests pass unchanged: `test_upgrade_never_touches_the_repository_a_git_variable_names` (GIT_DIR / GIT_WORK_TREE / GIT_INDEX_FILE / GIT_COMMON_DIR / GIT_OBJECT_DIRECTORY decoys, dry and real runs), the failed and timed-out scratch-git tests, and the `ls-files` tests.

## Behaviour notes (each checked)

- **Detached HEAD.** Every switched `branch --show-current` caller compared the result to a branch name, or used `or None` / `or ""` / `or 'a detached HEAD'`. `current_branch_name` gives `None` both on a detached HEAD and outside a repository, so each caller produces the same message or value as before.
  - `worker_turn_check.GitState.branch` used to hold `""` when detached and `None` when git failed; it now holds `None` for both. The finding text already prints `(detached)` for either.
  - `repo_ops.current_branch` (`rev-parse --abbrev-ref HEAD`, which returns `HEAD` when detached and raises on failure) is not switched, so its callers keep their behaviour. This is the brief's "If this fails" case.
- **`ignore_report` failure text.**
  - A non-zero exit still produces `git <subcommand>: <last stderr line>` (test_m13_7_notices checks this for `ls-files`).
  - When git never ran (timeout, missing binary), the skip line now reads `git <subcommand>: <error>` instead of the bare exception text.
  - When stdout is non-empty and stderr is empty, the message falls back to stdout.
- **`doctor_worktrees.worktree_findings`.** Outside a git checkout it used to raise `CalledProcessError` from `git_checked`. It now gets `None` from `git_root`, so no worktree compares equal to it. The doctor command only reaches this function inside a checkout.
- **Resolved roots.** `review_write_check`, `review_packet` and `specyrd_init.resolve_repo_root` used git's toplevel without resolving it; `git_root` resolves it. Git already prints a real path, so the value is the same.
- **`worktree_env.exclude_links`.** This keeps the unresolved exclude path, through `git_out`, so a symlinked `info/exclude` is still written through rather than resolved.

## Gates run (all from the worktree)

- `python -m pytest -n 4 -p no:cacheprovider -q`: 7113 passed, 17 skipped.
- `specy-road validate`, `export --check`, `digest --check` with `--repo-root tests/fixtures/specy_road_dogfood`: exit 0.
- `specy-road file-limits`: OK. The warnings are on files this leaf does not touch.
- `ruff check specy_road tests scripts`, `scripts/check_clones.py`, `scripts/check_test_private_imports.py`: OK.

## Touch zones

All edits are under `specy_road/` and `tests/`, which are in the zone list. Files outside the named list that changed:

- **Callers of the removed wrappers:** `worktree_prune`, `red_green`, `nested_repos`, `nested_repos_land`, `sibling_repos`, `review_gate_ready`, `review_packet`, `worktree_env`.
- **Inline-call sites the grep test finds:** `worker_process`, `review_delegate`, `review_write_check`, `session_presence`, `doctor_worktrees`, `specyrd_init`, `worker_turn_check`, `role_prompt_cli`.
- **Import-path-only changes** (`git_root`, and `git_run`/`git_capture` moved out of `repo_ops`): the remaining files in the diff.

No new module was needed. `git_subprocess.py` is 349 lines, well under the cap.

## Added

- `git_subprocess.git_root`: moved from `runtime_paths` (A1 names it in `git_subprocess`), now bytes-safe.
- `git_subprocess.is_worktree_root`: the one worktree-root check A1 asks for, which replaces the four inline checks and the two `is_repo_top` copies.
- `git_subprocess.run_bytes`, `GitBytes` (with `ok`, `message`, `checked`), `GitError`: one bytes primitive in place of the private spawners in `worktree_delete_set`, `integrity`, `runtime_paths` and `ignore_report`. `checked` and `GitError` carry `ignore_report`'s existing raise rule and message format.
- `git_subprocess.git_bytes`: `integrity`'s and `red_green`'s "raw stdout, empty on failure".
- `git_subprocess.git_out`, `git_subprocess.git_path`: moved from `worktree_delete_set` (and `runtime_paths.git_path`).
- `git_subprocess.git_run`, `git_subprocess.git_capture`: moved unchanged from `repo_ops`.
- Branch in `is_worktree_root` (`branch is None or ...`): `worker_ops_launch` and `role_prompt_cli` check the branch, while the other callers check only the root.
- Guard: none added. `doctor_worktrees` dropped the raise it had outside a repository (see the behaviour notes).
- Mocks: none added. `test_finish_bookkeeping_wiring` now patches `ft.write_registry` instead of the removed `ft._save_registry`.
- Test `test_only_git_subprocess_asks_git_for_the_root_or_the_branch`: A2.
- Test `test_is_worktree_root` (5 parametrized cases: top, top with the matching branch, top with another branch, a subdirectory, outside a repository): the new public helper's contract. No existing test called a worktree-root helper directly.
