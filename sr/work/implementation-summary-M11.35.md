# Implementation summary: M11.35 — roster-harness-model-id

Branch `feature/rm-roster-harness-model-id`, base `f78c3e03`.

## Commits

- `5bbf4a25` — touch zones: the leaf's zones predate the M11.59 split, so `specy-road edit-node M11.35 --add touch_zones=…`
  added `specy_road/worker_ops_launch.py`, `specy_road/worker_adapter_claude.py`, `specy_road/worker_adapter_codex.py`,
  `specy_road/worker_adapter_cursor.py`, `specy_road/review_delegate.py`, `specy_road/bundled_scripts/validate_roadmap.py`
  (maintainer's instruction; committed `roadmap/phases/M11__6cb421.json` and `roadmap/registry.yaml` as edit-node named them).
- `15642c9a` — the implementation.
- `a2cb319c` — this summary (first review round).
- `48339c33` — round 2 (Grok block): merge of `origin/WIP/improvements-0-3-1`. `worker_runner.py` conflicted with M11.27,
  which moved `_fresh_ready` to `worker_runner_ready.fresh_ready` and gave exit 0 `completion_summary` against a
  `before_all` checkpoint (READY present / invalid / missing). Resolved by keeping both: `run` takes `before_all`
  (M11.27) and `log_start` (this leaf); `_finish(…, before_all, usage_logged, log_start)` calls `fresh_ready` and then
  `worker_exit.exit_event(…, before_all=…, log=…, log_start=…)`, which writes the exit-0 completion with M11.27's
  `completion_summary` unchanged (the pre-M11.27 present/missing strings are not restored) and the non-zero early-failure
  summary from this leaf. The roadmap chunk and `registry.yaml` auto-merged; M11.35's claim row and zones are intact.
- `5210a439` — `specy-road edit-node M11.35 --add touch_zones=specy_road/worker_exit.py` (round 2's second required change).
- `05cfac06` — clean merge of `origin/WIP/improvements-0-3-1` (new Codex reviewer entries; WIP's `harness_env` now builds the harness environment in `worker_runner.run` and `review_delegate._turn`, beside this leaf's `log_start` / `exit_event` and `harness_model`, which are unchanged); no fix needed. Re-ran `tests/test_roster_harness_model.py`, `tests/test_worker_adapters.py`, `tests/test_review_delegate.py`, `tests/test_m11_27_small_cli_fixes.py` (56 passed) and `specy-road file-limits` (OK).

## Final touch zones

The original six, the six above, and `specy_road/worker_exit.py` (added in `5210a439`). `worker_runner.py` was at the
400-line cap, so the exit-event code `_finish` wrote inline moved to that new module with the early-failure logic
(`worker_runner.py` is 376 lines after the merge, since M11.27 moved `_fresh_ready` out as well).
`worker_adapter_codex.py` and `worker_adapter_cursor.py` were not changed (see A3).

## Acceptance

- **A1** — `harness_model` is a new optional roster field (`orchestration.schema.json`, same `id` pattern).
  `orchestration_config.harness_model(entry, profile_api_id)` is the one resolver: `harness_model`, else the profile's
  `api_id` (`unknown`/empty → harness default, as before), else the roster `id`. `worker_ops_launch._cli_for` uses it
  (so `worker delegate`, `message` and `resume`), and so does `review_delegate._Harness`, where a missing profile
  still means the harness default unless `harness_model` is set. `validate` prints
  `warning: roster entry '<id>' runs on claude-code and its id has a dot; set harness_model …` via
  `orchestration_config.harness_model_warnings`, from `validate_orchestration_contract`.
- **A2** — `worker_runner.run` records the log's length before the harness starts (`log_start`) and `_finish` hands the
  exit event to `worker_exit.exit_event`. On a non-zero exit with no worker event since this turn's `launched`
  (the wrapper's own null `usage` aside), the `error` summary becomes
  `exit N before any stream event: <line>; see <id>.log`, and `detail.harness_error` holds the line. The line is the
  last line of this turn's log tail (≤ 64 KiB, `[wrapper]` notes skipped) matching error/fail/denied/invalid/not
  found/unknown/a 4xx–5xx code, else its last line. An exit after a stream event keeps the old summary.
- **A3** — `ClaudeCode.resume` now passes `--model` like the launch. The default Codex (`-m`) and Cursor (`--model`)
  resume commands already passed it, so the brief's "all three drop it" was out of date for those two; the new tests
  pin all three, with and without `harness_model`, and with no model (no flag).

## Not changed / notes

- `specy_road/bundled_scripts/role_prompt.py` (`prompt --channel cli` reviewer launch) resolves its own model id and
  was not in the zones; it does not read `harness_model` yet.
- `sr/schemas/orchestration.schema.json` (the toolkit roadmap's consumer copy) is not refreshed here.
- `docs/orchestration-models.md`: one paragraph and an example on `harness_model`, the warning and the early-exit summary.

## Verification

- `python -m pytest -q tests/test_roster_harness_model.py` → 11 passed.
- Red/green: with `worker_adapter_claude.py` and `worker_runner.py` at HEAD, the claude resume case and the early-exit
  test fail; with `worker_ops_launch.py` and `review_delegate.py` at HEAD, the delegate/message and review-delegate
  `harness_model` tests fail.
- Round 2, after the merge: `python -m pytest -q -n auto` → 3387 passed, 2 skipped (includes M11.27's
  `tests/test_m11_27_small_cli_fixes.py`); `specy-road file-limits`, `check_test_private_imports.py`, `ruff` and dogfood
  `validate` clean; `git merge-tree --write-tree HEAD origin/WIP/improvements-0-3-1` → clean.
- Round 1: `python -m pytest -q -n auto` → 3378 passed, 2 skipped. A previous full run had one failure in
  `tests/test_worker_queue_message.py::test_message_while_running_queues_and_delivers`, which polls on wall-clock
  deadlines; it passed 3/3 alone and in the next full run.
- `specy-road file-limits` → OK. `python scripts/check_test_private_imports.py` → 0 new. `ruff check` on the changed
  files → clean. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` → 0.

## Added

- `orchestration_config.harness_model` — the one place the model id a harness is told is resolved (A1).
- `orchestration_config.harness_model_warnings` — the validate warning for a dotted claude-code id without `harness_model` (A1).
- Branch in `validate_roadmap.validate_orchestration_contract` printing those warnings (A1).
- Schema property `rosterEntry.harness_model` (A1).
- `--model` in `ClaudeCode.resume`'s default argv, with a one-line comment (A3).
- `specy_road/worker_exit.py` (new module, file-limit split): `exit_event` (the completion/error event `_finish` wrote
  inline; since the merge its exit-0 branch calls M11.27's `completion_summary` with the turn's `before_all`), `streamed` (did this turn give a stream event), `last_error_line` (the turn's log tail reason), `TAIL_BYTES` (A2).
- `log_start` in `worker_runner.run` and the `log_start` parameter of `_finish` — this turn's part of the log only (A2).
- `tests/test_roster_harness_model.py` (new): resolver precedence; schema + validate warning; worker delegate and
  message argv with and without `harness_model` (public path, `spawn` patched as other tests do); review delegate argv
  via a fake `claude` on `PATH`; resume argv per harness with/without `harness_model` and with no model; early-exit
  summary; plain summary after a stream event; only this turn's log is quoted.
- Mocks: `ops.spawn` patched to collect launches; a fake `claude` executable on `PATH` in a tmp dir.
