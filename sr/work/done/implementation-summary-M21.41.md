# Implementation summary: M21.41

## What changed

- `specy_road/review_record_rules.py`: the clause line of `NOTES_RULES_LINES` now names `'. '`, `'! '`, `'? '`, `'; '` and all eight conjunctions. Wording only; `clause_problem`, `_second_observation` and `note_problem` are unchanged, and the comma-list line stays.
- `specy_road/rework_rca.py`: the module docstring names `review_deferral.rca_deferral`.
- `tests/test_review_record_rules.py`: public-name test of the prompt's clause line, plus `CLAUSE_BREAK_ROWS` fed into the existing `test_note_problem` and `test_clause_problem` parametrizations.
- `tests/test_brainstorm_verify.py`: the two M21.36 tests patch `socket.getaddrinfo` and still call `check_source` with the fetcher argument.
- `CHANGELOG.md`: one bullet at the top of the first `[Unreleased]` `### Fixed`, where recent entries go.

## Touch zones

Confirmed as listed; nothing outside them changed. The call sites of `review_record_rules.py` (`role_prompt.py`, `review_record_write.py`, `review_rejected.py`) read `NOTES_RULES_LINES` as text and need no change. The `rework_rca.py` edit is docstring only.

## Notes for reviewers

- Each separator refused row is `Ship it<sep>The suite passed, not a defect because ...`, so the `'! '` row is the one A2 asks for. It uses a concrete reason, because a literal `...` after the marker is not a reason and the row would be refused for the wrong cause.
- Each conjunction refused row needs a defect word: `_second_observation` only splits on conjunctions when a part names a defect, so two plain clauses joined by a conjunction are accepted whatever the join. That is the existing rule, unchanged here.
- In each conjunction accepted row, the first marker's reason text runs to the end of the line, since a conjunction does not end a clause. The second clause and its marker sit inside that reason, and the row passes because the reason names no defect (`defect` in the second marker is negated by `not a`). A second clause that named a defect there would be refused as `says "<word>" in its reason`. So the row shows the line is accepted, not that the second reason was checked separately.
- `_is_off_host` stays in `constraints/test-private-imports-baseline.txt`: `tests/test_brainstorm_verify.py` still patches it at three other sites outside this leaf's two tests. The baseline did not grow (0 new).
- Red check: with the old `review_record_rules.py`, `test_notes_rules_name_every_clause_break` fails (exit 1). The behaviour rows pass before and after, because the checker did not change.

## Added

- `SEPARATORS`, `CONJUNCTIONS` (tests/test_review_record_rules.py): the clause breaks A1 and A2 list, shared by the prompt test and the rows.
- `SUITE_REASONED`, `COLD_REASONED` (tests/test_review_record_rules.py): the reasoned clause each row joins to, kept in one place.
- `CLAUSE_BREAK_ROWS` (tests/test_review_record_rules.py): A2's refused and accepted rows per separator and per conjunction, run through both `note_problem` and `clause_problem` by extending the existing parametrizations.
- `test_notes_rules_name_every_clause_break` (tests/test_review_record_rules.py): A2's public prompt check, plus A1's kept comma-list instruction.
- `_example_com_is_public` (tests/test_brainstorm_verify.py): the `socket.getaddrinfo` stub A3 asks for, shared by the two tests.
- Helpers, branches or guards in package code: none.
- Mocks: none beyond the `getaddrinfo` stub above.
