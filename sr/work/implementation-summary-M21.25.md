# M21.25 — review delegate reads a reviewer's answer when narration precedes its final JSON object

## What changed

- `specy_road/review_answer.py`: `_answer` reads a text terminal message (`envelope=False`: Cursor's `result`
  text, a Claude `result` without `structured_output`, Codex's `agent_message` or `-o` file) through the new
  `_last_object`. It scans left to right for complete JSON values starting at `{` or `[` with
  `JSONDecoder.raw_decode`, skipping each value's interior, so an object nested in another value is never the
  answer. A `{`/`[` that starts no value is prose. A decode that fails because the text ends (error at end of
  text, or an unterminated string) is refused as "ends inside an unfinished JSON object". `RecursionError` is
  refused as "nests JSON too deeply to read" (the guard `loads_untrusted` uses). The answer is the last
  top-level object, and only whitespace may follow it. If none: "holds no JSON object". If text follows:
  "does not end with a JSON object". The object still goes through `drop_nulls` and `output_schema`, so a
  schema-invalid last object gives the existing schema reason, and an earlier valid object is never used.
  The envelope path (generic/agy) is unchanged. The module docstring is updated.
- `tests/test_review_answer.py`: A4 rows are retargeted. claude-code "prose before the object" files,
  "two objects" gives the schema reason, "fenced object" gives "does not end with", and the non-JSON rows
  (claude, cursor, codex, plus codex "empty -o file" and cursor "structured_output is not Cursor's") give
  "holds no JSON object". Envelope rows are unchanged. A new parametrized test covers the four text paths
  times the A3 shapes.
- `tests/test_review_record_write.py`, `tests/test_review_record_write_closure.py`,
  `tests/test_review_delegate.py` (added to the touch zones mid-leaf): end-to-end expectations are
  retargeted to the new reasons. "Verdict:\nVERDICT" (prose before the object) now files, as A1 requires.
  No assertion was loosened: each refusal still asserts its own reason.
- `docs/orchestration-reviewer-output.md`: the bullets calling prose around JSON and two objects a rerun
  are replaced with the text-message rule (text before the final object is ignored, nothing may follow it).
- `CHANGELOG.md`: an [Unreleased] Fixed entry.

The reviewer prompt's "exactly one JSON object" instruction and `review record`'s input rule are unchanged.

## Final touch zones

specy_road/review_answer.py, tests/test_review_answer.py, docs/orchestration-reviewer-output.md, CHANGELOG.md,
tests/test_review_record_write.py, tests/test_review_record_write_closure.py, tests/test_review_delegate.py.

## Verification

- `pytest -q -n 4 -p no:cacheprovider`: 5555 passed.
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.

## Added

- `review_answer._last_object`: the text-message answer rule (A1/A2).
- `review_answer._OPENER` regex: finds the next `{`/`[` in one linear search (two `str.find`s per step would
  rescan to the end for every opener).
- Branch in `_last_object`, `except RecursionError`: the excessive-nesting refusal (A2).
- Branch in `_last_object`, error at end of text or unterminated string: the unfinished-object refusal (A1/A2).
- Branch in `_answer`, `isinstance(body, Rerun)`: passes `_last_object`'s refusal through.
- `import re` in review_answer.py: for `_OPENER`.
- Test `test_a_text_message_answers_with_its_final_object` (+ `TEXT_PATHS`, `TEXT_SHAPES`, `NARRATION`,
  `DEEP_TEXT`): A3's parametrization over the four text paths.
- Test constants `NO_OBJECT`, `NOT_LAST`, `UNFINISHED`, `DEEP` (test_review_answer.py) and `UNFINISHED`,
  `SCHEMA` (test_review_record_write.py): the new reasons.
- Branch `why is None` in `test_malformed_output_is_a_rerun_request_never_a_verdict`: the prose-before row now
  files, so it asserts a recorded review.
- Mocks: none.
