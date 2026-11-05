# Implementation summary: M14.10

Escalation recognises a converging loop and handoff status shows the findings trend.

## What changed

- **`specy_road/review_trend.py` (new).** `round_findings` counts every item in the four finding categories (`review_deferral.CATEGORIES`) of each blocking record in a round, summed across records. `converging(rounds, n)`: over the last `n` rounds the count never rose, fell at least once, and the latest round fails no acceptance id. `trend_status` builds the `findings_trend` status block: per-round `{round, findings, failing_acceptance}`, `converging`, `escalation_deferred`, and the printed lines (`findings by round: 13, 2, 2, 1, 0; acceptance all pass since round 2`, or `...; round N fails A1` when the latest round fails, plus `converging; escalation deferred (...)` when a rule was held back).
- **`specy_road/review_rca.py`.** `escalation()` checks `same_acceptance` first as before. Then, unless `policy.escalate_when_converging` is set, it returns `None` when the window since the last RCA is converging, which skips `same_family` and `review_rounds`. Forced escalation (`forced_escalation`) is unchanged, and `max_fix_rounds` (`review_next_step.fix_round_budget`) is independent of `escalation()`, so both still apply. `LoopState` gains `converging` and `deferred_converging`. The second is true only when re-running `escalation` with the policy set to true would have escalated. `LoopState.findings_trend()` returns the status block. RCA record validation (`_rca_semantic_errors`) goes through the same `escalation()`, so a record must match the convergence-aware trigger.
- **`specy_road/bundled_scripts/review_cli.py`.** No net line change (the file is at the 400-line cap). `_node_status` adds `"findings_trend": loop.findings_trend()` on the `review_rounds` line. `_render` prints its lines after the review-rounds line.
- **`specy_road/orchestration_config.py`.** `DEFAULT_POLICY["escalate_when_converging"] = False`.
- **`orchestration.schema.json`.** Adds the `escalate_when_converging` boolean to `$defs.policy`. Its description states the default change and that `true` restores the earlier behaviour.
- **`docs/design-notes/review-loop-rca.md`.** New subsection, "Converging loops are not escalated by round count", covering the rule, why it exists (the 13, 2, 2, 1, 0 run), what still applies, and the default change.

## Touch zones

All edits are inside the listed zones. `specy_road/review_status_render.py` was not needed: the rendering lives in `review_trend.py`. Not changed: `specy_road/templates/project/roadmap/orchestration.yaml` lists the other escalate keys, but it is outside the zones. A3 asks only for the schema and defaults, so the new key is not added to that template.

## Verification

- `python -m pytest -q -n 4 tests/test_review_trend.py tests/test_review_rca.py tests/test_review_cli.py`: passes.
- Full suite `python -m pytest -q -n 4`: 4124 passed.
- `specy-road file-limits`: OK (`review_cli.py` 400, `review_rca.py` 384).
- `ruff check` on the changed Python: clean.

## Added

- `review_trend.round_findings`: per-round count of blocking findings across all four categories (A1/A2).
- `review_trend._ids`: sorts acceptance ids numerically for stable output.
- `review_trend.converging`: the convergence rule (A2).
- `review_trend._line`: the `findings by round: ...` text, either "acceptance all pass since round N" or "round N fails ..." (A1).
- `review_trend.trend_status`: the `findings_trend` status and JSON block, including the deferred line (A1/A2).
- Branch in `review_rca.escalation`: return `None` before `same_family`/`review_rounds` while converging and the policy is false (A2/A3).
- `LoopState.converging`, `LoopState.deferred_converging`, `LoopState.findings_trend()`: carry the flag and trend to status without a new import in the capped `review_cli.py` (A1/A2).
- In `loop_state`: a second `escalation` call with the policy forced true, used only to decide whether anything was actually deferred, so "escalation deferred" is not printed for a loop that would not have escalated anyway (A2).
- `DEFAULT_POLICY["escalate_when_converging"]` and the schema property (A3).
- `tests/test_review_trend.py`, unit tests using fake `Round`s built from `SimpleNamespace` records (no repo needed to replay series):
  - 13, 2, 2, 1, 0 with passing acceptance never escalates at any prefix (A3);
  - flat or rising series (3, 3, 3; 2, 4, 1; 5, 5, 4, 6, 3) still escalate (A3);
  - a failing acceptance id in the latest round escalates (A2);
  - policy true restores `same_family`/`review_rounds` (A3);
  - `same_acceptance` still fires while counts fall (A2);
  - the default and the schema carry the key (A3).
- `tests/test_review_trend.py`, CLI tests that replay 13, 2, 2, 1, 0 through `review record` and `handoff status`:
  - the text and `--json` trend, and the `converging; escalation deferred` line (A1/A2);
  - the same replay with policy true escalates and prints no deferral (A3).
