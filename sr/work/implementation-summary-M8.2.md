# Implementation summary: M8.2 — Worker adapters harden the launch and run a deterministic post-run check

Base: `a54c409b` (origin/WIP/improvements-0-3-1 after the M8.2 touch-zone updates). Code commit: `4e6a6acb`.

## What changed, per acceptance item

**A1 (Claude Code).**
- **Launch and resume flags.** Both default commands now pass `EXECUTOR_PERMISSIONS`: `--allowedTools Read,Edit,Write,Glob,Grep,Bash --permission-prompts none --permission-mode acceptEdits` (`worker_adapter_claude.py`).
  - `--allowedTools` takes several values, so a single-value flag follows it before the stdin instruction.
  - The resume keeps the same flags.
  - The reviewer launch is unchanged (M8.3's scope).
- **Retry watchdog.** `TurnWatch` (new `worker_turn_check.py`) reads every `system/api_retry`. Once a turn's `rate_limit` retries announce more than `LIMIT_WAIT_CAP_SECONDS` (600 s) of waiting, it SIGTERMs the harness and records a `usage_limited` event with source `watchdog`.
  - Claude Code has no retry watchdog of its own: code.claude.com/docs/en/headless, read 2026-11-03, documents only the `api_retry` event. So the watchdog and its cap are specy-road's.
  - The cap is a module constant, not a `policy.*` key: the orchestration schema (`templates/project/schemas/orchestration.schema.json`) is outside the zones.
- **Paused-by-limit state.** A limit is recognised from the text, never the exit code:
  - a Claude result whose text `claude_code_limits.classify_limit` reads as a limit (a successful result only with a stated reset time);
  - a Codex `turn.failed`/`error` with limit wording, with its "try again in/at" time;
  - `rate_limit` retries that no completed turn followed;
  - or the watchdog.

  Such a turn ends in the new record state `paused_by_limit`, with the new field `limit_reset_at` (UTC ISO 8601, or null). Both are documented in `worker-record.schema.json` for M11.62 to reuse. The worker keeps its slot and lease, like `idle`.
- **Resume after the reset.** `worker_ops_message._send` calls `limit_gate`, so `worker resume` and `worker message` refuse the worker before `limit_reset_at` and resume the same session, with the same flags, after it. The next turn's `TurnWatch` clears the field.

**A2 (Codex and Cursor).**
- **Codex.** Launch and resume keep `exec --json` (resume: `exec resume --json`) and the `sandbox_mode=workspace-write` / `approval_policy=never` overrides. They add `-c features.memories=false -c memories.use_memories=false -c memories.generate_memories=false`.
  - **Per-profile `CODEX_HOME`.** They run with `CODEX_HOME=~/.specy-road/codex-home/<model id>/`, through a new `Launch.env` that the wrapper applies.
  - **Login.** The user's `auth.json` is symlinked in, so the login carries over and nothing else of `~/.codex` does.
  - **Finding the thread again.** `resume` and `human_resume` find the profile home that holds the thread's rollout. The hand-off command becomes `env CODEX_HOME=<home> codex resume <id>`.
- **Cursor.**
  - **Chat first.** The default launch runs `agent create-chat` in the worktree, then `agent -p --resume <chat> … --force --trust …`, with `session_id` known up front.
  - **No `-w`.** A `channels.cli` that passes `-w`/`--worktree` is refused on launch and resume.

**A3 (post-run check).**
- **When it runs.** `close_turn` runs in `worker_runner._finish` after every turn, before the exit record, whatever the exit code.
- **Stream findings.** Each `permission_denied`, parsed from Claude's result `permission_denials` (one event per denial). A failed turn: an `error` that no completed turn followed. `api_retry` events.
- **Git findings.** It compares the state at the turn's start with the state at its end. Findings:
  - the branch changed;
  - HEAD is not a descendant of the turn's start (reset, rebase or amend);
  - the turn's commits touched paths outside the claim's touch zones;
  - the stash list changed;
  - porcelain paths that are new, excluding the leaf's bookkeeping and the registry, as `reconcile` counts them.
- **Recording.** Findings go into one `post_run_check` event and set the new flag `post_run_findings`, which `worker sync` and `list` show. A clean turn clears the flag.
- **New event types:** `api_retry`, `permission_denied`, `usage_limited`, `post_run_check`.

**Docs.** `docs/orchestration-workers.md` has updated state, flag and event lists, the Permissions paragraph, the adapter table rows, and a new "Post-run check and usage limits" paragraph.

## Touch zones (final list)

These are the zones as given, plus one new module:
- **`specy_road/worker_turn_check.py` (new, outside the listed zones).** `worker_runner.py` and `worker_state.py` were both at the 400-line cap, so the check, the watchdog, the paused-state constants and `limit_gate` live there. Please add it to M8.2's zones; M11.62 will import `PAUSED_BY_LIMIT` and `limit_gate` from it.

Line-cap measures, with no comment or docstring shortened:
- `worker_runner.py`: the `worker_state` import list was reflowed onto two lines.
- `worker_state.py`: `WorkerEvent.to_dict`'s two-line body became one line.

Not changed, though they are now stale, because they are outside M8.2's zones:
- `specy_road/worker_adapters.py`: the module docstring still describes the Claude default as `acceptEdits` alone.
- `model-profiles/harness-facts.yaml` `headless_command` and the rendered `README.md`.
- `docs/agentic-sandbox-runbook.md:201`.
- `review_delegate.py`: ignores `Launch.env`, so a Codex reviewer it launches does not get the per-profile `CODEX_HOME`. Its resume is consistent, because it also ignores the env.

## Verification

- `pytest -n 8` over the whole suite: 3321 passed, 2 skipped.
- `tests/test_worker_turn_check.py`: 8 new tests. Fake `claude` / `codex` / `agent` binaries on PATH record the argv, environment and stdin the wrapper really ran them with, and replay the streams in `tests/fixtures/worker_turn_check/streams.json`.
- `ruff check specy_road tests scripts` (C901), `specy-road file-limits`, `scripts/check_test_private_imports.py`: clean.
- `scripts/check_clones.py` reports two new pairs. Both are in files this leaf does not touch (`abort_task_pickup`/`pm_sync`, `planning_sheet_bootstrap`/`planning_scaffold_check`), so they were already on the base.
- `tests/test_worker_faults.py::test_output_clears_a_stall_shorter_than_the_write_window` failed once under `-n 8` load and passed alone and in the full run. It is timing-sensitive, not affected by this change.

## Deviations and notes

- **One existing test changed on purpose.** `tests/test_worker_adapters.py::test_run_marks_completed_when_ready_exists_and_failed_on_nonzero_exit` used the message `"quota"` for a plain failure. Limit wording now pauses the worker, so the message is `"boom"`, and its event order includes the new `post_run_check`. It still asserts `failed` on a non-limit nonzero exit.
- **Real Cursor chats were created during development.** Before the conftest guard existed, the existing default-Cursor-launch tests ran the machine's real `agent create-chat` and created a few empty Cursor chats on the maintainer's account. `tests/conftest.py` now stubs `create_chat` suite-wide, and the fake-binary test calls the real function.
- **Real Codex homes were created and removed.** The same early run created two `~/.specy-road/codex-home/*` directories holding only `auth.json` symlinks; I removed them. Codex homes are now redirected to tmp.
- **Fixture provenance.** The stream fixtures are constructed from the documented field shapes, not captured: M8.7 could not trigger a live limit. The file's `_note` says so.
- **Spend caps.** A limit with no stated reset (a spend cap or unrecognised wording) still pauses, with `limit_reset_at: null`, so resume is allowed at once and the human decides.

## Added

- `worker_turn_check.py` (module): the post-run check and the paused state in one place; the runner and state modules were at the line cap.
- `PAUSED_BY_LIMIT`, `FLAG_POST_RUN`, `LIMIT_WAIT_CAP_SECONDS` (constants): the state, flag and watchdog cap that A1/A3 name; M11.62 reuses the first two.
- `GitState` / `git_state()`: the HEAD, branch, stash list and porcelain snapshot that A3 compares.
- `TurnWatch` (`observe`, `_watchdog`, `stream_findings`): reads each parsed event for A3's stream findings, and is A1's retry watchdog.
- `TurnWatch.failed` cleared by `turn_completed`: a launch-mode mismatch or a mid-turn Codex `error` followed by a completed turn is not a failed turn.
- `TurnWatch.pending`: `rate_limit` retries that end the turn with no completed turn count as a limit.
- `git_findings()` / `_outside_zones()`: A3's git half, reusing reconcile's `_bookkeeping` and `zone_matches`.
- `close_turn()`, with its `except Exception` guard: records findings, sets or clears the flag, sets `limit_reset_at`; the guard keeps a git failure from costing the turn its exit record.
- `limit_gate()`: A1's "resume picks it up after the reset"; refuses before `limit_reset_at`.
- `limit_gate(rec)` call in `worker_ops_message._send`: applies the gate to `resume`, `message` and queued delivery.
- `WorkerRecord.limit_reset_at` and the schema field: when the limit lifts, for resume to read.
- Schema enums `paused_by_limit`, `post_run_findings`, and event types `api_retry`, `permission_denied`, `post_run_check`, `usage_limited`: the record and events validate against them.
- `Launch.env` and `env.update(launch.env or {})` in `worker_runner.run`: carries Codex's per-profile `CODEX_HOME` to the harness only.
- `watch` parameter on `_consume` / `_finish`, `watch.proc = proc`: feed the watch and let the watchdog stop the harness.
- `EXECUTOR_TOOLS`, `EXECUTOR_PERMISSIONS` (Claude): A1's explicit mode, allow-list and no prompts, shared by launch and resume.
- `ClaudeCode._turn_signals()`: parses `system/api_retry`, `permission_denials` and the result's limit text.
- `limit_detail()`, `_try_again()` and their regexes (parsers): a limit and its reset read from text, Claude's "resets" and Codex's "try again in/at".
- `CODEX_MEMORY_OFF`, `codex_homes()`, `profile_home()` (with the `auth.json` link), `session_home()` (Codex): A2's memory switches and per-profile `CODEX_HOME`, and finding a thread's home for resume and hand-off.
- `Codex.parse_events()` override: a `usage_limited` event from a failure's "try again" text.
- `Codex.human_resume` `env CODEX_HOME=…` prefix: the hand-off finds the thread in its profile home.
- `create_chat()` (Cursor): A2's "create the chat first"; refuses a non-zero exit or an unsafe id.
- `_no_worktree_flag()` (Cursor): A2's "never -w" for custom commands too.
- `tests/conftest.py` `codex_homes_stay_in_tmp`, `cursor_chats_are_never_created` (autouse): no test writes to `~/.specy-road` or creates a real Cursor chat.
- `tests/test_worker_turn_check.py` (8 tests, with the fake harness binary `FAKE`, `_harness`, `_calls`, `_respec`, `_events`, `_findings`): pin each harness's argv, environment and stdin as run, and the limit, watchdog, flag and git findings.
- `tests/fixtures/worker_turn_check/streams.json`: the replayed streams, labelled as constructed.
- Mocks: the conftest stubs above; no other mocks (the tests use fake binaries).
