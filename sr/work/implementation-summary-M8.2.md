# Implementation summary: M8.2 — Worker adapters harden the launch and run a deterministic post-run check

Base: `a54c409b` (origin/WIP/improvements-0-3-1 after the M8.2 touch-zone updates). Code commit: `4e6a6acb`. Zone commit: `55c44ecd`. Review fixes: `da6f33a4`.

- **Merge of WIP (`d5fb31d0`, after `4f3990a7`):** brings in the Codex reviewer entries, M8.5's `harness_env`, the Cursor pricing changes and `worker_runner_ready`. Conflicts were resolved keeping both sides:
  - `worker_adapter_codex.py`: `exec resume` takes WIP's `-m <model>` plus this branch's memory switches and `CODEX_HOME`.
  - `worker_adapter_parsers.py`: both sides' new imports are kept.
  - `worker_runner.py`: WIP's `fresh_ready`, `completion_summary` and `harness_env` sit alongside this branch's `TurnWatch` and `close_turn`. `launch.env` is applied on top of `harness_env`, and `paused_by_limit` still wins over READY.
  - No behaviour change was needed: the leaf's tests and the WIP tests on these modules pass (147 tests).

- **Merge of WIP for D4 (`62061abc`, clean):** brings `5d1828a8`, which replaces A3 with RCA-8's bounded text. There was no code change; the post-run check is unchanged. How each clause is met:
  - **One `post_run_check` per turn, whatever the exit code:** `close_turn` runs on every end, including the `OSError` start failure and an already-`terminated` record.
  - **Stream findings:** permission denial, a failed turn (an error with no later `turn_completed`), and `api_retry`.
  - **Git findings:** branch change; HEAD missing or not descended from the start; an out-of-zone commit; a stash change; a porcelain change (a new dirty path, changed bytes, or a start-dirty path that vanished).
  - **Out of scope:** index-only changes.
  - **Tests:** `tests/test_worker_turn_check.py` and the missing-binary test in `tests/test_worker_adapters.py` cover these. `pytest -n 4` (116 tests, including WIP's `test_worker_reconcile_merged.py`) and `specy-road file-limits` pass.
- **Merge of WIP for `toolkit_version`:** the conflict was in `worker_state.py`, where `WorkerRecord` keeps `limit_reset_at` and WIP's `toolkit_version`, with `unknown_fields` last. The schema carries both. The post-run check is unchanged while the maintainer decides on the RCA's proposal to bound A3. `pytest -n 4` over the leaf's tests passes (110 tests), and `specy-road file-limits` passes again: WIP's `worker_cli.py` is back to 400 lines.
- **Merge of WIP for M11.35:** two conflicts, both resolved keeping both sides:
  - `worker_adapter_claude.py`: the Claude resume passes `*_model_flag("--model", model)` (M11.35) and `EXECUTOR_PERMISSIONS`.
  - `worker_runner.py`: `_finish` keeps `log_start` and M11.35's `exit_event`, and still runs `close_turn` first, with `PAUSED_BY_LIMIT` winning over READY and the exit code. `exit_event`'s `streamed()` counts only `source: worker` events, so the system `post_run_check` written before it does not hide the harness's stderr reason.
  - No behaviour fix was needed: `pytest -n 4` over the leaf's tests and `tests/test_roster_harness_model.py` passes (110 tests).
  - `specy-road file-limits` still exits 1, only for WIP's own `bundled_scripts/worker_cli.py` (401 lines, identical to WIP).
- **Merge of WIP for M11.57 (`ff5ce21f`):** the conflict was the `state` row in `docs/orchestration-workers.md`. It keeps this branch's `paused_by_limit` / `limit_reset_at` wording and M11.57's clause that a completed worker whose leaf is over does not keep its slot.
  - **Follow-on fix (`3bce63d8`):** M11.57's `worker_orphans.HELD_STATES` named only `idle` and `completed`. A worker paused at a usage limit whose leaf then ended would have held its `max_workers` slot for good, and neither `terminate --orphaned` nor finish would end it. `HELD_STATES` now includes `paused_by_limit`. `specy_road/worker_orphans.py` was added to M8.2's zones with `edit-node` (`3d2a513c`).
  - **Regression:** new `test_a_paused_worker_frees_its_slot_once_its_leaf_is_over_like_an_idle_one`, covering `orphans`, `holding_slots` and `end_finished_workers`. It fails without the fix: `orphans` returns `{}`.
  - **`specy-road file-limits` exits 1, from WIP:** WIP's own `specy_road/bundled_scripts/worker_cli.py` is 401 lines (M11.57's merge), and this branch does not touch it. Every file this branch changes is within its cap.
  - **Timing:** `test_message_while_running_queues_and_delivers` failed once in the `-n 4` run at load average 39, the known state-read race. It passed twice alone.
- **Merge of WIP for M11.69:** the conflict was in `worker_state.py`, where `WorkerRecord` keeps both `limit_reset_at` and M11.69's `unknown_fields`. `unknown_fields` stays last, so `load_record` and `to_dict` still treat `limit_reset_at` as a known field. No behaviour fix was needed: the leaf's tests, `test_schema_revision.py` and file-limits pass.
  - **Timing failure under load:** `test_spawn_returns_before_the_worker_ends_and_the_record_catches_up` failed once with the load average near 38. Timing a spawned turn in isolation showed this branch costs about 0.3 s more per turn than WIP's own checkout (0.6 s against 0.2–0.3 s): the post-run check's git reads and record writes. The test then passed twice in under 2 s, and passed in the full targeted run.

## Round 5: fix for review gpt-5.6-sol-medium at `c2588247` (block)

Required change (1), and where it is done (commit `2bfd8f5d`):
- **Exactly one `post_run_check` per turn, clean turns included.** `close_turn` in `specy_road/worker_turn_check.py` now always appends one event.
  - **Clean turn:** `detail: {"findings": []}` and the summary `post-run check: clean`.
  - **Turn with findings:** unchanged, with the findings and their count.
  - **Flag:** findings still set `post_run_findings`, and a clean turn still clears it. This covers every turn end: a harness that ran, the `OSError` start failure, and an already-`terminated` record.
- **Runner-level clean-turn regression updated.** In `tests/test_worker_turn_check.py::test_claude_launch_and_resume_pass_mode_tools_and_no_prompts_and_a_denial_flags_the_worker`, the second turn is clean. The test now asserts it adds exactly one more `post_run_check` (two in all) with empty findings and the clean summary, and that the flag is cleared. Before, it asserted that no event was added.
  - **Red-green:** it fails against `c2588247` (one event, not two) and passes on the fix.
- **Tests that pin a clean turn's event order.** `test_run_records_session_id_events_and_a_clean_exit` and `test_the_wrapper_payload_carries_the_mode_and_records_the_mismatch` in `tests/test_worker_adapters.py` now include `post_run_check` before `completion`. The file stays at 400 lines.
- **Docs and schema.** The post-run sentence in `docs/orchestration-workers.md` and the `post_run_check` description in `worker-event.schema.json` now say one event per turn, with empty findings when clean. Both are updated in place.
- **Touch zones.** No file outside M8.2's zones was needed.
- **Verification.** `pytest -n 4` over the leaf's tests passes (144 tests), as do the other worker and review round suites that read event sequences (105 tests). `specy-road file-limits` and `ruff` are clean.

## Round 4: fix for review gpt-5.6-sol-medium (block, again)

- **Lost pre-turn work is a finding.** `git_findings` now compares the union of the starting and ending dirty-path keys, excluding expected bookkeeping. Before, it walked only the paths still dirty at the turn's end, so pre-turn work outside the zones that the turn restored or deleted left no finding.
  - A path is a porcelain finding when it is **new, changed or gone** during the turn: absent from the start, a different content digest, or absent from the end.
  - "Gone" covers a restored tracked edit, a deleted untracked file and a pre-existing edit the turn committed.
  - The summary text is now "dirty paths new, changed or gone during the turn". The sentence in `docs/orchestration-workers.md` is updated in place.
- **Regression.** New `test_pre_turn_work_outside_the_zones_that_the_turn_restores_or_deletes_is_a_finding`: before the turn, the test leaves a tracked edit to `docs/x.md` and an untracked `docs/notes.md`, both outside the `src` zone. The turn runs `git checkout -- docs/x.md` and `rm docs/notes.md`. The test asserts the `post_run_check` event's porcelain paths, its summary, state `idle` and the flag.
  - **Red-green.** Without the fix the test fails (there is no `post_run_check` event at all); with it, it passes.

## Round 3: fix for review gpt-5.6-sol-medium (block)

- **Every started turn's end runs the post-run check.** Before this fix, two paths returned before `close_turn`, so no check ran and a stale `post_run_findings` flag survived as if it described that turn:
  - **A harness that cannot start** (`Popen` `OSError`): it now goes through `close_turn` as a failed turn (`watch.failed = "cannot start …"`). The worker is flagged by a fresh `post_run_check` naming the start failure, and the state is still `failed` with its lease released.
  - **A record already `terminated`** when the turn ends: `_finish` now runs `close_turn(..., pause=False)` before returning. Findings are recorded, and the flag is set or cleared. A usage limit stays a finding but sets no `limit_reset_at`, so the state stays `terminated`. As before, that path writes no exit record.
- **Tests.**
  - `tests/test_worker_adapters.py::test_run_reports_a_missing_binary_as_failed` now also asserts the `post_run_check` event (before the exit record) and the flag. Its line count is unchanged; the file is at the 400-line cap.
  - New `test_a_turn_whose_record_was_terminated_still_gets_the_check_and_stays_terminated`: the fake harness marks its own record terminated mid-turn, leaves a stray file and reports a limit. The test asserts the state stays `terminated` with no `limit_reset_at`, the flag is set, the findings are `porcelain` and `usage_limit`, and there is no `completion` event. It cannot use `worker terminate`, which would signal the test's own process group.
  - **Red-green.** Both fail against `a45defbc` and pass on the fix.

## Round 2: fixes for review gpt-6.1-sol (block)

- **R1.** In `worker_runner._finish`, a detected usage limit now takes precedence over a fresh READY. A turn that exits 0 with a valid READY at HEAD and a timed limit ends in `paused_by_limit`, so `limit_gate` applies. Its `completion` event still records `"ready": true`. New regression: `test_a_limit_wins_over_a_fresh_ready_written_in_the_same_turn`, which goes through `worker_runner.run` and `worker_ops_message.resume`.
- **R2.** `GitState.dirty` now maps each dirty path to its content (`_content`: a sha256 of the file, a link's target, or `-` when gone). The porcelain finding covers paths that are new **or whose content changed** during the turn, so a resumed turn that edits a file already dirty outside the expected set stays a finding and keeps the worker flagged. New regression: `test_a_further_edit_to_an_already_dirty_file_outside_the_zones_keeps_the_worker_flagged`.
  - **Not a finding:** a dirty path the turn leaves untouched. The check judges what this turn did, so an outside path the turn did not change does not count.
- **Red-green.** Both regressions fail against `55c44ecd` (`completed` instead of `paused_by_limit`; one `post_run_check` instead of two) and pass on the fix.
- **Docs.** `docs/orchestration-workers.md` says both, in place; still 400 lines.

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
- `tests/test_worker_turn_check.py`: 8 new tests (10 after round 2, 11 after round 3, 12 after round 4). Fake `claude` / `codex` / `agent` binaries on PATH record the argv, environment and stdin the wrapper really ran them with, and replay the streams in `tests/fixtures/worker_turn_check/streams.json`.
- `ruff check` (C901) over every changed or added Python file, `specy-road file-limits`, `scripts/check_test_private_imports.py`: clean.
- `ruff check specy_road tests scripts` exits 1, but only for `uncommitted_refs_section` in `specy_road/bundled_scripts/review_packet_uncommitted_refs.py` (12 > 10). That file is untouched here, so the failure is on the base.
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
- `_content()` (round 2, R2): a dirty path's content digest, so a further edit to an already-dirty file is seen.
- `PAUSED_BY_LIMIT if paused else …` ordering in `_finish` (round 2, R1): a limit wins over a fresh READY.
- Fake-harness `write` option in `tests/test_worker_turn_check.py` (round 2): lets a turn write its READY, for the R1 regression.
- Union of start and end dirty paths in `git_findings` (round 4): pre-turn work the turn restores, deletes or commits is a finding.
- `paused_by_limit` in `worker_orphans.HELD_STATES`, and `test_a_paused_worker_frees_its_slot_once_its_leaf_is_over_like_an_idle_one` (M11.57 merge): a paused worker whose leaf is over frees its slot, like idle.
- `test_pre_turn_work_outside_the_zones_that_the_turn_restores_or_deletes_is_a_finding` (round 4): Sol's required regression.
- `test_a_turn_whose_record_was_terminated_still_gets_the_check_and_stays_terminated` (round 3): the terminated path's check.
- `test_a_limit_wins_over_a_fresh_ready_written_in_the_same_turn`, `test_a_further_edit_to_an_already_dirty_file_outside_the_zones_keeps_the_worker_flagged` (round 2): the reviewer's two regressions.
- `TurnWatch` (`observe`, `_watchdog`, `stream_findings`): reads each parsed event for A3's stream findings, and is A1's retry watchdog.
- `TurnWatch.failed` cleared by `turn_completed`: a launch-mode mismatch or a mid-turn Codex `error` followed by a completed turn is not a failed turn.
- `TurnWatch.pending`: `rate_limit` retries that end the turn with no completed turn count as a limit.
- `git_findings()` / `_outside_zones()`: A3's git half, reusing reconcile's `_bookkeeping` and `zone_matches`.
- The clean `post_run_check` event in `close_turn` (round 5): the log shows the check ran on every turn.
- `close_turn()`, with its `except Exception` guard: records findings, sets or clears the flag, sets `limit_reset_at`; the guard keeps a git failure from costing the turn its exit record.
- `close_turn(..., pause=False)` and its calls on the start-failure and terminated paths (round 3): the check runs on every started turn's end without changing that path's terminal state.
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
