# Implementation summary: M22.44 (workers-run-in-a-sandbox)

## What changed

- `specy_road/worker_sandbox.py` (new) builds the bwrap command for one worker turn.
  - **Read-only:** `--ro-bind / /`, with `--dev /dev`, `--proc /proc`, a private tmpfs on `/tmp`, `--die-with-parent` and `--chdir <worktree>`.
  - **Writable:** the leaf worktree; in the common git dir, `objects`, `refs`, `logs` and `worktrees/<name>` (`logs/` is created on the host if it is missing).
  - **Read-only again on top:** `worktrees/<name>/commondir` and `gitdir`.
  - **Outbox:** a per-worker directory (`work/.workers/<id>.outbox`) is mounted at `reviews_dir(repo_root, node)`.
  - **Git pointers read-only:** the worktree's `.git` file, `worktrees/<name>/commondir` and `gitdir`, and `worktrees/<name>/config.worktree`. When `config.worktree` is absent, `/dev/null` is mounted there read-only. A worktree without its `gitdir` file is refused (fix round 1).
  - **Harness state, one rule (`HARNESS_STATE`, fix rounds 1 and 2):** no directory of the user's is writable from the sandbox; only named auth files are. Each state directory the harness uses is replaced by the worker's own (`work/.workers/<id>.state/<dir>`, kept across its turns; `state_home()`), transcripts and sessions included. Into it go the user's auth files, writable (Claude `.credentials.json`, Cursor `~/.config/cursor/auth.json`, Codex `auth.json` and the file it links to; an auth name that is a directory is not bound), and the user's settings, hooks, plugins, skills, rules, MCP and instruction files, read-only; each only when the user has it. `~/.claude.json` (or `$CLAUDE_CONFIG_DIR/.claude.json`) and Cursor's `cli-config.json` are seeded once from the user's file and bound from the per-worker copy. `~/.cache` is per-worker for Claude and Cursor.
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
- `docs/orchestration-workers.md`: a new "Worker sandbox" section, with the per-harness state table. It covers what an unsandboxed project does not protect, how to opt in, the modes, the binds, the outbox, failures and known limits, and the Claude/Cursor real-harness smoke check.
- `CHANGELOG.md`: an `[Unreleased]` / `### Added` entry.

## Touch zones

Final list: unchanged (all seven zones; no file outside them changed). The merge of `origin/WIP/improvements-0-3-1` brought in the coordinator's changed acceptance and other leaves' files; this leaf changed none of those files.

## Verification

- Targeted run: `python -m pytest -n 4 -q -p no:cacheprovider tests/test_worker_sandbox.py tests/test_worker_*.py tests/test_review_round6_runner.py tests/test_chore_mode.py tests/test_schema_revision.py tests/test_m11_27_small_cli_fixes.py tests/test_claude_config_dir.py`: 425 passed.
- Red-green:
  - With `prepare` forced to `off`, 4 sandbox tests fail.
  - With `worker_sandbox.py` at `e0369a2d` (before round 1), the three per-harness cases fail.
  - With `worker_sandbox.py` at `deebc49d` (before round 2), the three per-harness cases fail. With only `worker_runner.py` at `deebc49d`, the limit-from-the-worker's-transcript test fails (`failed` instead of `paused_by_limit`).
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK (only the existing warnings on other files).
- Not verified: real Claude/Cursor/Codex authentication, token refresh, and resume under the binds. That is the recorded smoke check in the docs. The per-worker state directories make this more important: login state a harness keeps outside the named auth files stays per worker.

## Fix round 1 (R1, gpt-6.1-sol at e0369a2d)

- **Class:** protection that depends on the protected entry existing. Shared steering was made read-only only when present, inside a directory mounted writable. Any absent name could then be created and would persist into the user's later sessions.
- **Design change:** I removed the deny-list over a writable directory instead of adding names to it. Harness state directories are now per-worker, and only named transcript and auth entries are written through (an allow-list). Absent steering lands in the worker's own directory.

## Fix round 2 (grok-4.7-high at deebc49d)

- **Class:** a writable directory shared with the user's home is an open namespace. The write-through transcript directories (Claude `projects/`, Cursor `chats/`, Codex `sessions/`) took any file at any depth, including `projects/<project>/memory/MEMORY.md`, which Claude reads as instructions. Listing names inside such a directory cannot close it.
- **Design change, one bounded rule:** no directory of the user's is writable from the sandbox, and only the named auth files are. Transcripts and sessions are the worker's own. The runner reads a Claude usage limit from the worker's transcript (`Box.state`, passed to `ClaudeCode.transcript_limit(home=)`).
- **Cost, documented:** a sandboxed worker's sessions cannot be resumed natively from the user's home (`worker handoff`), and the docs warn against pointing a harness at the worker's state directory instead.
- **Broader than the review:** the shared git directories a commit needs (`refs/`, `objects/`, `worktrees/<name>/`) are open namespaces of the same class. They cannot be made read-only without breaking commits, so I documented them as known limits (refs already an accepted limit, M22.45) rather than changing them. See Probes.

## Probes

- Claude: creating absent `settings.local.json`, `hooks/h.sh`, `skills/s/SKILL.md` and `CLAUDE.md` under `~/.claude` through the public runner → host home unchanged (the files and their parent dirs stay absent). Test: `[claude-code]`.
- Claude `~/.cache/claude-cli-nodejs/log` (an existing cache) → host unchanged; `~/.cache` is per-worker.
- Claude `projects/`: appending to the user's existing transcript, creating `projects/slug/memory/MEMORY.md` and `projects/planted.md` → host unchanged (round 2; the reviewer's case). `.credentials.json` → written through on both turns. The worker's own new transcript → still there on the resume turn (persist clause).
- Claude usage limit with the transcript in the worker's state dir → the worker is `paused_by_limit`, and nothing is written to the user's `projects/` (round 2 test).
- Claude `~/.claude.json` → writable inside; the host file is unchanged (per-worker seeded copy).
- Cursor: creating absent `mcp.json`, `rules/r.mdc`, `skills/s/SKILL.md` and `~/.config/cursor/cli.json` → host unchanged. Existing `hooks.json` → write refused. Appending to the user's `chats/c.db` and creating `chats/planted.md` → host unchanged (round 2). `~/.config/cursor/auth.json` → written through. The worker's own `chats/x/store.db` persists to the resume turn. `cli-config.json` → per-worker copy, host unchanged. Test: `[cursor]`.
- Codex (`CODEX_HOME` profile home): creating absent `AGENTS.md`, `hooks/h` and `skills/s/SKILL.md` → host unchanged. Existing `config.toml` → refused. Appending to the user's `sessions/s.jsonl` and creating `sessions/planted.md` → host unchanged (round 2). The `auth.json` symlink target in `~/.codex` → written through. The worker's own `sessions/2026/r.jsonl` persists to the resume turn. Test: `[codex]`.
- Seeded file absent on the host (`~/.claude.json`): home is read-only, so the write is refused and nothing reaches the home. When it lives in a replaced state dir (`cli-config.json`, `$CLAUDE_CONFIG_DIR/.claude.json`), it is created in the worker's own dir. Checked by reading the code (not a separate test).
- Worktree `.git` file (inside the writable worktree): was writable, which allowed a redirect like spike probe 3 → now read-only, write refused (common probe in all three cases).
- `worktrees/<name>/config.worktree` (absent, inside the writable `worktrees/<name>`, read by git under `extensions.worktreeConfig`): was creatable → now an empty read-only mask; write refused, and the host file stays empty.
- `worktrees/<name>/gitdir` absent: could not be held read-only → the turn is now refused ("worktree without its gitdir file" case). An empty mask was rejected because `git worktree prune` would drop the worktree.
- `commondir`: required by `linked_worktree` already → always held read-only.
- Common `config`, `hooks/`, `info/` (existing or absent): outside every writable mount (the common dir itself is read-only) → write refused, absent ones not creatable.
- `~/.ssh`, `~/.config/gh` absent: home is read-only → not creatable; present → hidden by tmpfs (unchanged).
- Outbox and reviews dir: an absent reviews dir is created on the host before the mount; the outbox is emptied each turn (unchanged, A4 tests pass).
- `<common>/logs` absent: created on the host before the mount, so a commit's reflog works (unchanged).
- Auth names that are directories in the user's home → not bound (`.is_file()` on the resolved source); every remaining write-through entry is a single file.
- Seeded copies and `~/.cache` → per-worker, never shared (unchanged).
- Shared git directories (`refs/`, `objects/` including `info/alternates`, `worktrees/<name>/` including rebase/merge state, `logs/`) → writable by necessity, since a commit writes there. The files git reads as config or as repository pointers are read-only (round 1). The rest is documented as a known limit, not changed.
- The leaf worktree → writable by design. Untracked steering in it (for example `.claude/settings.local.json`) affects sessions opened in that tree, which is the accepted "affects the worker's own harness" class from the spike report.

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
- `worker_sandbox.HARNESS_STATE`: the one table for harness state (directories replaced, auth files written through, read-only steering, seeded files) (R1; round 2 narrowed write-through to files).
- `worker_sandbox.state_home` and `Box.state`: the worker's own state home, which the runner reads transcripts from (round 2).
- Guard in `_harness_binds`: an auth name is bound only when it resolves to a file, never a directory (round 2).
- `worker_runner._transcript_limit(..., home=)`: reads the sandboxed worker's transcript (round 2).
- `tests/test_worker_sandbox.py::test_a_sandboxed_claude_turn_that_stops_at_a_limit_is_read_from_the_workers_own_transcript`: a distinct regression for the runner reading the worker's own transcript (round 2).
- `worker_sandbox._harness_binds`: applies `HARNESS_STATE`, replacing the old `_harness_state` deny-list (R1).
- `worker_sandbox._state_path`: resolves a table path under `$CLAUDE_CONFIG_DIR` / `$CODEX_HOME` or the home directory (R1).
- `worker_sandbox._binds(..., at=)`: a destination for auth files whose source is a symlink target (Codex `auth.json`) (R1).
- Guard in `linked_worktree`: refuses a worktree without its `gitdir` file (R1 class).
- Binds in `prepare`: the worktree's `.git` read-only, and `config.worktree` read-only or masked by `/dev/null` (R1 class).
- `worker_sandbox._read_available`: a non-blocking read of bwrap's status pipe, so a harness that inherits the pipe cannot hang the runner.
- `worker_sandbox._deliver_ready`: the outbox move (A4); skips symlinks and non-READY files.
- `worker_sandbox.SandboxError`, `HIDDEN_ENV`, `HIDDEN_HOME`, `NO_SANDBOX_WARNING`: the refusal type and constants.
- `git_workflow_config.worker_sandbox_mode` / `WORKER_SANDBOX_MODES`: the config key, default off (A1).
- `worker_runner._not_started`: the shared "turn ends before the harness runs" path, for a sandbox refusal and a failed `Popen`.
- `worker_runner._launched`, `_feed`: extracted from `run()` to keep its complexity within ruff's limit; `_launched` adds the sandbox and warning fields.
- `worker_runner._close_box`: delivers READY and records a start failure after the turn.
- Branch: `auto` with no bwrap available warns on each launch and runs unsandboxed (A5).
- `tests/test_worker_sandbox.py::test_a_sandboxed_launch_and_resume_commit_hand_off_ready_and_reach_nothing_else`: A6, parametrized over a `HARNESSES` table (claude-code, cursor, codex). Each case runs a launch and a resume through `wr.run` with a temporary home. It checks: the commit; READY versus REVIEW delivery; refused probes (git pointers, main checkout, home, existing steering); absent steering and anything in the transcript directories created inside without reaching the home (round 2); auth files written through; the worker's own transcripts persisting to the resume turn (round 2); per-worker seeded copies; hidden credentials (R1 extends it).
- `tests/test_worker_sandbox.py::test_a_turn_the_sandbox_cannot_hold_stops_unless_auto_finds_no_sandbox`: the main-checkout refusal, a worktree without its `gitdir` file (R1), a failed bwrap start (a fake `bwrap` on PATH), and auto's warning path.
- `tests/test_worker_sandbox.py::test_worker_sandbox_is_off_unless_the_project_opts_in`: omitted, false and off give off; auto and bwrap are read as written.
- Mocks: none (the fake `bwrap` script on PATH and the fake harness are real processes).
