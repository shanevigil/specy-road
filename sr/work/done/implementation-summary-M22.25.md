# M22.25 — Upgrade's git calls share one bounded, cleaned environment

## Summary

A real `specy-road upgrade` and `upgrade --dry-run` now follow one environment rule. Every git call the run makes sees no `GIT_` variable of the caller's, and is bounded by a timeout. The plan's mirror and the dry run's copy also read no global or system git config and run no hook. The checkout still reads the caller's own config files. The planning-mirror refresh is the only stretch that isolates, in both runs, and it restores the caller's environment before anything is applied or validated in the checkout.

Touch zones, confirmed by reading the call sites of each zoned module: `specy_road/bundled_scripts/upgrade.py`, `specy_road/bundled_scripts/upgrade_plan.py`, `specy_road/bundled_scripts/upgrade_generated.py`, `specy_road/ignore_report.py`, `specy_road/file_limits_engine.py`, `tests/test_upgrade_preview.py`, `CHANGELOG.md`. No zone was added or removed. `tests/parity/` does not exist, so acceptance line 5 does not bind.

## Changes

- `scratch_environ` takes `Path | None`. `None` replaces `os.environ` with `scratch_git_env()` (every `GIT_` variable dropped, config files still read) and does not change ignore-report isolation. A path keeps today's isolation: `GIT_CONFIG_NOSYSTEM`, an empty `GIT_CONFIG_GLOBAL`, and `isolate_git`. On exit it restores the previous environment and, when it isolated, the isolation `isolate_git` returned, so a nested stretch never clears the outer one. It still yields the caller's environment with `GIT_` dropped, for `regenerate`.
- `run_upgrade` runs `_upgrade` inside `scratch_environ(None)`, so `project_root`, `_resolve_root`, the line-cap scans, `validate`, `digest --check`, `regenerate`'s `ls-files`, and `_other_worktrees` all see the stripped environment.
- `make_plan` wraps only `refresh` in `scratch_environ` of the plan's temporary directory. `Mirror.build`'s `git init` still passes that directory's environment itself. When refresh returns, the caller environment is back before `apply_plan`, the work-template copy, the line-cap scan and validate. In a dry run this nests inside the copy's isolation and restores it. The refresh's ignore note therefore reads no global excludes file in a real run either, the same as a dry run.
- `isolate_git` returns the isolation it replaces.
- `git_ignored_paths` passes `timeout=git_subprocess.DEFAULT_TIMEOUT` and treats `subprocess.TimeoutExpired` like any other answer it cannot trust: an empty set, so the scan counts those files.
- `upgrade`'s module docstring, which is `--help`, states the environment rule and that the exit code is 2 when a git call it depends on fails or times out, 1 when validate fails or a write is refused, and 0 otherwise.
- The `[Unreleased]` upgrade Security bullet now names the real run and the checkout's `check-ignore`. Git spawns a run reaches, each with a timeout: `git_subprocess.run` (mirror `init`, dry-run `add` and `commit`, `ls-files` on `roadmap.md`, `worktree list`), `ignore_report`'s git for the refresh's ignore note (`timeout=60`), `runtime_paths.git_path` (`rev-parse`), and `file_limits_engine.git_ignored_paths`. `specyrd_init.resolve_repo_root` spawns git with no timeout; `refresh_stubs` imports other names from that module and does not call it, so an upgrade does not reach it.

## Verification

- `pytest -n 4` — 6211 passed. The brief's gate is `pytest -n auto`; section 7 caps parallel workers at 4 while other workers share the machine, which they were, so the suite ran as `pytest -n 4`.
- `specy-road file-limits` — OK (existing hard-alert warnings only).
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` — OK.
- `ruff check` on the edited Python files — passed.

## Walkthrough

1. A real upgrade with `GIT_DIR` and `GIT_WORK_TREE` (or `GIT_INDEX_FILE`, `GIT_COMMON_DIR`, `GIT_OBJECT_DIRECTORY`) pointing at a second repository exits 0, leaves that repository's HEAD, index and files unchanged, and writes the plan in the project.
2. `GIT_CONFIG_COUNT` injecting `core.fsmonitor`, a clean filter, or `core.hooksPath` creates no marker in either run. A real run leaves HEAD, refs and the index unchanged.
3. A `core.fsmonitor` in `$HOME/.gitconfig` or the XDG config appends `$PWD`. A dry run leaves the marker absent and `specy.probe` unread. A real run's marker lines are only the checkout's path, and validate reads `specy.probe` as `reached`.
4. The checkout's `git -C <root> check-ignore --stdin -z` timing out still finishes the real run at exit 0, with `== next` and no traceback.
5. `specy-road upgrade --help` includes "The exit code is 2 when a git call it depends on fails or times out".

## Added

### Helpers

- none

### Branches or guards

- `scratch_environ(None)` drops `GIT_` variables and leaves ignore-report isolation as it was, so the whole run, including the checkout, shares that environment.
- `scratch_environ(path)` restores the isolation `isolate_git` returned, so the plan's refresh can nest inside the dry run's isolation and put it back.
- `git_ignored_paths` catches `subprocess.TimeoutExpired` and returns an empty set, the same as any other answer it cannot trust.

### Mocks

- `test_a_timed_out_check_ignore_still_finishes_the_real_run` stubs `subprocess.run` so the checkout's `git -C … check-ignore --stdin -z` raises `TimeoutExpired`, and delegates every other call, so the bound is tested without sleeping.

### Tests

- `test_the_callers_global_git_config_never_reaches_the_copy` gained `dry_run`: the marker stays empty in a dry run; a real run's lines are only the checkout path and `specy.probe` is `reached`.
- `test_git_config_count_runs_no_command` (renamed from the dry-run-only test) gained `dry_run`: an injected `GIT_CONFIG_COUNT` runs no command in either run, and a real run keeps HEAD, refs and the index.
- `test_upgrade_never_touches_the_repository_a_git_variable_names` (renamed from the dry-run-only test) gained `dry_run`: the second repository is unchanged in both runs, and after a real run the paths the review saw exist in the project.
- `test_a_timed_out_check_ignore_still_finishes_the_real_run`: a timed-out checkout `check-ignore` still exits 0 with `== next` and no traceback.
- `test_upgrade_help_states_exit_2_when_a_git_call_fails`: `upgrade.main(["--help"])` states exit 2 for a failed or timed-out git call.
