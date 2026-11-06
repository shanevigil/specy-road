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
- **A3, run record** — repair attempts carry `repair: true` (one rule in `_attempts`: an attempt launched while the run holds a `refusal` is a repair attempt, so the in-run repair phase, a stored-refusal `--resume` and every capacity retry of either are marked as they are appended); `run["refusal"]` keeps the first refusal text. When
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

## Fix round 1 (review by gpt-6.1-sol-low at 5c351462)

Finding: a stored-refusal `--resume` sends the repair prompt but its attempts lacked `repair: true` (A3).
Class: an attempt launched with the repair prompt pair but not marked, because the marking was done after the
loop, in `_repair` only, so any other launch path with the repair pair missed it. Design change: the marking moved
into `_attempts` itself and is derived from the same fact that selects the repair pair (`refusal` held by the run),
so no caller can launch a repair attempt unmarked; the post-loop marking in `_repair` is removed (no added
branch left behind). Merged `origin/WIP/improvements-0-3-1` first (clean).

## Fix round 2 (review by gpt-6.1-sol-low at 5b6336ff)

Finding: three rows (second refusal, repair writes a tracked file, repair reports another model) never checked the
prompt the fake harness received (A4). Class: a row that checks the run record's attempts but not the prompts
sent, so the two can disagree unnoticed. Design change: the test file's one way to read the attempts' `repair`
flags is `_turns(spec, run, skip)`, which first asserts that each launch's received prompt carries the refusal
exactly when its attempt is a repair attempt; the old `_repairs` helper and the per-test prompt-count checks are
gone, so every row checks the prompts by construction. Merged `origin/WIP/improvements-0-3-1` first (clean).
No package change this round.

## Probes

- Fix round 2: every one of the 8 test functions in tests/test_review_delegate_repair.py reads the flags through `_turns` (no `_repairs` left) — yes.
- Fix round 2: the three named rows now assert the prompt per launch: second refusal `[False, True]`, repair write `[False, True]`, repair model mismatch `[False, True]` — pass.
- Fix round 2: the no-repair rows (files / writes / no JSON) assert exactly one launch whose prompt carries no refusal — pass.
- Fix round 2: the `--resume` rows check the resume's two prompts (skipping the earlier run's) and the earlier run's own two — pass.
- Fix round 2: with `repair_prompt` temporarily sending "(omitted)" in place of the refusal, 10 of 13 rows fail, the 3 named among them; only the no-repair rows pass, as they should. Reverted.

- Every `_attempts` caller (two: `_delegate_locked`, `_repair`): the repair pair is passed exactly when `run["refusal"]` is set before the call — consistent, both marked.
- Stored-refusal `--resume` with a capacity error then an answer: attempts `[repair, repair]`, both prompts carry the refusal (extended `test_resume_sends_a_stored_refusal_only_on_an_incomplete_run`).
- Same with a complete run, a non-string or a missing refusal: attempts unmarked, both prompts are `RESUME_PROMPT` (same test, other rows).
- In-run repair with a capacity retry: `[False, True, True]` (existing test, unchanged, passes).
- First turn of a fresh run: never marked (`"refusal"` absent until `_repair` sets it) — `test_no_repair_turn_unless_review_record_refused` rows pass.
- Chore reviewer: never gets a `refusal` (no `file_review`), so never marked — `test_review_delegate.py` chore test passes.
- Red-green: with only the package change reverted, the `incomplete-refused` resume row fails; the other 12 pass.
- Every test file importing the zoned modules or the helper: 731 passed; `ruff check specy_road tests scripts` and `specy-road file-limits` OK.

## Added

- `review_record_rules.NOTES_RULES_LINES`: the operational notes rules (A1), shared by the prompt's last section and the repair prompt.
- `review_record_write.repair_prompt`: the repair section (refusal in a fence, notes rules, the request for the whole object) (A2).
- `Outcome.refusal` field: carries `review record`'s whole output from `file_review` to the delegate (A2).
- `review_delegate._reviewer_prompt`: `build_prompt` plus the error refusal, shared by a fresh start and a refusal-carrying resume (A3).
- `review_delegate._repair_prompts`: writes the `-repair-full` / `-repair` prompt pair for `_attempts` (A2, A3).
- `review_delegate._file`: the existing first-turn model check and filing, moved into a helper so the repair turn reuses it from its own attempt and snapshot (A2).
- `review_delegate._repair`: the one repair phase, storing `refusal` before its attempts (A2, A3).
- `_attempts`: an attempt launched while the run holds a `refusal` gets `repair: true` (A3; fix round 1, the one marking rule).
- Branch in `_start`: incomplete run + matching commit + `str` refusal → repair prompt pair (A3).
- Branches in `_delegate_locked`: one repair turn when the first filing was refused and the run has no `refusal` yet; a refusal on a refusal-carrying resume names both refusals (A3).
- Guard in `_repair`: a non-recorded repair outcome keeps the first refusal's reason in front (A3; keeps the unmodified strict-schema-removals test true).
- `tests/review_delegate_helpers.py` FAKE: records the prompt text each launch received (`prompts.json`) when the spec names it; `fake_prompts()` reads it; `set_steps` names it (A4: each row checks the prompt the harness received).
- `tests/test_review_delegate_repair.py` `_turns`: the attempts' `repair` flags, read only after checking each launch's received prompt against them (fix round 2: every row checks the prompt).
- `tests/test_review_delegate_repair.py`: the A4 table — refused then valid; refused twice; no repair (files / writes / no JSON, parametrized); repair writes a tracked file; repair reports another model; capacity retry in the repair keeps the refusal; non-resumable harness; `--resume` with a stored refusal (incomplete) vs complete / non-string / no refusal (parametrized; each `--resume` row also hits a capacity retry and checks both prompts and the attempts' `repair` flags).
