# Implementation summary: M11.75 — reviewer-probe-rules

## What changed

- **A1 (reviewer prompt rules):** `PROBE_RULES_LINES` in `specy_road/review_record_rules.py` holds four numbered rules. `role_prompt.reviewer_lines` appends them after `REMOVED_TEXT_LINES`, so every reviewer prompt gets them, including the ones `review delegate` builds through `build_prompt`. The rules say to (1) run the tests that import each changed module, not only the executor's selection or the READY's verifiers; (2) for each changed public function, try at least one input the diff's tests do not use and report it under `commands_rerun`; (3) fail an acceptance item whose observed behaviour differs from its text, even when the difference looks minor; (4) list every defect under `required_changes`, or explain on that same line why it is not one, starting `not a defect because`. Rule 4 also tells the reviewer that `review record` checks for this, and that quoted text in backticks or on a `>` line is not checked.
- **A2 (refusal):** `review record` refuses an approve whose findings or notes name a defect with no `not a defect because` line on it. An approve can't carry `required_changes`; `review_semantic_errors` already refuses that, so the only way past is the explanation line, or a block. The check runs in `check_record` (`approve_defect_problem` → `unexplained_defects` → `defect_word`).
  - **Which words count:** a line names a defect when it says advisory, non-blocking/not blocking, nit/nitpick, minor, cosmetic, residual, latent, optional fix, weak assertion, bug or defect.
  - **What is skipped:** mentions negated within three words ("no defect", "no other correctness defect", "nothing minor"); headings; `>` quotes; code spans; fenced code in the notes.
  - **The message:** it names each one, e.g. `findings.correctness[1] says "Advisory"` or `notes line 3 says "Non-blocking"`, then says to list it under required_changes and block, or say why it is not one. Nothing is written when it refuses.
- **Docs:** a new section, `## What a reviewer probes`, in `docs/orchestration-review.md`.

## Touch zones (final)

- `specy_road/bundled_scripts/role_prompt.py`
- `specy_road/bundled_scripts/review_cli.py`: added by the coordinator (commit 09a58a3a).
- `specy_road/review_record_rules.py`: **new module**, added by me with `specy-road edit-node M11.75 --add touch_zones=…` (commit f4ebdb12). `review_cli.py` (400) and `role_prompt.py` (399) were both at the 400-line cap. The new code went into this module, and `review_cli._check_record` moved there unchanged as `check_record`, with the new check as its last step. No docstring, comment or message was removed: `review_cli.py`'s module docstring gained a sentence about the refusal, and three imports it no longer uses were dropped from it (`HUMAN`, `load_review`, `milestone_open_problem`).
- `docs/orchestration-review.md`
- `tests/`

## Calibration against existing records

I ran `unexplained_defects` over the 293 distinct approving records in the main checkout's `sr/work/reviews/` (I wrote nothing there). It would have refused 43 of them (~15%). I read a sample by hand. Each one names an issue and approves anyway: "Advisory: …", "Non-blocking nit: …", "Residual (not required) …", "Two traces that look like bugs do not fail an acceptance item", "latent prune bug". That matches the pattern the planning sheet describes. Records that say "No defect." or "None blocking." pass.

## Known limits

- This is a word list, not a parser. A reviewer can still describe a defect without any of these words, and an unquoted acceptance text that says "defect" is refused until it is quoted in backticks or with `>`. The prompt and the docs both tell reviewers this.
- Approve records already filed are not re-checked: the rule applies only in `review record`, not in `load_review`/`list_reviews`, so the gate still counts existing records.
- The `specy-road review record` instructions under `specy_road/templates/` do not mention `not a defect because`. The reviewer prompt and the refusal message both do, and adding it to the templates would mean widening the touch zones further.

## Verification

- `python -m pytest -q tests/test_review_record_rules.py` → 16 passed
- `python -m pytest -q -n auto <44 test files that import review_cli / role_prompt / review_record_rules>` → 569 passed
- `python -m pytest -q -n auto tests/test_review_gate.py tests/test_validate_acceptance_coverage.py` (they file records without importing those modules) → 22 passed
- `specy-road file-limits` → OK
- `ruff check` on the changed Python files → clean

## Added

- `specy_road/review_record_rules.py` — new module, because `review_cli.py` and `role_prompt.py` are at the file cap.
- `NOT_A_DEFECT` — the one phrase that the prompt asks for and the check accepts, defined once.
- `PROBE_RULES_LINES` — the four A1 rules in the reviewer prompt.
- `_DEFECT`, `_NEGATED`, `_CODE_SPAN` regexes — find the words that name a defect, skip negated mentions, and ignore quoted code.
- `defect_word` — decides for one line whether it names a defect, so findings entries and notes lines go through the same rule.
- `unexplained_defects` — walks the findings entries and the notes lines (skipping fenced code) and labels each hit with where it is, so the message can say which.
- `approve_defect_problem` — the A2 refusal message; only for `verdict: approve`.
- `check_record` — `review_cli._check_record`, moved unchanged, plus the A2 guard as its last step.
- `tests/test_review_record_rules.py::test_reviewer_prompt_carries_the_four_probe_rules` — pins the four A1 rules in the rendered reviewer prompt, and checks they are absent from the executor prompt.
- `…::test_record_refuses_an_approve_whose_finding_names_a_defect` — A2 refusal from a findings entry; the message names which entry, and nothing is filed.
- `…::test_record_refuses_an_approve_whose_notes_name_a_defect` — A2 refusal from a notes line; the message names the line.
- `…::test_record_files_an_approve_with_no_findings` — A2: a clean approve (with "No defect found; no bugs.") is filed.
- `…::test_record_files_an_approve_that_says_why_it_is_not_a_defect` — the explanation line lets an approve through.
- `…::test_record_files_a_block_that_lists_the_defect` — a block with the defect under required_changes is not affected.
- `…::test_defect_word` (9 cases) — pins negation, headings, quotes, code spans and the explanation phrase.
- `…::test_fenced_code_in_the_notes_is_not_checked` — test output in fenced code is not read as a defect.
- Mocks: none.
