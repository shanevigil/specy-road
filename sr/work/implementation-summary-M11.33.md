# M11.33 implementation summary — dynamic-routing reviewers

Implementation commit: `f116f383` on `feature/rm-dynamic-routing-reviewers` (base `232df5b8`); `5bd9b720` added this
summary and the unbalanced-quote test case; `e7ef2a38` answered the block at `5bd9b720` (see "Review round 2"),
and the round-3 commit (this summary's latest) answers the block at `e7ef2a38` (see "Review round 3").

## Review round 3 — gpt-5.6-sol-medium block at `e7ef2a38`

1. **Model from the actual harness invocation, or unknown (A2, A4).** Round 2's `launch_model` and the gate's
   `entry_routing` took the first `--model` anywhere in a custom shell program, so
   `printf ... --model fixed >/dev/null; agent -p {prompt}` counted an Auto-routed Cursor approval and recorded a
   decoy `requested_model`. New `worker_models.command_model(command)`: a command's `--model` / `-m` only when it is
   one simple command. Outside literal spans (single quotes, double quotes without a substitution, backslash
   escapes) it must contain no `;`, `&`, `|`, `(`, `)`, backtick, newline or `$(`; the redirections `2>&1`, `<&3`
   and `&>file` are allowed. Anything else returns `None`, the conservative reading the reviewer allowed.
   - Both callers use it. `entry_routing` (local import) makes a cursor entry whose `channels.cli` is a list or
     pipeline `dynamic`. `launch_model` records `requested_model: null` for such a launch, so no decoy and no
     false mismatch reach `worker sync`.
   - `launch_model` moved from `worker_adapter_parsers.py` into `worker_models.py` beside it. `entry_routing`'s
     own `shlex.split` / `except ValueError` moved into `command_model`, which keeps the unbalanced-quote handling.
   - Public-path regressions in `tests/test_dynamic_routing_reviewers.py`:
     - The gate test gains a cursor `channels.cli` of
       `printf %s --model gpt-5.6-sol >/dev/null; agent -p {prompt}`, which must not count, and
       `agent -p --model gpt-5.6-sol {prompt} 2>&1`, which counts: a redirection is not a list.
     - The `worker delegate` custom-cli test gains `printf %s --model decoy >/dev/null; <fake harness> {prompt} --model claude-sonnet-5-5`:
       `requested_model` is `null`, `observed_model` is `fake`, and `worker sync` prints no mismatch and no `decoy`.
   - Red-green: at `e7ef2a38` with the new test file, both decoy cases fail (2 failed, 16 passed); with the fix all pass.
   - `docs/orchestration-models.md` states the one-simple-command rule in the `routing` row and the `requested_model` sentence.
   - A wrapper script that is one simple command (`run-cursor.sh --model x {prompt}`) is still read as passing
     `x`. Its program name is not checked against the harness binary; `pinned` stays the maintainer's attestation
     either way.

## Review round 2 — gpt-5.6-sol-medium block at `5bd9b720`

1. **Requested model through custom-command launches (A2).** A roster `channels.cli` launch is
   `Launch(["sh", "-c", <command>])`, so `model_from_argv(launch.argv)` read no `--model`. New
   `worker_adapter_parsers.launch_model(argv)`: the argv's `--model` / `-m`, else, for exactly `["sh", "-c", cmd]`,
   the `--model` / `-m` among `cmd`'s shell words (the `_WORD` tokenizer `output_mode_note` already uses, quotes
   stripped; it never raises). `worker_runner` uses it for the `launched` event's `model` and for the `OSError`
   path's `requested_model`, so `requested_model` and the `worker sync` mismatch suffix cover custom commands.
   `model_from_argv` itself is unchanged (it also feeds the roster price estimate). Regression test, public path:
   `tests/test_dynamic_routing_reviewers.py::test_custom_cli_model_is_requested_and_sync_flags_a_mismatch`
   runs `worker delegate` with a roster `channels.cli` ending `--model <told>` against the fake harness (whose
   `system/init` reports `fake`): `told=claude-sonnet-5-5` records `requested_model: claude-sonnet-5-5`,
   `observed_model: fake` and `worker sync` prints `model mismatch: told claude-sonnet-5-5, harness reported fake`;
   `told=fake` records both and prints no mismatch. Red-green: with the runner's two `launch_model` calls put back
   to `model_from_argv`, both cases fail (2 failed); with the fix, both pass. `docs/orchestration-models.md` now says
   `requested_model` includes a `channels.cli`'s own `--model` (it said `null` for a custom command).
2. **`specy_road/worker_models.py` boundary.** On the coordinator's instruction, added to this leaf's touch zones on
   this branch with `specy-road edit-node M11.33 --add touch_zones=specy_road/worker_models.py` (commits
   `sr/roadmap/phases/M11__174228.json` and the claim's zones in `sr/roadmap/registry.yaml`). Why it exists:
   `worker_runner.py` was at 395 of its 400-line cap, and the turn-model helpers (`turn_models`, `mismatch_note`)
   would have pushed it over; the runner is at 399 with them in the new module.

Also in this round: `tests/test_worker_cli.py` went over its 400-line cap with the new test, so both M11.33 worker
tests (`test_usage_keeps_requested_and_observed_model_and_sync_flags_a_mismatch` and the new one) moved, unchanged
apart from imports, into `tests/test_dynamic_routing_reviewers.py`. `specy-road digest --check` (project root `sr/`)
reports `sr/roadmap-context.md` drift; it reports the same at `5bd9b720` before the `edit-node` change, and
that file lists no touch zones, so it is left alone.

## What changed

- **A1 — roster `routing` / `pinned`, gate filter.** `orchestration.schema.json` accepts `routing: fixed|dynamic`
  (absent = fixed) and `pinned: boolean` on a roster entry. `orchestration_config.entry_routing(repo_root, entry)`
  classifies an entry; `orchestration_config.routing_problem(repo_root, config, data)` returns why an approval does
  not count: the verdict is `approve`, `policy.reviewers_distinct_families` is on, the entry is not `pinned` and
  its routing is `dynamic`. `review_gate._eligibility` chains it with the other "does not count" reasons (it now
  takes `repo_root`), so the approval lands in `GateResult.ineligible`. `GateResult.problems()` (which `handoff
  status` and `review list` print) says `does not count — '<model>' runs on a harness that routes models
  dynamically … until its roster entry sets pinned: true`. `handoff status`'s "who can still supply a counting
  approval" row shows the same reason through `review_eligible._rejected` (unchanged). A block from a dynamic entry
  still counts, and with distinct families off a dynamic approval counts as before. `prior_approvals` uses the same
  `_eligibility`, so a dynamic approval cannot be a delta-review basis under distinct families either.
- **A4 — Cursor Auto.** `entry_routing` returns `dynamic` for a `cursor` entry whose launch model is `None` or
  `auto` (case-insensitive), whatever `routing` says: the model is the custom `channels.cli`'s `--model`/`-m`
  (via `model_from_argv` on `shlex.split`), else `harness_model(entry, profile api_id)` with the committed profile
  from `pinned_profile_for_entry`, `""` when there is no valid profile — the same value `review delegate` passes.
  `pinned: true` still overrides it (the maintainer's attestation).
- **A2 — requested / observed model.** The wrapper's `launched` event detail now has `model` (the launch's
  `--model`, a custom `sh -c` command's included: `worker_adapter_parsers.launch_model`; `None` when it passes none). `worker_runner._consume` adds `model` to a worker `started` event when
  the line is a `system/init` with a `model` (`worker_adapter_parsers.init_model`; Claude Code and Cursor print
  one, Codex does not). Each `usage` event detail now has `requested_model` and `observed_model` for the current
  turn (events since the last `launched`, `worker_models.turn_models`), beside `harness_version`; a turn that never
  launched (`OSError`) passes its own requested model and `observed_model: null`. When both are known and differ
  (ignoring case), the usage summary ends `; model mismatch: told X, harness reported Y`, which `worker sync`
  prints (`worker_models.mismatch_note`). The worker-event schema's usage `$defs` already allows extra keys.
- **A3 — docs.** `docs/orchestration-models.md` has a new section "Harnesses that route models": the rule
  (cascades, Auto and an internal critic can put the executor's family on the reviewer side), the `routing` /
  `pinned` table, the Cursor default, that a block still counts, that a harness's internal critic is supporting
  evidence and never a gate approval, and the `requested_model` / `observed_model` / mismatch fields.
  `docs/orchestration.md` (at its 400-line cap) names `routing` and `pinned` in the "Roster entries also accept"
  sentence and links that section.

## Touch zones

Final list: the brief's zones plus **`specy_road/worker_models.py`** (new), now in the node's touch zones (review
round 2, item 2). `worker_runner.py` was at 395/400 lines; the new turn-model helpers went into that module so the
runner stays at 399. `review_gate.py` stays at 400 (the docstring bullet was re-wrapped, not shortened, to name the rule).

Not changed, outside the zones, possible follow-ups:

- `specy_road/review_eligible.py`: before a dynamic entry files anything, its row still reads "can approve"; once
  it files, the row says why it does not count. A pre-filing hint would need this file.
- `docs/orchestration-workers.md`'s usage-detail table does not list `requested_model` / `observed_model` (they
  are documented in `orchestration-models.md`).
- `suggested_prompts/bootstrap-roadmap.md` lists optional roster fields; it already omits `harness_model`,
  `available` and others, so `routing` / `pinned` were not added there.

## Verification

- `specy-road file-limits`, `ruff check specy_road tests scripts`, `python scripts/check_test_private_imports.py`,
  `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`: all exit 0.
- Full suite, split in two halves to fit the harness's 10-minute command limit
  (`ls tests/test_*.py | sort`, files 1–155 and 156–310), `pytest -n 4`: first half 1869 passed, 2 skipped;
  second half 1800 passed with `tests/test_worker_queue_message.py::test_message_while_running_queues_and_delivers`
  deselected. That test failed twice in the second half under load (`state 'running' == 'idle'`): it reads the
  record between the second turn's `completion` event and `_exit_state`'s `idle` write (`mirror_logs` runs in
  between), and this change adds nothing in that window. It fails the same way at the base commit `232df5b8` under
  the same load (`pytest -n 6` over `tests/test_worker*.py`: base 1 failed, head 0 failed), and passes on its own
  (`pytest tests/test_worker_queue_message.py`, 6 passed, three runs). Pre-existing flake, not fixed here.
- `scripts/check_clones.py` (pylint R0801) was not run: `pylint` is not installed in this environment.
- Red-green: in a worktree at the base commit with the new test files copied in, `tests/test_dynamic_routing_reviewers.py`
  and the new `test_worker_cli.py` test failed (10 failed, 2 passed before the unbalanced-quote case was added: the two cases that need no new schema key or
  behaviour — routing absent, and cursor with an explicit model — pass at base too).

## Verification, round 2

- `pytest -n 4 tests/test_dynamic_routing_reviewers.py tests/test_worker_cli.py tests/test_review_gate.py
  tests/test_orchestration_config.py tests/test_worker_adapters.py tests/test_roster_harness_model.py`: 95 passed.
- `pytest -n 4` over every `tests/test_worker*.py`: 259 passed.
- `specy-road file-limits`, `ruff check specy_road tests scripts`, `python scripts/check_test_private_imports.py`,
  `specy-road validate`, `specy-road export --check`: exit 0.

## Verification, round 3

- `pytest -n 4 tests/test_dynamic_routing_reviewers.py tests/test_worker_cli.py tests/test_review_gate.py
  tests/test_orchestration_config.py tests/test_worker_adapters.py tests/test_roster_harness_model.py`: 98 passed.
- `pytest -n 4` over every `tests/test_worker*.py`: 259 passed. An earlier run of the same set hit the known
  `test_message_while_running_queues_and_delivers` race; it fails the same way at base `232df5b8` (round 1). It
  passed alone (6 passed) and in the re-run.
- `specy-road file-limits`, `ruff check specy_road tests scripts`, `python scripts/check_test_private_imports.py`,
  `specy-road validate`: exit 0.

## Added

- `orchestration_config.entry_routing` — classifies an entry as fixed or dynamic, including the Cursor no-model/auto rule (A1, A4).
- `orchestration_config.routing_problem` — the gate's reason an approval does not count toward distinct families (A1).
- `except ValueError` around `shlex.split` (in `entry_routing` until round 3, now in `command_model`) — an unbalanced quote in a cursor `channels.cli` reads as no model (dynamic) instead of crashing the gate (the schema does not refuse such a command; only the launch does); reached by the unbalanced-quote case of the parametrized gate test.
- `review_gate._eligibility` gains a `repo_root` parameter and the `routing_problem` call (A1).
- `worker_adapter_parsers.init_model` — the `model` a `system/init` line reports (A2).
- `worker_models.launch_model` (round 2 in `worker_adapter_parsers`, moved in round 3) — the requested model of a launch, reading inside a custom `sh -c` command through `command_model` (A2); its `sh -c` branch is reached by the custom-cli test, the plain-argv branch by the flat-argv test.
- `worker_models.command_model` with `_LITERAL`, `_REDIRECT_AMP`, `_CONTROL` — a shell command's `--model` only when it is one simple command, else unknown (A2, A4; review round 3); the list case is reached by both decoy regressions, the redirection allowance by the `2>&1` gate case, the `except ValueError` by the unbalanced-quote gate case.
- New module `specy_road/worker_models.py`: `turn_models` (the turn's requested and observed model) and `mismatch_note` (the usage-summary suffix worker sync prints) (A2; split for the file limit).
- `worker_runner`: `model` on the `launched` event detail; `model` on a worker `started` event from its init line; `requested_model` / `observed_model` in every usage event; the `OSError` path passes its own requested model (A2).
- Schema: `rosterEntry.routing` (enum fixed|dynamic) and `rosterEntry.pinned` (boolean) (A1).
- Test `tests/test_dynamic_routing_reviewers.py::test_dynamic_routing_approval_does_not_count_toward_distinct_families` — parametrized: routing absent, fixed, dynamic, dynamic+pinned, cursor with no model, cursor `auto`, cursor custom cli without `--model`, cursor custom cli with an unbalanced quote, cursor with a model, cursor+pinned; checks pass/approval count, the problem text and the handoff-status eligibility row (A1, A3, A4).
- Test `tests/test_dynamic_routing_reviewers.py::test_dynamic_routing_still_blocks_and_counts_without_distinct_families` — reaches the `verdict != approve` and distinct-families-off branches of `routing_problem` (A1).
- Test `tests/test_dynamic_routing_reviewers.py::test_usage_keeps_requested_and_observed_model_and_sync_flags_a_mismatch` (moved from `test_worker_cli.py` for its file limit) — parametrized match / mismatch through the real wrapper and `worker sync` output, argv `--model` (A2, A3).
- Test `tests/test_dynamic_routing_reviewers.py::test_custom_cli_model_is_requested_and_sync_flags_a_mismatch` — parametrized match / mismatch / decoy-before-the-harness through `worker delegate` with a roster `channels.cli` (A2, review rounds 2 and 3).
- Gate test cases (round 3): cursor `channels.cli` with a decoy `--model` before `agent` (dynamic) and with `2>&1` after an explicit model (fixed).
- Touch zone: `specy_road/worker_models.py` added to M11.33 with `specy-road edit-node` (review round 2 item 2).
- Extended expectations (no test loosened): `test_usage_events_per_turn_and_the_usage_command` now expects `requested_model: None, observed_model: "claude-opus-5-5"` in the Claude usage detail; `test_launch_events_ack_time_and_timeline` expects `model: None` in the `launched` detail (custom command).
- Mocks: none.
