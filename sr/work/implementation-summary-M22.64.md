# Implementation summary: M22.64 (`reviewer-and-rca-launch-paths`)

## What changed

- **A1 (rca on stdin).** `harness-facts.yaml`'s `codex` `executor_template.value` now ends `- < {prompt}` instead of
  `"<prompt>"`; its `source` names the codex adapter's stdin launch (`specy_road/worker_adapter_codex.py`).
  `refresh-profiles --render` (run against `project_template_root()`) re-rendered the four OpenAI GPT profiles'
  `access.cli` and the README harness block; `refresh-profiles --check` reports no drift and
  `tests/test_harness_facts.py::test_the_shipped_profiles_are_already_rendered_from_the_fixture` passes. The
  hand-written "Headless invocation" table row for GPT Sol in `model-profiles/README.md` was updated to the same form.
  No Python launch code changed; `oversized_arg` and its tests are unchanged.
- **A2 (not-run test).** `PROBE_RULES_LINES` rule 1 (`specy_road/review_record_rules.py`) gains the sentence: if the
  sandbox prevents a test from running, name the command and its error as not run in the notes; on an approve,
  include the existing `not a defect because <reason>` explanation; do not put the command in `commands_rerun`; the
  absence of that run alone is no block. Prompt text only: `review record` and the gate are unchanged.
- **A3.** Tests below; `docs/orchestration-harness-launch.md` (the bundled OpenAI profiles read the rca prompt on
  stdin; the others still pass `"<prompt>"` and are refused over 128 KiB); `CHANGELOG.md` `[Unreleased]` → `### Fixed`.
- Not changed: the research notes in `gpt-6-sol.md` / `gpt-6.1-sol.md` that quote the vendors' `"<prompt>"` syntax
  (they report what the research runs found, not the command specy-road runs).

## Touch zones

Final list is the planned list, unchanged; every changed file is inside it. `file-limits` passes with no new warning.

## Verification

- `pytest -n 4 tests/test_harness_launch.py tests/test_review_record_rules.py tests/test_harness_facts.py`: pass.
- Full suite `pytest -n 4`: 7150 passed, 18 skipped.
- `refresh-profiles --check` on the shipped templates: no drift. Dogfood `validate`, `export --check`,
  `digest --check`: exit 0. `file-limits`: OK.
- Red/green: with the gpt-6.1-sol profile's `access.cli` put back to `"<prompt>"`, the new rca test fails
  (`prompt ... --run` exits 1, the oversized-argument refusal); with the fix it passes.

## Added

- Test `tests/test_harness_launch.py::test_an_rca_prompt_over_the_limit_reaches_the_bundled_codex_profile_on_stdin`: the "rca stdin" and "rendered" rows: a real `prompt <leaf> --role rca --model sol --channel cli --force --reason x --run` with the bundled gpt-6.1-sol profile and a >128 KiB prompt exits 0, the fake `codex` gets the whole prompt on stdin with `-` last, no argument over 32 KiB, and all four shipped OpenAI profiles' `access.cli` end `- < {prompt}`.
- Constants `FAKE_CODEX`, `SOL_ROSTER` in that test file: the fake harness on PATH (records argv and stdin size) and the roster with a separate blocking reviewer (the analyst may not have reviewed the leaf).
- Monkeypatch of `subprocess.run` in that test, wrapping the real call: records the shell command `run_plain_cli` gives `sh -c` so its size can be checked; it still runs the command.
- Test `tests/test_review_record_rules.py::test_a_not_run_test_does_not_meet_the_rerun_policy` (parametrized): the "not run, no rerun" (refused with the existing rerun refusal) and "not run, with rerun" (filed) rows through the public `file_review` under `reviewer_reruns_required: true`.
- Constant `NOT_RUN` in that file: the not-run notes line with its sandbox error and `not a defect because` reason.
- Extended `test_reviewer_prompt_carries_the_four_probe_rules`: the "reviewer rule" row (rule 1 carries the not-run sentence, the notes, the explanation and "not `commands_rerun`").
- Helpers, branches, guards: none.
