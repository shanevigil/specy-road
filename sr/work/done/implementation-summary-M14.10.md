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

## Fix round 1 (gpt-6.1-sol-low blocked 4009a140)

Before this round I merged `origin/WIP/improvements-0-3-1` into the branch (merge commit `86d379a4`).

**Finding class:** convergence was declared on incomplete evidence. A window shorter than `n = escalate_same_acceptance_blocks`, for example the 2 rounds 5, 1 with n=3, counted as converging and deferred `review_rounds` when `escalate_review_rounds < n`. The same class covers a round whose count is unknown, and n=1, where a count cannot fall inside the window.

**Design fix:** `review_trend.converging` is now the single place that decides convergence, and it returns false unless it has at least `n` rounds (and n ≥ 2) since the last RCA, each with a known count. `round_findings` returns `None` when a blocking record lacks a list for any of the four categories. That cannot happen for a valid record (the schema requires all four, and `review_rounds` keeps only valid records), but it means an unknown count can never count as evidence. The trend line prints such a count as `?`. Both callers (`escalation()` and `loop_state()`) pass the same window, `rounds[resolved:]`, so neither can see a different window. The design note states the rule.

## Probes

- `converging([5, 1], 3)`, the reviewer's case: was True, now False. A CLI replay with `escalate_same_acceptance_blocks: 3, escalate_review_rounds: 2` and counts 5, 1 with acceptance passing now escalates at round 2 on `review_rounds`, with `converging` and `escalation_deferred` both false. This test fails against `4009a140`'s `review_trend.py` (exit 1) and passes now.
- Boundary grid with n=3. At n-1 rounds (5, 1) with `escalate_review_rounds` 2, 3 and 4, the results are `review_rounds`, none and none, and nothing is deferred. At n rounds (5, 1, 1) with 2, 3 and 4, the deferral is true, true and false. At n+1 rounds (5, 1, 1, 0) with 2, 4 and 5, it is true, true and false. A deferral is reported only when an escalation was actually due.
- Window after an RCA: rounds 9, 5, 1 with `resolved=1` leave a window of 5, 1, which is shorter than 3, so the loop is not converging and `review_rounds` (2) escalates.
- Threshold 1: `converging(..., 1)` is always false, so nothing is deferred.
- Unknown count: a blocking record missing its `boundary` list gives `None`; the loop is not converging, and `same_family` still escalates.
- `loop_state` uses the same `converging(rounds[resolved:], n)` call, so the status flags match `escalation()`. The CLI test checks this.
- `_rca_semantic_errors` calls `escalation()`, so RCA trigger validation uses the corrected window. No other module calls `converging`; I checked with `grep -rn "converging(" specy_road`.
- A1 trend line: `_line` is unaffected except that an unknown count prints as `?`. The earlier 13, 2, 2, 1, 0 CLI test still passes.

## Verification

- `python -m pytest -q -n 4 tests/test_review_trend.py tests/test_review_rca.py tests/test_review_cli.py`: 59 passed (after fix round 1).
- Full suite `python -m pytest -q -n 4`: 4124 passed (before the test-helper change, which touched only `tests/test_review_trend.py`).
- `specy-road file-limits`: OK (`review_cli.py` 400, `review_rca.py` 384).
- `ruff check specy_road tests scripts`: clean.

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
- `tests/test_review_trend.py` `run_cli` and `node_status`: public helpers defined in the test file. They run `review_cli.main` and read `handoff status --json`, so the test imports no underscore-prefixed name from another test module.
- `tests/test_review_trend.py`, CLI tests that replay 13, 2, 2, 1, 0 through `review record` and `handoff status`:
  - the text and `--json` trend, and the `converging; escalation deferred` line (A1/A2);
  - the same replay with policy true escalates and prints no deferral (A3).
- Fix round 1, in `review_trend.converging`: guards that return false for fewer than `n` rounds, for `n < 2`, and for any unknown count, so incomplete evidence never defers an escalation.
- Fix round 1, in `review_trend.round_findings`: returns `None` when a blocking record lacks a category list, so an unknown count is explicit rather than 0.
- Fix round 1, `tests/test_review_trend.py::test_convergence_needs_a_full_window_at_every_threshold`: parametrized over n-1, n and n+1 rounds and `escalate_review_rounds` below, equal to and above n.
- Fix round 1, `test_rounds_before_an_rca_are_not_convergence_evidence`: the window after an RCA.
- Fix round 1, `test_threshold_one_or_an_unknown_count_never_converges`: the n=1 and unknown-count members of the class.
- Fix round 1, `test_cli_two_falling_rounds_below_the_window_escalate_on_review_rounds`: the reviewer's public CLI regression (thresholds 3 and 2, counts 5, 1).
