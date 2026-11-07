# Implementation summary: M22.40 — Cursor display names match the model they name

## Touch zones (confirmed)

Final touch zones: `specy_road/model_names.py`, `tests/test_model_names.py`, `CHANGELOG.md`.

`tests/test_model_names.py` was not in the tree; A2 names it, so it is new. Call sites of `model_names` stay unchanged: `review_model_check.py`, `worker_models.py`, and `worker_adapter_parsers.py` already compare through `same_model` (parsers only call `roster_match`). `check` still returns `unreported` before that comparison when the harness reports no model. `normalise` is unchanged, so `tests/test_cursor_display_name_cost.py` still pins separator folding. No path outside the zones needed an edit.

## Behaviour

`same_model` drops a context-size token (`300K`, `1M`) only when the name also has an effort word, so `Claude Opus 5.5 300K High` and `GPT-5.6 Sol 1M High` match `claude-opus-5-5-high` and `gpt-5.6-sol-high`. `Extra High` is also compared as `xhigh`, and the `extra-high` spelling is kept. A different model or effort does not match. A context size with no effort word is kept, so the medium display name `GPT-5.6 Sol 1M` does not collapse onto the profile's bare model name and match `gpt-5.6-sol-high`.

## Added

### Helpers

- `_without_context_size` — drops a `300k`/`1m` token from a normalised name when an effort word is present, so the effort lines up with the catalog suffix.
- `_EFFORT_WORDS` — the effort words (`high`, `xhigh`, `medium`, …) that allow that drop.
- `_CONTEXT_SIZE` — the token shape of a context size (`300k`, `1m`).

### Branches or guards

- Effort-word guard in `_without_context_size` — a name with no effort word keeps its context-size token, so a medium display name that omits the word does not match a different effort.
- `extra-high` also recorded as `xhigh` in `_forms` — Cursor's effort word `Extra High` is the catalog suffix `xhigh`; the original spelling still matches a slug that already says `extra-high`.

### Mocks

- none

### Tests

- `test_cursor_display_name_matches_the_catalog_id_it_names` — Opus, Sol and Grok at 300K and 1M High match their catalog ids; Extra High matches `xhigh`; a different effort and a different model stay mismatches.
- `test_a_context_size_without_an_effort_word_does_not_match_another_effort` — `GPT-5.6 Sol 1M` with the Sol profile's model name and effort aliases does not match `gpt-5.6-sol-high`.
