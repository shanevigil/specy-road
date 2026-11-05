# Implementation summary: M15.37

## What changed

- `specy_road/review_record_rules.py` `_second_observation`: a part joined by `,` or ` and ` counts as a
  separate observation only when `_named_defect` finds a defect word in it. When such a part exists, the
  first part counts from two words, so "X fails and Y crashes" and "X fails, Y crashes" are still refused.
  Parts joined by `;`, a sentence end or the other `_PARTS` conjunctions keep the old rule (a defect
  word, or three words or more not opening with a `_CONTINUES` word). `_parts`, `_DEFECT`, `_CLAUSE_END`
  and the reason check are unchanged.
- `PROBE_RULES_LINES` rule 4: a comma or `and` joins a second observation only when the part after it
  names a defect, so a list is one observation; other conjunctions such as `but` and `while` still may not.
- Tests (planned changes per A3, planner 2026-11-05):
  - `tests/test_review_record_rules.py`: added the four A2 rows to `test_note_problem` and flipped the
    'cache miss is expected and the cache key ignores the branch name' row of `test_clause_problem` to None.
  - `tests/test_review_friction_m15_17.py`: `test_the_reported_shape_is_refused_with_the_word_and_both_parts`
    and `test_refusal_quotes_a_two_clause_line_and_the_rule` now use examples whose part after 'and' names
    a defect ("crashes", "leaks"), so they still exercise the refusal path. The M12.5 row of `_REAL` now
    expects no refusal.

## Touch zones (final)

`specy_road/review_record_rules.py`, `tests/test_review_record_rules.py`, `tests/test_review_friction_m15_17.py`.
Call sites `review_cli.py` and `role_prompt.py` need no change.

## Not done (out of scope)

- `docs/orchestration-review.md:71` still describes the old split (comma and 'and' parts count from
  three words). It is outside the zones and should be updated in a follow-up.
- `sr/tools/review-addendum.md` workaround left as is (A4 puts it out of scope).

## Verification

- `python -m pytest -q -n 4 tests/test_review_record_rules.py tests/test_review_friction_m15_17.py`: 124 passed
- `ruff check` on the three files: clean
- `specy-road file-limits`: OK

## Added

- `_second_observation`: `listed` flag (a comma/'and' part names a defect), so the first part counts from
  two words only then.
- `_second_observation`: branch that skips non-defect parts joined by ',' or 'and'. This is the core A1 rule.
- `test_note_problem`: four rows (the two A2 lines that are now accepted, plus the 'and' and ',' refusals).
- `test_a_real_refusal_names_its_trigger_and_quotes_the_line`: a `want is None` guard, so the flipped
  M12.5 row can assert that no refusal is made.
- Mocks: none. New test functions: none.
