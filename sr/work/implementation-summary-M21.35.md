# Implementation summary: M21.35 — refused review gets one repair turn

Branch `feature/rm-refused-review-gets-one-repair-turn`, base `dee07131`, change commit `3855bf46`.

## What changed

- **A1, prompt** — `review_record_rules.NOTES_RULES_LINES` holds the approve-notes rules in operational form: one
  observation per line; every findings entry, and every notes line of two words or more other than a heading,
  a bare `A1: pass`, a `>` quote, fenced code or a table separator, either matches a `required_changes` entry
  (block) or carries 'not a defect because <reason>' on that line, outside backticks, with a reason that names no
  defect; `A1: pass` with more words is an observation; each clause split on '. ', '; ' or a conjunction (and,
  but, while) is checked on its own; a comma list is several observations; evidence goes in `commands_rerun`.
  `schema_lines()` places them after the intro paragraph and immediately before the JSON schema fence. Rule 4 of
  `PROBE_RULES_LINES` keeps its first sentence and points to that section. The rule code (`clause_problem`,
  `_second_observation`, `note_problem`) is unchanged; `tests/test_review_record_rules.py` is unmodified and passes.
  The rest of the old rule 4 (quote text in backticks, a `>` line or fenced code) moved into the evidence bullet.
- **A2, repair turn** — `Outcome.refusal` holds `review record`'s whole output on a refusal (`file_review`);
  the one-line `said[-400:]` reason is unchanged (M22.16). `repair_prompt(refusal)` builds the repair section: the
  refusal in a fence longer than any backtick run in it, the notes rules, and "Send the whole corrected JSON
  object…". `review_delegate._repair` runs `_attempts` once more with `(full prompt + repair section,
  repair section)` (`-repair-full` / `-repair` prompt files) and the same retry budget, resuming the reported
  session when the harness can, else one fresh launch with the full prompt; snapshot right before it, the same
  write check after it (via the existing `file_review`), `model_check` from the repair attempt's own span
  (`_file`, the first-turn filing code moved into a helper), same `h.launch` (read-only restrictions). No repair for
  a parse/schema rerun, a review failure or a chore reviewer (no `file_review`, so no refusal).
- **A3, run record** — repair attempts carry `repair: true`; `run["refusal"]` keeps the first refusal text. When
  the repair turn does not file, the reason is `<first refusal reason>; after the repair turn, <its own reason>`,
  so a second refusal names both. `_start` with `--resume` returns the stored refusal only when the record's state
  is `incomplete`, the commit matches (existing check) and `refusal` is a `str`; then the repair prompt pair is
  sent and that run gets no further repair turn. Otherwise `RESUME_PROMPT`, unchanged.
- **A4, docs** — `docs/orchestration-reviewer-output.md` rerun-request bullet; `CHANGELOG.md` [Unreleased] Fixed.

## Note on one outside-zone test

`tests/test_review_strict_schema_removals.py::test_an_approve_without_the_removal_entry_is_a_rerun_request`
(unmodified) asserts the run's reason names the record refusal. With the repair turn, the Codex fake's resumed
turn gives no JSON, so the reason first named only that. I changed the package, not the test: a repair turn that
does not file keeps the first refusal's reason in front of its own (above). The test passes unmodified.

## Touch zones

Confirmed accurate; nothing outside them changed. Call sites outside the zones (role_prompt.py, review_cli.py,
review_rejected.py, review_run_status.py) need no change: `schema_lines()` and `Outcome` keep their signatures
(the new `Outcome.refusal` field has a default and comes last).

## Verification

- `pytest -n 4 tests/test_review_delegate_repair.py tests/test_review_record_rules.py tests/test_review_delegate.py tests/test_review_strict_schema_removals.py` pass.
- Full suite `pytest -n 4`: 5707 passed.
- Red-green: with the package changes removed, `tests/test_review_delegate_repair.py` fails 10 of 13 (the 3 "no
  repair turn" rows pass either way, as they should).
- `ruff check specy_road`, `specy-road file-limits` OK.
- Net lines: package about +88 (124 added, 36 removed), tests +134 (new file) +11 (helpers), docs +19.

## Added

- `review_record_rules.NOTES_RULES_LINES`: the operational notes rules (A1), shared by the prompt's last section and the repair prompt.
- `review_record_write.repair_prompt`: the repair section (refusal in a fence, notes rules, the request for the whole object) (A2).
- `Outcome.refusal` field: carries `review record`'s whole output from `file_review` to the delegate (A2).
- `review_delegate._reviewer_prompt`: `build_prompt` plus the error refusal, shared by a fresh start and a refusal-carrying resume (A3).
- `review_delegate._repair_prompts`: writes the `-repair-full` / `-repair` prompt pair for `_attempts` (A2, A3).
- `review_delegate._file`: the existing first-turn model check and filing, moved into a helper so the repair turn reuses it from its own attempt and snapshot (A2).
- `review_delegate._repair`: the one repair phase, marking attempts `repair: true` and storing `refusal` (A2, A3).
- Branch in `_start`: incomplete run + matching commit + `str` refusal → repair prompt pair (A3).
- Branches in `_delegate_locked`: one repair turn when the first filing was refused and the run has no `refusal` yet; a refusal on a refusal-carrying resume names both refusals (A3).
- Guard in `_repair`: a non-recorded repair outcome keeps the first refusal's reason in front (A3; keeps the unmodified strict-schema-removals test true).
- `tests/review_delegate_helpers.py` FAKE: records the prompt text each launch received (`prompts.json`) when the spec names it; `fake_prompts()` reads it; `set_steps` names it (A4: each row checks the prompt the harness received).
- `tests/test_review_delegate_repair.py`: the A4 table — refused then valid; refused twice; no repair (files / writes / no JSON, parametrized); repair writes a tracked file; repair reports another model; capacity retry in the repair keeps the refusal; non-resumable harness; `--resume` with a stored refusal (incomplete) vs complete / non-string / no refusal (parametrized).
