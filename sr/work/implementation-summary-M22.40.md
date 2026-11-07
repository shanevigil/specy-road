# Implementation summary: M22.40 — Cursor display names match the model they name

## Touch zones (confirmed)

Final touch zones: `specy_road/model_names.py`, `tests/test_model_names.py`, `CHANGELOG.md`.

`tests/test_model_names.py` was not in the tree; A2 names it, so it is new. Call sites stay unchanged. `review_model_check.check` and `worker_models.mismatch_note` already compare through `same_model`. `worker_adapter_parsers` only calls `roster_match`. `check` still returns `unreported` before that comparison when the harness reports no model. `normalise` is unchanged.

## Behaviour

One effort table (`_EFFORT_TAILS`, longest first, each suffix with its canonical form) is the comparison rule. Only the context-size token immediately before the trailing effort suffix is dropped, so `Claude Opus 5.5 300K High` and `GPT-5.6 Sol 1M High` match `claude-opus-5-5-high` and `gpt-5.6-sol-high`, and `Model 1M Series High` does not match `model-series-high`. `Extra High` becomes `xhigh` only when it is that trailing suffix, so `Grok 4.7 500K Extra High` matches `grok-4.7-xhigh` and `Extra High Model` does not match `xhigh-model`. `fast` stays on the identity (`high-fast` is not `high`).

When the slug or `harness_model` names an effort, a profile name that names a different effort is not added. A Medium or Low report with a context size does not match a High request through `same_model`, `review_model_check.check`, or `worker_models.mismatch_note`, even when the profile lists every effort as an alias. A profile name that names no effort still counts, so `Grok 4.6` matches `cursor-grok-4.6-high` through the profile's model name. A name that does not end in an effort keeps its context-size token, so `GPT-5.6 Sol 1M` (medium, the word omitted) does not become the bare model.

Limit: a request that names no effort still accepts every profile alias. A `<digits>k` or `<digits>m` token in the one position immediately before a trailing effort is a context size on either name, so a catalog id is not expected to carry one there.

## Probes

- Class: a profile alias list that names every effort, so the report's effort is lost when those aliases are unioned in. Checked on Sol and Grok, for Medium, Low, Max, None, Minimal, Extra High and High Fast, through `same_model`, `check` and `mismatch_note`. A different effort does not match; the same effort does.
- `check("GPT-5.6 Sol 1M Medium", high entry, Sol profile)` returns `mismatch`. `check` of the High report returns `match`.
- `mismatch_note` for that Medium report is the mismatch suffix. The High report's note is empty.
- `same_model("gpt-5.6-sol-high", None, None, Sol profile)` stays true, so `check` still attaches the profile for a High effective model.
- `GPT-5.6 Sol 256K High` matches `gpt-5.6-sol-high`. `256K Low` does not.
- `GPT-5.6 Sol 1M` (no effort word) against `gpt-5.6-sol-high` with the Sol profile stays false.
- `Grok 4.6` against `cursor-grok-4.6-high` with a profile whose model name has no effort stays true.
- `Grok 4.7 1M Low` against `grok-4.7-high` with the Grok aliases stays false.
- A request with no slug and no `harness_model` still matches a Medium report through the aliases. That is the limit above, not the High-request path.
- Class: `extra-high` rewritten anywhere in the name, not only as the trailing effort suffix. `Extra High Model`, `Model Extra High Series`, `Extra High Fast Model`, `extra-high-model`, and `Extra High Model High` do not match the `xhigh` spelling. Trailing `Model Extra High`, `Extra High`, `Grok 4.7 Extra High Fast`, and `Grok 4.7 500K Extra High` do match `xhigh` / `xhigh-fast`. `Extra High` does not match `high`.
- Class: every context-size token dropped once an effort is present, not only the token immediately before the trailing suffix. `Model 1M Series High`, `Model 300K Series Extra High`, `1M Model High`, `Model High 1M`, `Model 1M 300K High`, and `Model 1M Series High Fast` do not match the name with that token removed. `Model 1M High Fast`, `Claude Opus 5.5 300K High`, and `GPT-5.6 Sol 256K High` do match. `256K Low` and `Grok 4.7 500K High` against `grok-4.6-high` do not.
- `check` and `mismatch_note` for `Extra High Model` against `xhigh-model`, and for `Model 1M Series High` against `model-series-high`, are mismatch. `check("Grok 4.7 500K Extra High", grok-4.7-xhigh)` is match. An alias equal to the collapsed spelling does not make either false pair match.
- `check("")` and `check(None)` stay `unreported`. `GPT-5.6 Sol 1M Medium` against `gpt-5.6-sol-high` with the Sol aliases stays false.

## Added

### Helpers

- `_EFFORT_TAILS` — the one effort table (raw suffix, canonical form, longest first), so `Extra High` becomes `xhigh` only as that trailing suffix and context-size dropping uses the same suffix.
- `_CONTEXT_SIZE` — the token shape of a context size (`300k`, `1m`, `256k`).
- `_tail` — the canonical effort identity a name ends with, or none.
- `_drop_context` — drops the single context-size token immediately before a matched effort suffix.
- `_rewrite` — applies the table to the trailing suffix and that one context-size token.
- `_comparable` — normalised name after `_rewrite`.
- `_effort` — that identity for a request or a profile name; missing names have none.
- `_keeps_name` — keeps a profile name that names no effort, or the effort the request names.
- `_profile_names` — profile ids and names passed through `_keeps_name` before they join the comparison.

### Branches or guards

- none beyond `_keeps_name`: a profile name with a different effort is left out, and a request that names no effort keeps every profile name.

### Mocks

- none

### Tests

- `test_cursor_display_name_matches_the_catalog_id_it_names` — Opus, Sol and Grok at 300K and 1M High match their catalog ids; Extra High matches `xhigh`; a different effort and a different model stay mismatches; `Extra High Model` does not match `xhigh-model`; `Model 1M Series High` does not match `model-series-high`.
- `test_a_context_size_without_an_effort_word_does_not_match_another_effort` — `GPT-5.6 Sol 1M` with the Sol profile's model name and effort aliases does not match `gpt-5.6-sol-high`.
- `test_a_profile_alias_for_another_effort_does_not_match` — a High request with a profile that lists every effort does not match a Medium (or other) report that carries a context size, through `same_model`, `check` and `mismatch_note`; the same effort still matches.
