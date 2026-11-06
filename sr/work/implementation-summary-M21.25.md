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

## Fix round 1 (gpt-6.1-sol-low block at 31fdcc16)

- Class 1, "a decode that failed only because the text ends": the old test (error at end of text, or an
  unterminated string) missed cuts inside a token, because the decoder reports the error at the token's start
  (`{"x": tru`, `nul`, `-`, `1.`, `1e+`, `"\u12`). It is replaced by one bounded rule, `_CUT_TOKEN`: the
  decode failed only because the text ends when the text from the error position is a proper prefix of one JSON
  token (a literal, a number or its fraction/exponent, an unterminated string, a `\u` escape) or nothing. Limit,
  documented in the docstring: `{1` at the very end is refused as unfinished, although no completion is valid
  JSON (it is still a refusal).
- Class 2, "a value's interior scanned as top-level text": strings were not skipped. `"` is now a value opener
  like `{` and `[`, so a complete JSON string's interior is skipped. A `"` that starts no string is prose and
  never triggers the unfinished refusal. Limit: a prose quote that pairs with a quote inside the answer on the
  same line (`He said "x {...}`) swallows the answer's start. That gives a refusal ("holds no JSON object"),
  never a wrong answer.
- No branch was added: the unfinished condition was replaced by one condition, and the opener set grew by one
  character.

## Fix round 2 (gpt-6.1-sol-low block at 548e419b)

- Class: "judging a cut from the error tail without the decoder's context". `_CUT_TOKEN` looked only at the
  text from the error position, so `Use {1` (tail `1`) and `{"x": 1.e` (tail `.e`) counted as cuts, although no
  JSON continues them. Design change: `_CUT_TOKEN` is removed and the decoder itself judges a cut. `_FILLS` lists
  the completions of one cut-off token: nothing, the rest of each literal prefix, a digit for a number, a
  closing quote, and the rest of an escape. `_cut_short` decodes the text plus each fill from the opener. The
  value was cut short when one of them makes the decoder run out of text instead of failing inside it. Every
  prefix of a JSON token has a fill in the list, and no fill closes a container. So this is exact for JSON's
  grammar: a valid prefix is refused as unfinished, and anything else is prose. The round 1 limit (`{1`) is gone.
- Remaining edge: Python's decoder accepts `NaN`/`Infinity`, so `{"x": NaN` at the end is refused as unfinished
  rather than read as prose. It is still a refusal.

## Final touch zones

specy_road/review_answer.py, tests/test_review_answer.py, docs/orchestration-reviewer-output.md, CHANGELOG.md,
tests/test_review_record_write.py, tests/test_review_record_write_closure.py, tests/test_review_delegate.py.

## Verification

- `pytest -q -n 4 -p no:cacheprovider`: 5555 passed.
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.

## Added

- `review_answer._last_object`: the text-message answer rule (A1/A2).
- `review_answer._OPENER` regex: finds the next value opener (`{`, `[`, `"`) in one linear search (fix round 1
  added `"` so string interiors are skipped).
- `review_answer._FILLS` and `_cut_short` (fix round 2, replacing round 1's `_CUT_TOKEN` regex): the decoder judges
  whether a value was cut short by the end of the text.
- Branch in `_last_object`, `except RecursionError`: the excessive-nesting refusal (A2).
- Branch in `_last_object`, a non-string opener that `_cut_short` reports: the unfinished-object
  refusal (A1/A2).
- Branch in `_answer`, `isinstance(body, Rerun)`: passes `_last_object`'s refusal through.
- `import re` in review_answer.py: for `_OPENER`.
- Test `test_a_text_message_answers_with_its_final_object` (+ `TEXT_PATHS`, `TEXT_SHAPES`, `NARRATION`,
  `DEEP_TEXT`): A3's parametrization over the four text paths.
- Test constants `NO_OBJECT`, `NOT_LAST`, `UNFINISHED`, `DEEP` (test_review_answer.py) and `UNFINISHED`,
  `SCHEMA` (test_review_record_write.py): the new reasons.
- Branch `why is None` in `test_malformed_output_is_a_rerun_request_never_a_verdict`: the prose-before row now
  files, so it asserts a recorded review.
- `TEXT_SHAPES` rows (fix round 2): `Use {1` holds no object, and four prefixes no JSON continues after a valid
  answer do not end with an object.
- `TEXT_SHAPES` rows (fix round 1): a cut inside each token kind, alone and after a valid object; a bad
  `\u` escape is not a cut; `json.dumps("{}")` holds no object; quoted braces in prose, then the object, files.
- Mocks: none.

## Probes

- Reviewer's `{"x": tru`, `{"x": nul` and `{"x": "\u12` (Cursor result text): unfinished-object reason.
- Reviewer's `json.dumps("{}")`: "holds no JSON object".
- Valid object, then `{"x": tru`: unfinished-object reason (was "does not end with").
- `[1, tru`, and a valid object followed by a lone `[`: unfinished (arrays share the rule).
- Truncated `-`, `1.`, `1e+`, `"ab`, `"\`, `fals`, alone and after a valid object (all four text paths, in the
  table): unfinished.
- `{"x": "\uZZ` after a valid object: not a cut, "does not end with a JSON object".
- A JSON string holding the whole answer (`json.dumps(VT)`): "holds no JSON object" (interior skipped).
- Prose with an unclosed quote on its own line, then the answer: files (a raw newline ends no JSON string).
- Prose quote on the same line as the answer: refused, "holds no JSON object" (documented limit, never a wrong
  answer).
- Round 2, `Use {1`: holds no JSON object (was unfinished).
- Round 2, a valid answer, then `Use {1`, `{"x": 1.e`, `{"x": tru ` (space after the cut) or `[1 2`: does not
  end with a JSON object (table rows on all four text paths).
- Round 2, impossible prefixes `{"x": 01`, `{"x": "\uZZ`, `{"x": "a\q`, `{"x", `, `[,`, `{"a" : }`: holds no
  JSON object.
- Round 2, genuine cuts kept: `{"x": t`/`tru`/`nu`/`fals`/`-`/`1.`/`1e+`, `{"x": "a\`, `{"x": "\u1`, `{"x"`,
  `{"x":`, `[1,`, `{"x": [tru`, `{"a":{"b":"c"`, a lone `{` after the answer, the answer cut inside a long
  string: all "ends inside an unfinished JSON object".
- Round 2, the rc4 narration shape and `see {below}` prose before the answer: the answer files.
- Round 2, cost: `_cut_short` only runs for a failed `{`/`[` decode. Its 17 filled texts are built once per
  message, so a prose brace costs 17 decodes that fail at the same early position, with no per-opener copy.
- Round 2, other places the class could reach: none. `_last_object` is the only scanner, and the envelope path
  and per-line events still use `loads_untrusted` whole-text parsing.
- Answer cut inside one of its strings: unfinished. Answer plus trailing whitespace: files.
- Other places this class can reach: the generic/envelope path (`_object` -> `loads_untrusted`, whole-text
  parse, no scanning), still "is not one complete JSON object" for prose then an object; per-line event
  parsing in `_final_answer` uses `_object`, unaffected. `_last_object` is the only scanner.
- Complexity: `_last_object` keeps its branch count (one condition replaced); ruff (C901) is clean.
