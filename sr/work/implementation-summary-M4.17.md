# Implementation summary: M4.17 — review-loop escalation and root-cause analysis

Base: `73f7b23` (merge of `origin/WIP/improvements-0-3-1`, which widened the touch zones). Feature commits: `59cbc54` (implementation), `9d4bd562` (round-1 review fixes), plus follow-up commits on this branch. Executor hand-off: `composer-2.5`.

## Round 2 (REVIEW-gpt-5.6-sol-high.md)

- `loop_state` now semantically validates each schema-valid RCA before it advances `resolved`: it replays `escalation` on the history prefix through `trigger.round` (with `resolved` from earlier valid records only) and requires matching `trigger.rule` and `acceptance_ids`, plus a rostered independent analyst (`is_rostered_reviewer` or active substitution, and not in `rca_parties`). A mismatched or non-independent record stays invalid and leaves escalation active (A4, A5).

## Round 1

- The design note no longer attributes Google's flake rule, the Debugging Decay Index, or the Claude Code 8.9%→1.5% result to both reports: those are the Claude report's, and the OpenAI report's own wording ("three strikes", CI retries flaky tests 2–3 times) is what the note states. "No debate and no self-critique" moved out of the agreement list; the note follows the Claude report there, against the OpenAI report's self-reflection ranking. The sentence that said the note is wrong wherever it disagrees with the code is gone.
- `rca_preamble` step 5 now says a valid record clears the escalation and an invalid one is listed as a problem.
- Every round's diff in the RCA prompt is a full `git diff`, including round 1. The prompt no longer claims the full diff is in the review packet.
- `review_rounds` keys a round by `full_sha` when the commit resolves, and by the raw string when it does not, so a short SHA and the full id of one commit are one round and the later record per model wins. The note's round definition says the same.

## Acceptance

- **A1** — `docs/design-notes/review-loop-rca.md` folds both research reports (OpenAI and Claude runs). It covers where they agree, the triggers and signals adopted, the protocol, the record schema, and what is deferred: the oscillation, novelty and pre-existing-share triggers; the deterministic preflight; k=3 voting; the oracle probe; enforcement in the gate; and retrieval and evaluation. Where the reports differ, the note says which one it follows and why. It keeps 5 rounds, which matches the OpenAI report and A2; the Claude report's hard stop is at 6. History is shown side by side, as the Claude report recommends.
- **A2** — Records are overwritten each round, so `review record` now keeps a copy of every record it files under `work/reviews/<ID>/history/`. The gate still reads only the top-level `REVIEW-*.md`.
  - A round is one reviewed commit. It blocks on `A<n>` when a blocking record at that commit (the latest one per model) fails `A<n>`.
  - `handoff status` and `review list` escalate when the last `escalate_same_acceptance_blocks` (default 3) rounds all block on one id, or when `escalate_review_rounds` (default 5) rounds have passed since the last analysis.
  - Both thresholds are in the orchestration schema, `DEFAULT_POLICY` and the starter `orchestration.yaml`. They are read from the integration branch, like the rest of the gate's policy.
- **A3** — `handoff status` reports state `escalated` (exit 1) whenever the gate has not passed. `--json` carries `escalation` with the rule, round, acceptance ids, threshold and a description; the text output adds a line naming the trigger and the next command.
  - `prompt <ID> --role rca --model <id>` builds the prompt from three sources: the brief with its acceptance criteria, every round's records side by side (verdict, failed ids, findings, required changes, notes), and the diffs. Round 1 gets a stat against the base; later rounds get the full diff since the previous round.
  - The prompt asks for one of the six classes, evidence for and against each class, a counterfactual, a check where one settles the question, and the cheapest action. For a `specification` cause it also asks for a bounded rewrite of the criterion and a disposition for each past finding.
  - It refuses when the loop is not escalated. It also refuses a model that implemented the leaf (a READY `agent`) or reviewed it, as the research recommends.
- **A4** — The analyst writes `work/reviews/<ID>/RCA-<round>.md`, validated against `specy_road/schemas/rca-record.schema.json`. A specification cause requires `criterion_rewrite`, and a `trigger.round` beyond the history makes the record invalid.
  - Schema validation is not enough: the record's trigger must match the escalation replayed at that round, and its `model` must be a rostered reviewer (or substitute) who did not implement or review the leaf. Otherwise it is listed as a problem and resolves nothing. A valid record resolves every round up to its `trigger.round`, and counting starts again after it.
  - Until one exists, reviewer prompts include a "Loop escalated" section.
- **A5** — Thresholds, signals, protocol and record follow the design note. No tracked research prompt or register entry exists in this checkout; the reports are only at the untracked absolute paths, so the note is the tracked record.

## Decisions

- `rca` is not a roster role or a profile score. `model_profiles.ROLES` is outside the touch zones and also drives per-role profile scores, so `role_prompt.py` accepts `PROMPT_ROLES = (*ROLES, "rca")`. The analyst must hold the `reviewer` role (or an active substitution).
- The analyst writes the RCA record directly; `handoff status` and `review list` validate it. There is no filing command, to keep the CLI surface small.
- The interactive human approval (`write_human_approval`) is not copied into `history/`. It only approves, so it never adds a block.

## Final touch zones used

`specy_road/bundled_scripts/review_cli.py`, `specy_road/bundled_scripts/role_prompt.py`, `specy_road/review_files.py`, `specy_road/review_rca.py`, `specy_road/orchestration_config.py`, `specy_road/schemas/`, `specy_road/templates/project/schemas/`, `specy_road/templates/project/roadmap/`, `specy_road/templates/specyrd/commands/`, `docs/orchestration.md`, `docs/design-notes/review-loop-rca.md` and `tests/`. Zones not needed: `specy_road/review_gate.py`, `schemas/` (no such directory at the git root) and `docs/pm-llm-review.md` (it covers the PM GUI's advisory review).

Left alone, outside the zones:

- `docs/design-notes/README.md`: the new note needs an index row there.
- `scripts/verify_wheel_contents.py`: it could list the new schema, which already ships through the `schemas/*.json` glob.
- `sr/schemas/orchestration.schema.json`: the project's copy; `specy-road refresh-schemas` updates it.

## Verification

- `pytest tests/test_review_rca.py tests/test_review_cli.py`: 21 passed (round 2 adds trigger/independence validation).
- Full `pytest`: 2395 passed, 2 skipped, 1 failed. The failure is `tests/test_validate_file_limits.py::test_file_limits_passes_on_repo`, on `specy_road/bundled_scripts/worker_cli.py` (408 lines) and `specy_road/worker_adapters.py` (430 lines). Both were already over at base `73f7b23` and this branch does not touch them.
- `specy-road file-limits`: only those two pre-existing failures. `docs/orchestration.md` stays at 399 lines.
- `ruff check` on the changed Python files: clean.

## Added

### Helpers
- `review_files.archive_review`: keeps every filed record, because `REVIEW-<model>.md` is overwritten each round.
- `review_files.list_review_history`: reads that history, oldest first.
- `review_files.list_rcas`: loads `RCA-*.md` with schema and `node_id` checks.
- `review_rca._trigger_ids`, `_rca_semantic_errors`: replay the escalation at `trigger.round` and enforce analyst independence when consuming an RCA file (round 2, A4, A5).
- `review_rca.Round`, `Escalation`, `LoopState`, `review_rounds`, `escalation`, `loop_state`: round grouping and trigger detection (A2, A4). `review_rounds` keys by `full_sha` so two spellings of one commit are one round (round 1). `loop_state` applies semantic RCA checks in trigger-round order before advancing `resolved` (round 2).
- `review_rca.escalated_note`: the reviewer-prompt section (A4).
- `review_rca.rca_parties`: excludes the leaf's executor and reviewers as analysts (research: independence).
- `review_rca.rca_preamble`, `_skeleton`, `rca_evidence`, `_record_lines`, `_diff`: the RCA prompt body (A3).
- `review_cli._escalation_line`, `_print_rcas`: status and list output.
- `role_prompt.PROMPT_ROLES`: adds `rca` without changing roster roles or profile scores.

### Branches and guards
- `escalated` state in `_node_status`, only when the gate has not passed (A3).
- `build_prompt` refuses `rca` when the loop is not escalated, and refuses a model that is a party. Both are reached by `test_rca_prompt_refuses_when_not_escalated_and_for_a_party`.
- `loop_state` marks an RCA record invalid when its `trigger.round` exceeds the history (agent input), so a bogus round cannot silence escalation. Reached by `test_rca_record_validates_and_resolves_the_escalation`.
- `loop_state` rejects RCAs whose trigger does not replay the active escalation or whose `model` is not an independent rostered analyst (round 2). Reached by `test_mismatched_or_non_independent_rca_keeps_escalation`.
- `_diff` falls back to "empty, or git could not produce it" when git output is empty (subprocess boundary, as in the review packet).
- The schema's `if`/`then` requires `criterion_rewrite` for a specification cause (A3, A4).
- `review list` prints the escalation only when the gate has not passed, consistent with `handoff status`.

### Mocks
- none

### Tests
- `test_three_rounds_blocking_on_one_id_escalate_status_and_list`: the same-acceptance trigger, text and JSON status, exit 1, `review list` (A2, A3).
- `test_total_rounds_threshold_comes_from_policy`: the rounds trigger and configurable thresholds (A2).
- `test_rca_prompt_carries_history_diffs_and_protocol`: prompt content (A3).
- `test_rca_prompt_refuses_when_not_escalated_and_for_a_party`: the two refusals (A3).
- `test_rca_record_validates_and_resolves_the_escalation`: invalid records (missing rewrite, round beyond history), a valid record resolving the trigger, `review list` output, and counting restarting (A4).
- `test_mismatched_or_non_independent_rca_keeps_escalation`: wrong trigger or party on a schema-valid RCA leaves escalation active (round 2, A4, A5).
- `test_reviewer_prompt_says_the_loop_is_escalated_until_an_rca_exists` (A4).
- `test_two_spellings_of_one_commit_are_one_round`: a short SHA and the full id are one round, and the later record is the one that counts (round 1).
- `test_design_note_attributes_each_report`: the fold attributes the flake rule, the Debugging Decay Index and the 8.9% result to the Claude report, states the OpenAI report's threshold wording, and keeps "no debate" out of the agreement list (round 1, A1).
- Extended `test_rca_prompt_carries_history_diffs_and_protocol`: round 1's diff is full (`+r = 1`), and step 5 says a valid record clears the escalation (round 1, A3).
- Changed: in `tests/test_review_cli.py::test_review_list_prints_records_and_the_gate_and_writes_nothing`, the writes-nothing snapshot now walks the reviews directory recursively. `review record` now creates `history/`, which `read_text` on the directory could not read; the check is stricter, not weaker.
