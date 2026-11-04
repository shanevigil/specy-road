# M11.33 implementation summary — dynamic-routing reviewers

Implementation commit: `f116f383` on `feature/rm-dynamic-routing-reviewers` (base `232df5b8`); the commit that adds
this summary also adds the unbalanced-quote test case.

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
- **A2 — requested / observed model.** The wrapper's `launched` event detail now has `model` (the launch argv's
  `--model`, `None` for a custom command). `worker_runner._consume` adds `model` to a worker `started` event when
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

Final list: the brief's zones plus **`specy_road/worker_models.py`** (new). `worker_runner.py` was at 395/400
lines; the new turn-model helpers went into that module so the runner stays at 399. Please add it to the leaf's
touch zones. `review_gate.py` stays at 400 (the docstring bullet was re-wrapped, not shortened, to name the rule).

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

## Added

- `orchestration_config.entry_routing` — classifies an entry as fixed or dynamic, including the Cursor no-model/auto rule (A1, A4).
- `orchestration_config.routing_problem` — the gate's reason an approval does not count toward distinct families (A1).
- Branch in `entry_routing`: `except ValueError` around `shlex.split(cli)` — an unbalanced quote in a cursor `channels.cli` reads as no model (dynamic) instead of crashing the gate (the schema does not refuse such a command; only the launch does); reached by the unbalanced-quote case of the parametrized gate test.
- `review_gate._eligibility` gains a `repo_root` parameter and the `routing_problem` call (A1).
- `worker_adapter_parsers.init_model` — the `model` a `system/init` line reports (A2).
- New module `specy_road/worker_models.py`: `turn_models` (the turn's requested and observed model) and `mismatch_note` (the usage-summary suffix worker sync prints) (A2; split for the file limit).
- `worker_runner`: `model` on the `launched` event detail; `model` on a worker `started` event from its init line; `requested_model` / `observed_model` in every usage event; the `OSError` path passes its own requested model (A2).
- Schema: `rosterEntry.routing` (enum fixed|dynamic) and `rosterEntry.pinned` (boolean) (A1).
- Test `tests/test_dynamic_routing_reviewers.py::test_dynamic_routing_approval_does_not_count_toward_distinct_families` — parametrized: routing absent, fixed, dynamic, dynamic+pinned, cursor with no model, cursor `auto`, cursor custom cli without `--model`, cursor custom cli with an unbalanced quote, cursor with a model, cursor+pinned; checks pass/approval count, the problem text and the handoff-status eligibility row (A1, A3, A4).
- Test `tests/test_dynamic_routing_reviewers.py::test_dynamic_routing_still_blocks_and_counts_without_distinct_families` — reaches the `verdict != approve` and distinct-families-off branches of `routing_problem` (A1).
- Test `tests/test_worker_cli.py::test_usage_keeps_requested_and_observed_model_and_sync_flags_a_mismatch` — parametrized match / mismatch through the real wrapper and `worker sync` output (A2, A3).
- Extended expectations (no test loosened): `test_usage_events_per_turn_and_the_usage_command` now expects `requested_model: None, observed_model: "claude-opus-5-5"` in the Claude usage detail; `test_launch_events_ack_time_and_timeline` expects `model: None` in the `launched` detail (custom command).
- Mocks: none.
