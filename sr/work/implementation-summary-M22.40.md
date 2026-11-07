# Implementation summary: M22.40 — Cursor display names match the model they name

## Touch zones (confirmed)

Final touch zones: `specy_road/model_names.py`, `tests/test_model_names.py`, `CHANGELOG.md`.

`tests/test_model_names.py` was not in the tree; A2 names it, so it is new. Call sites stay unchanged. `review_model_check.check` and `worker_models.mismatch_note` already compare through `same_model`. `worker_adapter_parsers` only calls `roster_match`. `check` still returns `unreported` before that comparison when the harness reports no model. `normalise` is unchanged.

## Behaviour

One effort table (`_EFFORT_TAILS`, longest first) is the comparison rule. A context-size token (`300K`, `1M`, `256K`) is dropped only when the name ends in an effort from that table, so `Claude Opus 5.5 300K High` and `GPT-5.6 Sol 1M High` match `claude-opus-5-5-high` and `gpt-5.6-sol-high`. `Extra High` is `xhigh`. `fast` stays on the identity (`high-fast` is not `high`).

When the slug or `harness_model` names an effort, a profile name that names a different effort is not added. A Medium or Low report with a context size does not match a High request through `same_model`, `review_model_check.check`, or `worker_models.mismatch_note`, even when the profile lists every effort as an alias. A profile name that names no effort still counts, so `Grok 4.6` matches `cursor-grok-4.6-high` through the profile's model name. A name that does not end in an effort keeps its context-size token, so `GPT-5.6 Sol 1M` (medium, the word omitted) does not become the bare model.

Limit: a request that names no effort still accepts every profile alias. Effort identity is enforced only when the slug or `harness_model` names one.

## Probes

- Class: a profile alias list that names every effort, so the report's effort is lost when those aliases are unioned in. Checked on Sol and Grok, for Medium, Low, Max, None, Minimal, Extra High and High Fast, through `same_model`, `check` and `mismatch_note`. A different effort does not match; the same effort does.
- `check("GPT-5.6 Sol 1M Medium", high entry, Sol profile)` returns `mismatch`. `check` of the High report returns `match`.
- `mismatch_note` for that Medium report is the mismatch suffix. The High report's note is empty.
- `same_model("gpt-5.6-sol-high", None, None, Sol profile)` stays true, so `check` still attaches the profile for a High effective model.
- `check("")` and `check(None)` stay `unreported`.
- `GPT-5.6 Sol 256K High` matches `gpt-5.6-sol-high` with the Sol profile. `256K Low` does not.
- `GPT-5.6 Sol 1M` (no effort word) against `gpt-5.6-sol-high` with the Sol profile stays false.
- `Grok 4.6` against `cursor-grok-4.6-high` with a profile whose model name has no effort stays true.
- `Grok 4.7 1M Low` against `grok-4.7-high` with the Grok aliases stays false.
- A request with no slug and no `harness_model` still matches a Medium report through the aliases. That is the limit above, not the High-request path.

## Added

### Helpers

- `_EFFORT_TAILS` — the one effort table (longest first), including `fast`, so context-size dropping and effort identity use the same suffixes.
- `_CONTEXT_SIZE` — the token shape of a context size (`300k`, `1m`, `256k`).
- `_tail` — the effort identity a name ends with, or none.
- `_comparable` — normalised name with `Extra High` as `xhigh` and a context-size token dropped only beside an effort tail.
- `_effort` — that identity for a request or a profile name; missing names have none.
- `_keeps_name` — keeps a profile name that names no effort, or the effort the request names.
- `_profile_names` — profile ids and names passed through `_keeps_name` before they join the comparison.

### Branches or guards

- none beyond `_keeps_name`: a profile name with a different effort is left out, and a request that names no effort keeps every profile name.

### Mocks

- none

### Tests

- `test_cursor_display_name_matches_the_catalog_id_it_names` — Opus, Sol and Grok at 300K and 1M High match their catalog ids; Extra High matches `xhigh`; a different effort and a different model stay mismatches.
- `test_a_context_size_without_an_effort_word_does_not_match_another_effort` — `GPT-5.6 Sol 1M` with the Sol profile's model name and effort aliases does not match `gpt-5.6-sol-high`.
- `test_a_profile_alias_for_another_effort_does_not_match` — a High request with a profile that lists every effort does not match a Medium (or other) report that carries a context size, through `same_model`, `check` and `mismatch_note`; the same effort still matches.
