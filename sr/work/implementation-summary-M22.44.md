# Implementation summary: M22.44 (workers-run-in-a-sandbox)

## What changed

- `specy_road/worker_sandbox.py` (new) builds the bwrap command for one worker turn.
  - **Read-only:** `--ro-bind / /`, with `--dev /dev`, `--proc /proc`, a private tmpfs on `/tmp`, `--die-with-parent` and `--chdir <worktree>`.
  - **Writable:** the leaf worktree; in the common git dir, `objects`, `refs`, `logs` and `worktrees/<name>` (`logs/` is created on the host if it is missing).
  - **Read-only again on top:** `worktrees/<name>/commondir` and `gitdir`.
  - **Outbox:** a per-worker directory (`work/.workers/<id>.outbox`) is mounted at `reviews_dir(repo_root, node)`.
  - **Harness state** (for `rec.harness`): the state directories are writable, with shared settings, hooks, plugins, skills, rules and MCP config read-only on top. `~/.claude.json` (or `$CLAUDE_CONFIG_DIR/.claude.json`) and Cursor's `cli-config.json` are bound from per-worker copies in `work/.workers/`.
  - **Hidden:** `~/.ssh` and `~/.config/gh` behind an empty tmpfs; `SSH_AUTH_SOCK`, `GH_TOKEN` and `GITHUB_TOKEN` removed from the harness environment.
  - **Start report:** bwrap's `--json-status-fd` pipe shows whether the harness ever started.
  - **After the turn:** only regular `READY-*` files move from the outbox into the reviews directory; the outbox is then removed.
  - **Linked worktree check:** `linked_worktree()` reads `.git` and `commondir` without running git and refuses anything that is not a linked worktree, naming `--worktree`.
- `specy_road/worker_runner.py`:
  - `run()` calls `worker_sandbox.prepare()` and passes `box.command(launch.argv)` to the existing single `Popen`, with `pass_fds`.
  - A `SandboxError` ends the turn as `failed`, recorded through `_not_started`. That is the old "cannot start" block, moved out of `run()` and shared.
  - `_close_box` delivers READY before `_finish`'s READY check and records an `error` event when bwrap never started the harness.
  - The `launched` event moved to `_launched` and the stdin write to `_feed`, to keep `run()` under ruff's C901 limit and the 80-line function cap.
  - With the default `off` the event is unchanged. A sandboxed launch adds `sandbox: bwrap`; an unsandboxed `auto` launch adds `sandbox: off` and the warning, which also goes into `<id>.log`.
- `specy_road/git_workflow_config.py`: `WORKER_SANDBOX_MODES` and `worker_sandbox_mode()`. It returns `off` when the key is omitted, YAML `false`, or the config is unreadable.
- `specy_road/templates/project/schemas/git-workflow.schema.json`: the `worker_sandbox` enum `bwrap | auto | off | false`.
- `docs/orchestration-workers.md`: a new "Worker sandbox" section. It covers what an unsandboxed project does not protect, how to opt in, the modes, the binds, the outbox, failures and known limits, and the Claude/Cursor real-harness smoke check.
- `CHANGELOG.md`: an `[Unreleased]` / `### Added` entry.

## Touch zones

Final list: unchanged (all seven zones; no file outside them changed). The merge of `origin/WIP/improvements-0-3-1` brought in the coordinator's changed acceptance and other leaves' files; this leaf changed none of those files.

## Verification

- `python -m pytest -n 4 -q -p no:cacheprovider` over `tests/test_worker_sandbox.py` and every test file that drives the worker runner, plus the schema tests: 1185 passed.
- Red-green: with `prepare` forced to `off`, 4 of the 9 sandbox tests fail. The unsandboxed probe overwrites `gitdir`, so `git log` in the worktree fails; and the refusals and the warning are missing.
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK (only the existing warnings on other files).
- Not verified: real Claude/Cursor/Codex authentication and token refresh under the binds. That is the recorded smoke check in the docs.

## Notes for reviewers

- `~/.local/share/cursor-agent` (Cursor's binaries) stays read-only, unlike the spike's experiment, which bound it writable. If Cursor needs to write there (to update itself), the smoke check will show it.
- Codex: only the resolved `auth.json` file is writable, so a refresh that writes a temporary file next to it would fail. That is the planning sheet's "If this fails" case.
- Accepted limits that are unchanged:
  - Reviewer turns are not wrapped.
  - Refs stay writable.
  - The network stays open.
  - A nested repository's common git dir is not carved out.
  - `SSH_AUTH_SOCK`'s socket file is still reachable by path if the worker knows it; only the variable is removed.

## Added

- `worker_sandbox.Box`: one turn's launch, with prefix, outbox, warning and status pipe; `command()` adds the prefix, and `finish()` closes the pipe, delivers READY and reports a start failure.
- `worker_sandbox.prepare`: selects the mode, refuses what cannot be sandboxed, and builds the binds.
- `worker_sandbox._select`: chooses bwrap, the warned fallback, or a refusal from the mode and the host.
- `worker_sandbox._binds`: binds existing paths only, since bwrap cannot create a mount point on the read-only root.
- `worker_sandbox.linked_worktree`: the A2 guard (a linked worktree distinct from the main checkout).
- `worker_sandbox._harness_state` / `_harness_binds`: per-harness writable, read-only and per-worker-copy paths (A3).
- `worker_sandbox._read_available`: a non-blocking read of bwrap's status pipe, so a harness that inherits the pipe cannot hang the runner.
- `worker_sandbox._deliver_ready`: the outbox move (A4); skips symlinks and non-READY files.
- `worker_sandbox.SandboxError`, `HIDDEN_ENV`, `HIDDEN_HOME`, `NO_SANDBOX_WARNING`: the refusal type and constants.
- `git_workflow_config.worker_sandbox_mode` / `WORKER_SANDBOX_MODES`: the config key, default off (A1).
- `worker_runner._not_started`: the shared "turn ends before the harness runs" path, for a sandbox refusal and a failed `Popen`.
- `worker_runner._launched`, `_feed`: extracted from `run()` to keep its complexity within ruff's limit; `_launched` adds the sandbox and warning fields.
- `worker_runner._close_box`: delivers READY and records a start failure after the turn.
- Branch: `auto` with no bwrap available warns on each launch and runs unsandboxed (A5).
- `tests/test_worker_sandbox.py::test_a_sandboxed_launch_and_resume_commit_hand_off_ready_and_reach_nothing_else`: A6. A table-driven launch and resume through `wr.run` with a temporary home. It checks the commit, READY versus REVIEW delivery, the refused probes, the hidden credentials, writable state and the per-worker copy.
- `tests/test_worker_sandbox.py::test_a_turn_the_sandbox_cannot_hold_stops_unless_auto_finds_no_sandbox`: the main-checkout refusal, a failed bwrap start (a fake `bwrap` on PATH, which is a public interface), and auto's warning path.
- `tests/test_worker_sandbox.py::test_worker_sandbox_is_off_unless_the_project_opts_in`: omitted, false and off give off; auto and bwrap are read as written.
- Mocks: none (the fake `bwrap` script on PATH and the fake harness are real processes).
