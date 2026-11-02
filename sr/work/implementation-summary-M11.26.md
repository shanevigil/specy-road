# Implementation summary: M11.26 — profile-aliases

## Goal

Ship Cursor effort-suffixed model ids as profile `aliases`, add a GPT-5.6 Sol profile, and have `specy-road models list` name roster ids that resolve to no profile.

## Touch zones (confirmed)

- `specy_road/model_profiles.py` — `unmatched_roster_ids`
- `specy_road/templates/project/model-profiles/` — new `gpt-5.6-sol.md`; `aliases` on Grok 4.7/4.6 and Composer 2.5; README roster row
- `specy_road/templates/project/schemas/` — no change (aliases already validated in `model_profiles._structure_errors`; no JSON schema for profile front matter)
- `docs/orchestration-models.md` — `models list` documents unmatched roster ids
- `tests/` — `test_model_profile_aliases.py`; counts in `test_models_and_prompt.py`

## Behaviour

- **A1:** Shipped templates include `openai-gpt/gpt-5.6-sol.md` with Cursor `gpt-5.6-sol-*` aliases; Grok and Composer profiles list Cursor effort ids from `harness-captures/cursor/inventory-models.txt`.
- **A2:** `models list` prints and JSON-exports `unmatched_roster_ids` for roster entries `pinned_profile_for_entry` cannot resolve; tests cover alias `for_id` matches and unmatched ids (`human`, `sol` in the fixture roster).

## Verification

- `pytest tests/test_models_and_prompt.py tests/test_model_profile_aliases.py`
- `specy-road file-limits`

## Added

- `unmatched_roster_ids` in `model_profiles.py` — collect roster entry ids with no profile match for `models list`
- `unmatched_roster_ids` JSON field and text section in `models_cli.cmd_list` — A2 reporting
- `specy_road/templates/project/model-profiles/openai-gpt/gpt-5.6-sol.md` — GPT-5.6 Sol profile and Cursor aliases
- `aliases` front matter on shipped Grok 4.7, Grok 4.6, Composer 2.5 profiles — A1
- README roster row for GPT-5.6 Sol — discoverability
- `tests/test_model_profile_aliases.py` — alias match and unmatched roster id list
- Profile count / refresh-profiles expectations in `test_models_and_prompt.py` — 17 shipped profiles
