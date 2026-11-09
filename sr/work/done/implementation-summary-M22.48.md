# Implementation summary: M22.48

## Change

- `specy_road/review_eligible.py`
  - `Identity` records each roster entry's family; `Identity.ambiguous` now records today's problem text only when the
    candidate entries span more than one family.
  - `writers` no longer calls `ambiguous` for a READY author: an ambiguous author is still keyed under every entry
    it may be (excluded under all), but no longer closes the gate (A1, row 5).
  - `reviews_to_judge` calls `ambiguous` only for a record that does not intersect the writers. A record that may be
    a writer goes to `ineligible` as before, with no closing problem. A judged record of one family counts; its family
    still comes from `family_of(config, model)` (the roster id), which is that one family whenever the candidates
    share it, so no entry is picked (planning sheet "If this fails" not triggered).
  - Module and `Identity` docstrings updated.
- `specy_road/review_gate.py`: docstring bullet and one comment updated to the narrowed rule; no code change.
- `tests/test_review_gate_ready_author.py`: the M22.19 table `test_authorship_that_cannot_be_decided_closes_the_gate`
  asserted that ambiguity alone closes the gate, which A1 reverses. It is replaced by
  `test_a_shared_name_closes_the_gate_only_when_it_could_be_the_writer`, which keeps all five M22.19 roster cases
  (SHARED, COLLIDE x3, refused PROFILED) with their new expected outcomes, and adds the A2 rows. Each row also checks
  the `handoff status` lines (`reviewer_eligibility` / `eligibility_lines`) give every excluded entry its reason.
  The other M22.19 test (case folding and aliases) is unchanged and passes.
- `CHANGELOG.md`: [Unreleased] / Fixed entry.

## Touch zones

Final list: `specy_road/review_eligible.py`, `specy_road/review_gate.py`, `tests/test_review_gate_ready_author.py`,
`CHANGELOG.md`. `docs/roadmap-history.md` was listed but describes `specy-road history`, not the review gate; it
is unchanged. No call site outside the zones needed a change (signatures unchanged).

## Verification

- `python -m pytest -q tests/test_review_gate_ready_author.py`: 23 passed.
- Red without the fix: 7 of the 9 new rows fail on the old `review_eligible.py` (rows 4 and refused-profile pass both ways).
- Full suite with `-n 4`: 6847 passed, 8 skipped (run in two halves).
- `specy-road file-limits`: OK.

## Added

- `Identity.family` (dict roster id -> family): needed to tell a one-family shared name from a cross-family one.
- Branch in `Identity.ambiguous` (`split`): closes only when candidate families differ (A1).
- Test rosters `SOL_ALIAS`, `CROSS`: A2 rows (1)-(3) and (4).
- Test `test_a_shared_name_closes_the_gate_only_when_it_could_be_the_writer` (replaces the M22.19 closing table): A2 rows (1)-(5), the kept M22.19 rows, and the handoff-status reason per excluded entry.
- Mocks: none.
