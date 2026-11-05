# M15.19 implementation summary — Cursor display-name cost

## Root cause

Field roster entry `cursor-grok-4.6-high` (`harness_model: cursor-grok-4.6-high`) points at a `grok-4.6` profile with no `aliases`. `apply_roster_price_estimate` matched only `Profile.for_id(model_id)`, so it found no price and showed `$?`. Separately, `mismatch_note` compared `cursor-grok-4.6-high` with Cursor's `Grok 4.6 High` and saw a mismatch. The mismatch did not cause the missing cost.

## Changes

- `specy_road/model_names.py` (new):
  - `normalise` lowercases the name and turns every run of characters other than letters and digits into one `-`. That covers spaces, dots, hyphens, underscores and Cursor's zero-width padding.
  - `same_model(reported, slug, harness_model, profile)` checks the reported name against the slug, `harness_model`, and the profile's `api_id`, file name, `aliases`, `model` and `display_name`. It also tries each name without Cursor's `cursor-` prefix.
  - `roster_match(repo_root, model_id)` returns the first roster entry whose `id` / `harness_model` is the launched id, or whose pinned profile answers to it, together with that profile.
- `specy_road/worker_adapter_parsers.py`: `apply_roster_price_estimate` now uses `roster_match`, so the grok entry is priced from its profile. It also sets the new `ROSTER_PRICED` marker on the cost it fills (rework R1). The file is now 386 lines.
- `specy_road/worker_models.py`:
  - `mismatch_note` uses `same_model` and takes optional `harness_model` / `profile` arguments.
  - New `usage_event(repo_root, detail)` builds the usage event's summary and detail. On a real mismatch it drops the cost only when `apply_roster_price_estimate` filled it (marker `ROSTER_PRICED` = `cost_from_roster`), so the cost shows `?`. A cost the harness reported is kept, even one it parses as an estimate (Claude's `total_cost_usd`). The marker is popped and never stored.
  - The old `_model_key` is removed.
- `specy_road/worker_runner.py`: in `_append_usage`, the `append_event` call now takes `**usage_event(repo_root, detail)`. The imports changed to match: `mismatch_note` and `usage_text` are no longer imported there. The file stays at 396 lines.

Dots count as separators rather than being removed. That keeps the existing `composer-2.5` ≠ `composer-25` assertion in `tests/test_worker_turn_accounting.py` passing without editing it.

**Final touch zones:** `specy_road/model_names.py`, `specy_road/worker_models.py`, `specy_road/worker_adapter_parsers.py`, `specy_road/worker_runner.py`, `tests/`.

## Rework (R1, review by cursor-grok-4.6-high)

The previous guard keyed on `cost_is_estimate`. Claude Code parses `total_cost_usd` with `estimate=True`, so a real Claude mismatch lost a cost the harness had reported. The fix changes the signal: `apply_roster_price_estimate` marks its own fill, and `usage_event` reads that marker, not `cost_is_estimate`. `worker_adapter_claude.py` is unchanged.

## Probes

- Class: a cost the harness reported, treated as if the roster filled it. With the fix, only the roster fill sets the marker, so no harness parse can reach the drop.
- Claude Code (`total_cost_usd`, `estimate=True`) mismatch: the cost is kept beside the note. Pinned by the new run-level test, which fails on the previous commit.
- Codex: its parser reports no cost, so any cost comes from the roster fill. The marker survives the `session_cost_usd` `replace` in `CodexAdapter.parse_events`. A mismatch drops `cost_usd`; checked with a direct `usage_event` call.
- Codex, the same mismatch: `session_cost_usd` stays stored. That is existing behaviour, and it keeps the next turn's delta (`worker_usage_delta.turn_usage`) relative to the previous total.
- Cursor real mismatch: the cost is still dropped (existing test). Cursor naming-only difference: the cost is kept and the marker is not stored (assert added).
- `cost_is_estimate=True` without the marker, on a mismatch: the cost is kept. A naming-only difference with the marker: the cost is kept. Both checked with direct `usage_event` calls.
- Stored detail and schema: the marker is popped in `usage_event`, so the `usage` detail shape stays as before. `worker_cli_render` and `gui_app_routes_workers` totals never see it.
- Other callers of `apply_roster_price_estimate`: only `worker_adapter_base.parse_events` calls it, and its output reaches storage only through `_append_usage` → `usage_event`.

## Verification

- `pytest -n 4` on 15 worker test files (the reviewer's two command sets): 169 passed.
- `specy-road file-limits`: OK. `worker_adapter_parsers.py` is at 386 lines and `worker_runner.py` at 396.
- Red/green (R1): the new Claude test fails with the previous commit's `worker_models.py` and `worker_adapter_parsers.py`, and passes with the fix.
- Red/green: I ran the new run-level tests against the base code in a throwaway worktree. The display-name test fails there (no estimate). The real-mismatch test passes there too, because the base never priced that unaliased entry at all.

Out of scope: reasoning-token counts the harness does not report.

## Added

- `model_names.normalise`: one name comparison for usage, treating case, spaces, dots, hyphens and underscores as equivalent (A1).
- `model_names._forms`: the normalised name with and without Cursor's `cursor-` prefix, so `Grok 4.6 High` matches `cursor-grok-4.6-high` (A1).
- `model_names.same_model`: compares against the slug, `harness_model` and profile names (A1).
- `model_names.roster_match`: finds an entry by `id` / `harness_model` as well as profile ids, so an unaliased profile still prices (A1 cost).
- `worker_models.usage_event`: one place where the usage summary is built and an estimate is dropped on a real mismatch (A2).
- Guard in `usage_event`: drops the cost only when `ROSTER_PRICED` is set, never a cost the harness reported (A2 without losing real costs; R1).
- `worker_adapter_parsers.ROSTER_PRICED` marker, set by `apply_roster_price_estimate` and popped by `usage_event`: the only signal that a cost came from the roster (R1).
- `tests/test_cursor_display_name_cost.py::test_real_mismatch_keeps_a_cost_the_harness_reported`: a Claude turn told `claude-sonnet-5-5` whose init reports `claude-opus-5-5` and whose result has `total_cost_usd: 0.01`; it keeps that cost beside the mismatch note (R1).
- `tests/test_cursor_display_name_cost.py::_run_turn`: a shared fake-harness turn runner, so the cursor and claude-code run tests use one path.
- `tests/test_cursor_display_name_cost.py::test_display_name_is_the_rostered_slug_and_the_turn_is_priced`: cursor init (`Grok 4.6 High`) plus the recorded result line; no note, and the cost is estimated (A1).
- `tests/test_cursor_display_name_cost.py::test_real_mismatch_keeps_the_note_and_leaves_cost_unknown`: init `Composer 2.5`; the note is printed, the cost is `$?` and the detail cost is null (A2).
- `tests/test_cursor_display_name_cost.py::test_normalise_treats_case_spaces_dots_hyphens_alike`: pins normalisation, including the zero-width padding and `composer-2.5` ≠ `composer-25`.
- `tests/test_cursor_display_name_cost.py::test_same_model_against_slug_harness_model_and_profile`: pins matches on the slug, profile `model`, `api_id` and `display_name`, and non-matches for another model.
- Mocks: none. The run-level tests run a real `worker_runner.run` with a fake cursor script printing captured-shape lines. The `init` line is constructed in Cursor's shape (the fixture records only the result line); the result line is the recorded one.
