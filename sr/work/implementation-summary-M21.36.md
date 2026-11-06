# M21.36 implementation summary

`brainstorm verify` now normalizes fetched page text and the quote alike, so a quote survives citation markers and typographic variants. Repo sources are unchanged.

## What changed

- `specy_road/bundled_scripts/brainstorm_verify.py`: `_norm` unescapes after stripping tags, removes `_CITATION` markers, applies the `_FOLD` table, then collapses whitespace and runs the punctuation-space rule as before. `quote_in_file` is untouched.
- `tests/test_brainstorm_verify.py`: table tests through `check_source`, both directions; not-found rows; repo-source pin.
- `docs/brainstorming.md`: verify paragraph (A4). `CHANGELOG.md`: [Unreleased] Fixed.

## Touch zones

Confirmed accurate: the four listed files, nothing else. `_norm` is called only by `check_source`; the importers outside the zones use other names and need no change.

## Notes for reviewers

- The test rule forbids patching a `_`-prefixed name, but A2 explicitly requires stubbing `_is_off_host` as `test_check_source_states` does. I followed A2. No test touches `_norm`, `_CITATION` or `_FOLD` directly.
- The U+00A0, U+202F and U+2009 rows and `26&nbsp;%` passed before the fix, because `\s` already matched those characters. They pin the behaviour; they are not red-green evidence. The fold entries are there because A1 lists them.
- Order follows A1: markers are removed before the fold, so `[note<U+00A0>1]` with a non-breaking space is not treated as a marker. Not covered by A1; left as specified.
- The `[a-z]` alternative A1 requires also removes `[i]` and `[j]` on both sides, so a quote `x[i]` matches a page `x[j]`. This is a consequence of the specified regex; left as specified.

## Verification

- Before the fix: 34 failed, 13 passed in `tests/test_brainstorm_verify.py`.
- After the fix: `pytest -n 4` 5734 passed; `specy-road file-limits` OK (existing warnings only, none on zoned files).

## Added

- `_CITATION` (brainstorm_verify.py): regex for the bracketed markers A1 names.
- `_FOLD` (brainstorm_verify.py): translate table for the A1 maps and deletions.
- `_FOLDED`, `_SAME_WORDS` (test file): row data, one row per mapped or deleted code point plus the plan's table rows.
- `test_check_source_matches_page_text_variants_both_ways`: A2, every row in both directions; also `[A]` and `[Citation Needed]` rows for case-insensitivity, and `restudying [43] while` for a marker after a space.
- `test_check_source_still_needs_the_same_words`: A3, different words and a marker-only quote stay not-found.
- `test_repo_quotes_do_not_get_the_page_folds`: A3, `quote_in_file` gets no folds or marker removal.
- Helpers, guards, mocks: none beyond the `_is_off_host` stub A2 requires and the inline fake fetchers.
