# Implementation summary: M21.12

## What changed

`_second_observation` in `specy_road/review_record_rules.py` returns `None` unless some joined part names a defect, so neutral parts are one observation whatever joins them. The docstring, `PROBE_RULES_LINES` and the matching paragraph of `docs/orchestration-review.md` state this one rule. `CHANGELOG.md` [Unreleased] Fixed records it.

## Beyond the sheet's one condition

The sheet's Approach names one condition, but that alone fails A2. Before this leaf, defect/neutral joined by a comma or "and" ("The lock crashes and the cache is cold, not a defect because ...") was accepted, because a neutral part after those joiners never counted. A2 requires that shape refused for all nine joiners, so the third branch of `_second_observation` no longer checks the joiner.

This makes one shape stricter than before: after a comma or "and", a neutral part of three words or more now counts when another part names a defect. For example, "Minor wording, the docstring reads fine today, not a defect because ..." is now refused. Short list items (under three words) and parts opening with a carrying-on word still do not count: "Valid input crashes on the lexer, the parser and the loader" and "The lock crashes, so the cache is cold here" stay accepted under one explanation. The sheet records this under Decisions and notes.

`why`'s fallback to `found[1][0]` was removed: with the new guard, `found` always holds a part that names a defect.

## Touch zones

Final list is unchanged from the brief. `role_prompt.py` and `review_rejected.py` import this module but need no change: `role_prompt.py` only renders `PROBE_RULES_LINES`, and no test pins the rewritten sentence.

## Re-baselined rows

Two rows of `_REAL` in `tests/test_review_friction_m15_17.py` (M14.1 cursor-grok-4.6-high and M14.1 grok-4.7-low, both `findings.boundary[0]`) now expect acceptance. They are listed in the sheet, and the comments above them and the table are updated.

## Evidence

- With the base `review_record_rules.py` under the new tests, 13 tests failed (neutral joins, comma/"and" defect-then-neutral rows, the M21.8 row, the three-part row and the two re-baselined rows). With the fix, all pass.
- `tests/test_review_record_rules.py` is 397 lines (cap 400).

## Added

- `_second_observation` guard (`if not any(word ...)`): the rule itself, neutral joins return `None` (A1).
- `JOIN_ROWS` in `tests/test_review_record_rules.py`: 27 `test_clause_problem` rows, nine joiners by three part shapes (A2); the `plus` neutral/defect row is 'The cache is cold plus the lock crashes'.
- `test_clause_problem` row, M21.8 line: the real refused line, now accepted (A2).
- `test_clause_problem` row, three neutral parts: A1 says two or more parts.
- Mocks: none.
- New test functions: none.
