# Implementation summary: M11.75 — reviewer-probe-rules

## Round 3 (after the gpt-5.6-sol-medium block at c5944c15)

The block's `required_changes`: refuse an approve whose findings or notes plainly describe a defect even when they avoid the trigger vocabulary. Its example was a finding that read "Valid input raises ValueError, so the command exits 1 instead of filing the review." It also asked for a public-CLI regression using that wording, asserting that no review or history record is written and that the error names the offending finding. Commit c62f1cf9:

- **Findings are checked by structure, not wording.** This item was blocked twice on wording the list missed, and no word list catches every description of a defect. So on an approve, every `findings` entry without a `not a defect because` line is refused, whatever it says. The message names it `findings.<key>[i] says "<word>"` when a word matches, and `findings.<key>[i] is a finding` otherwise. The refusal message ends "on an approve every findings entry needs that line". The prompt's rule 4 and the docs tell reviewers to keep observations that are not defects in the notes. Of the 312 distinct approving records in the main checkout, only 3 are refused by this rule alone; every other approve with findings already hit the word list.
- **Notes keep the word list.** It now also matches refused valid input and a non-zero exit where success was due: "valid <x> raises|fails|errors|crashes|is rejected|is refused", "rejects|refuses a valid", "raises|fails|errors … on|for|with valid", and "exits 1|non-zero … instead of". "Raises ReviewTargetError on an unknown node", "exits 1 on an unknown node" and "no longer rejects a valid ledger" are still not matched.
- **My own tests changed:** two round-1 tests in this leaf's `tests/test_review_record_rules.py` asserted that a neutral finding ("Checked the lock order.") on an approve was *not* named. Under the new contract it is named (`is a finding`), so those assertions now expect that. No test from before this leaf was touched.
- **Red-green:** with c5944c15's `review_record_rules.py` swapped in temporarily (then restored, checked with `cmp`), the three new CLI tests failed: 3 failed. With this commit they pass.

## Round 2 (after the gpt-5.6-sol-medium block at 5f9cdcfc)

The block's `required_changes` asked for two things:
- refuse an approve when a finding or notes line describes a concrete failure, covering at minimum the "crashes … drops the review" wording;
- make sure "no workaround for this bug" does not negate the bug.

It also asked for public-CLI regression cases proving that nothing is filed and that the error names each offending finding or line. Commit d5fbd02d does all of this:

- **Concrete failures:** `_DEFECT` now also matches crashes, hangs, deadlocks, corruption, leaks, data loss, infinite loops, race conditions, unhandled/uncaught exceptions and tracebacks, and incorrect results. It also matches drop/lose/overwrite followed by something a user keeps (`_KEPT`: data, records, reviews, work, changes, commits, files, messages, events, entries, input, output, results, state, edits), "is/was/gets lost|dropped|corrupted|overwritten", "silently drops/ignores/accepts/…", and "returns the wrong"/"wrong result|value|path|…".
- **Bare verbs stay out:** a bare "fails", "drops" or "raises" is still not matched. In existing approves those words mostly describe intended behaviour ("drops a leaf that still has a placeholder", "raises ReviewTargetError on an unknown node", "the test fails without the fix").
- **Negation:** `_NEGATED` used to allow any three words between the negation and the defect word. Now only qualifiers from a list (`_QUALIFIER`: other, more, known, correctness, demonstrated, longer, …) may stand between them. So "no other correctness defect" and "no longer crashes" are still negated, and "no workaround for this bug" and "no test for this bug" are not. I added `not`, `…n't`, `cannot`, `rather than` and `instead of` as negations, so "does not crash", "doesn't drop data" and "rather than crashing the gate" are cleared.
- **Prompt and docs:** rule 4 in the reviewer prompt now names concrete failures, and `docs/orchestration-review.md` lists the vocabulary and the negation rule.
- **Red-green:** with 5f9cdcfc's `review_record_rules.py` swapped in temporarily (then restored from a copy), the three new CLI tests and the crash `defect_word` case failed: 4 failed, 2 passed. With this commit they pass.

## What changed

- **A1 (reviewer prompt rules):** `PROBE_RULES_LINES` in `specy_road/review_record_rules.py` holds four numbered rules. `role_prompt.reviewer_lines` appends them after `REMOVED_TEXT_LINES`, so every reviewer prompt gets them, including the ones `review delegate` builds through `build_prompt`. The rules say to (1) run the tests that import each changed module, not only the executor's selection or the READY's verifiers; (2) for each changed public function, try at least one input the diff's tests do not use and report it under `commands_rerun`; (3) fail an acceptance item whose observed behaviour differs from its text, even when the difference looks minor; (4) list every defect under `required_changes`, or explain on that same line why it is not one, starting `not a defect because`. Rule 4 also tells the reviewer that `review record` checks for this, and that quoted text in backticks or on a `>` line is not checked.
- **A2 (refusal):** `review record` refuses an approve with any findings entry (round 3), or a notes line that names a defect or describes a concrete failure (round 2), with no `not a defect because` line on it. An approve can't carry `required_changes`; `review_semantic_errors` already refuses that, so the only way past is the explanation line, or a block. The check runs in `check_record` (`approve_defect_problem` → `unexplained_defects` → `defect_word`).
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

I ran `unexplained_defects` over the distinct approving records in the main checkout's `sr/work/reviews/` (I wrote nothing there). In round 1 it would have refused 43 of 293 (~15%). In round 2, after adding the concrete-failure wording, it would refuse 73 of 301 (~24%). In round 3 it would refuse 76 of 312 (~24%); 3 of those come from the findings rule alone. I read every new round-2 hit. Most are real issues seen and excused ("`--why` is dropped without a message", "drops that record from `resolved`", "a removed worktree … blocks the coordinator"). A few describe intended behaviour or past rounds (for example, "the prior registered-span crash regression"); those reviewers would add a `not a defect because` line. I read a sample by hand. Each one names an issue and approves anyway: "Advisory: …", "Non-blocking nit: …", "Residual (not required) …", "Two traces that look like bugs do not fail an acceptance item", "latent prune bug". That matches the pattern the planning sheet describes. Records that say "No defect." or "None blocking." pass.

## Known limits

- Findings are covered whatever their wording (round 3). Notes are still checked against a word list, not parsed, so a defect described in the notes in other words (for example, "the second call reads the registry before the first writes it") still gets through. An unquoted acceptance text in the notes that says "defect" is refused until it is quoted in backticks or with `>`. The prompt and the docs both tell reviewers this.
- An approve that puts non-defect observations in `findings` ("Checked the lock order.") is now refused until each says `not a defect because …` or moves to the notes.
- Approve records already filed are not re-checked: the rule applies only in `review record`, not in `load_review`/`list_reviews`, so the gate still counts existing records.
- The `specy-road review record` instructions under `specy_road/templates/` do not mention `not a defect because`. The reviewer prompt and the refusal message both do, and adding it to the templates would mean widening the touch zones further.

## Verification

Round 3 (at c62f1cf9):

- `python -m pytest -q -n 4 tests/test_review_record_rules.py` → 36 passed
- `python -m pytest -q -n 4 <the same 46 files as round 2>` → 611 passed
- `specy-road file-limits` → OK; `ruff check` on the changed Python files → clean

Round 2 (at d5fbd02d):

- `python -m pytest -q -n 4 tests/test_review_record_rules.py` → 28 passed
- `python -m pytest -q -n 4 <46 files: every test importing review_cli / role_prompt / review_record_rules, plus test_review_gate.py and test_validate_acceptance_coverage.py>` → 603 passed
- `specy-road file-limits` → OK; `ruff check` on the changed Python files → clean

Round 1:

- `python -m pytest -q tests/test_review_record_rules.py` → 16 passed
- `python -m pytest -q -n auto <44 test files that import review_cli / role_prompt / review_record_rules>` → 569 passed
- `python -m pytest -q -n auto tests/test_review_gate.py tests/test_validate_acceptance_coverage.py` (they file records without importing those modules) → 22 passed
- `specy-road file-limits` → OK
- `ruff check` on the changed Python files → clean

## Added

- `specy_road/review_record_rules.py` — new module, because `review_cli.py` and `role_prompt.py` are at the file cap.
- `NOT_A_DEFECT` — the one phrase that the prompt asks for and the check accepts, defined once.
- `PROBE_RULES_LINES` — the four A1 rules in the reviewer prompt.
- `_DEFECT`, `_NEGATED`, `_CODE_SPAN` regexes — find the words that name a defect or describe a concrete failure, skip negated mentions, and ignore quoted code.
- `_KEPT` (round 2) — things a user keeps, so "drops the review" counts and "drops a leaf" does not.
- `_QUALIFIER` (round 2) — the only words allowed between a negation and a defect word, so "no workaround for this bug" is not read as negated.
- `defect_word` — decides for one line whether it names a defect, so findings entries and notes lines go through the same rule.
- `unexplained_defects` — walks the findings entries and the notes lines (skipping fenced code) and labels each hit with where it is, so the message can say which. From round 3, every findings entry without the explanation line counts (`is a finding` when no word matches).
- `approve_defect_problem` — the A2 refusal message; only for `verdict: approve`.
- `check_record` — `review_cli._check_record`, moved unchanged, plus the A2 guard as its last step.
- `tests/test_review_record_rules.py::test_reviewer_prompt_carries_the_four_probe_rules` — pins the four A1 rules in the rendered reviewer prompt, and checks they are absent from the executor prompt.
- `…::test_record_refuses_an_approve_whose_finding_names_a_defect` — A2 refusal from a findings entry; the message names which entry, and nothing is filed.
- `…::test_record_refuses_an_approve_whose_notes_name_a_defect` — A2 refusal from a notes line; the message names the line.
- `…::test_record_refuses_an_approve_whose_finding_describes_a_crash` (round 2) — the blocking reviewer's crash/drop wording, through the CLI; nothing is filed and the message names `findings.correctness[0]`.
- `…::test_record_refuses_an_approve_where_no_workaround_does_not_negate_the_bug` (round 2) — the "no workaround for this bug" wording, through the CLI; names the notes line.
- `…::test_record_names_every_offending_finding_and_line` (round 2) — several offenders across findings and notes: each is named, negated lines are not, and neither the record nor a history copy is written.
- `…::test_record_refuses_an_approve_whose_finding_says_valid_input_raises` (round 3) — the blocking reviewer's ValueError / exits-1 wording as a finding, through the CLI; no review or history record, and the message names `findings.correctness[0]`.
- `…::test_record_refuses_an_approve_with_any_finding_that_does_not_say_why_it_is_not_a_defect` (round 3) — a finding with no trigger word is still refused as `findings.boundary[0] is a finding`; no review or history record.
- `…::test_record_refuses_an_approve_whose_notes_say_valid_input_raises` (round 3) — the same wording on a notes line; names the line, and no review or history record.
- `…::test_record_files_an_approve_with_no_findings` — A2: a clean approve (with "No defect found; no bugs.") is filed.
- `…::test_record_files_an_approve_that_says_why_it_is_not_a_defect` — the explanation line lets an approve through.
- `…::test_record_files_a_block_that_lists_the_defect` — a block with the defect under required_changes is not affected.
- `…::test_defect_word` (23 cases; 9 added in round 2 for concrete failures, the tightened negation, and bare verbs that stay out; 5 in round 3 for refused valid input and non-zero exits, and the forms that stay out) — pins negation, headings, quotes, code spans and the explanation phrase.
- `…::test_fenced_code_in_the_notes_is_not_checked` — test output in fenced code is not read as a defect.
- Mocks: none.
