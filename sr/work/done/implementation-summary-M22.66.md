# Implementation summary: M22.66 `profile-match-reads-harness-model`

## What changed

- `specy_road/model_profiles.py`: new `match_entry(entry, candidates, match)` holds the one two-pass order:
  `match(candidate, id)` over every candidate first, and only when none matches, `match(candidate, harness_model)` over
  every candidate. An absent, non-string or blank (whitespace-only) `harness_model` adds no key. `profile_for_entry`
  uses it with `Profile.for_id` over `list_profiles` (working tree). The `roster_profile_gaps` warning now reads
  "matches no model profile by api_id, file name or alias of its id or harness_model". An explicit `profile:` path is
  unchanged.
- `specy_road/orchestration_pinned.py`: `_integration_profile_for_entry` uses the same `match_entry` over the committed
  profile paths, with `_pinned_for_id` as the matcher. Pass 2 therefore goes through `_pinned_for_id` too, so a
  `harness_model` match whose working-tree copy has drifted returns the existing integration-drift refusal (A3). The
  `pinned_profile_for_entry` docstring is updated.
- `docs/orchestration-roster.md`: one paragraph on how an entry without `profile:` finds its profile.
- `CHANGELOG.md` [Unreleased] / Fixed: one entry.

Net (added/removed): package +18/−7, tests +78/−4, docs +5, changelog +4.

## Touch zones

All five zones were accurate; no change was needed outside them. No file went over a `file-limits` cap.

## Parity goldens (A5)

No validate transcript under `tests/parity/` changed: the full suite passes with no golden edits. No launch flag changed
for an existing fixture entry.

## Test table → tests (`tests/test_model_profile_aliases.py`)

| Row | Test |
|---|---|
| api_id | `test_an_entry_matches_its_profile_by_harness_model[claude-opus-5-5]` checks that validate does not name the entry and that the executor prompt for `my-opus` holds the Opus model notes and prompting rules; also the `our-own-model, harness_model: claude-opus-5-5` row of `test_roster_profile_gaps_reports_and_hints_by_id_and_launchability` (no gap) |
| alias | the same test with `[claude-opus-5-5-high]`, a Cursor entry (the shipped profile already lists that alias) |
| id wins | `test_an_id_match_beats_a_harness_model_match_on_both_lookups[entry0]`: profile `b-model.md` sorts before `claude-opus-5-5.md` (asserted), and both `profile_for_entry` and `pinned_profile_for_entry` return the opus profile |
| blank | the same test's `"  "` and absent rows (no match). A blank `harness_model` fails the roster schema (`$defs/id`), so `roster_profile_gaps` never sees one, and the planned gaps row for it was dropped |
| neither | the `claude-opus-x, harness_model: unknown-zz` row of the gaps test still warns and names the closest profile |
| pinned | `test_an_entry_matches_its_profile_by_harness_model`, second half: with the working-tree profile deleted, `profile_for_entry` finds nothing but the prompt still holds the notes from the integration branch |
| pinned drift, api_id / alias | `test_a_drifted_profile_matched_by_harness_model_is_refused_and_runs_nothing[…]`: `pinned_profile_for_entry` is refused with the drift reason, and `prompt --channel cli --run` exits 1 with that reason, with neither the committed nor the local `access.cli` marker file created |
| explicit | `test_an_id_match_beats_…[entry3]`: an entry with `profile:` and a `harness_model` naming another profile keeps its `profile:` path |

The existing `_gap` helper's expected text was updated to the new warning wording (A2).

Red-green: with only the package change reverted, 15 tests in this file fail, including every new row above. With
the change, all 27 pass.

## Gates

`specy-road validate`, `export --check` and `digest --check` (dogfood fixture), and `specy-road file-limits`, pass.
`pytest -n 4`: 7162 passed, 18 skipped.

## Added

- `model_profiles.match_entry`: the single two-pass lookup order shared by the working-tree and integration-branch lookups (A1: "one order, not two copies").
- Branch in `match_entry`: skip `harness_model` when it is absent, not a string, or blank (A1: "an absent or blank harness_model is no key").
- Test helper `_harness_model_repo`: builds the repo with a second profile `b-model` that sorts first, plus the roster entries, landed on `dev`. The id-wins, pinned and drift rows all need this setup.
- Test constants `OPUS_REL` and `NOTES`: shared by the three new tests.
- Test `test_an_entry_matches_its_profile_by_harness_model` (parametrized api_id / alias): the api_id, alias and pinned rows.
- Test `test_an_id_match_beats_a_harness_model_match_on_both_lookups` (parametrized): the id-wins, harness_model-only, blank, absent and explicit rows on both lookups.
- Test `test_a_drifted_profile_matched_by_harness_model_is_refused_and_runs_nothing` (parametrized api_id / alias): the two pinned-drift rows.
- Parameter rows added to `test_roster_profile_gaps_reports_and_hints_by_id_and_launchability`: the neither row (`unknown-zz`) and the api_id match (no gap).
- Mocks: none.
