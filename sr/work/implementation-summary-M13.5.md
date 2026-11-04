# Implementation summary — M13.5

## What changed

- **A1, roster filter** (`specy_road/bundled_scripts/refresh_profiles.py`): `refresh_profiles()` has a new parameter, `profiles: str = "roster"` (`roster` | `all`). With `roster` it writes only the README and the bundled profiles that a `roadmap/orchestration.yaml` roster entry names. An entry names a profile by its `id` (matched with `Profile.for_id`, so the api_id, file stem or an alias all count) or by its `profile:` path. `--profiles all` keeps today's behaviour. `--only` still takes precedence. Paths given with `--force` are always kept, so you can still force a profile the roster does not name. The CLI has a new `--profiles roster|all` flag. When roster mode selects no profile, the CLI prints `no roster entry … names a profile this specy-road ships; \`specy-road refresh-profiles --profiles all\` adds every one`. `upgrade.py` was not edited; its existing `refresh_profiles(project, dry_run=…)` call now gets the roster default.
- **A2, near-miss alias** (`specy_road/model_profiles.py`): when a roster entry matches no profile, `roster_profile_gaps` keeps today's warning text. If exactly one bundled profile's api_id, stem or alias matches the roster id after normalising, it adds: `; it differs from bundled api_id <api_id> only in punctuation or a vendor/effort prefix or suffix: add \`profile: model-profiles/<family>/<file>.md\` to that entry`. If that file is not in the repo yet, it also says `, then run \`specy-road refresh-profiles\` to add the file`. Normalising means lower-case, `.`/`_` → `-`, stripping one known harness/vendor prefix and stripping one known effort suffix. Bundled profiles are read from the package template. Importing `init_project` here would create an import cycle, so I didn't.
- **A3**: the roster is not edited, profiles already on disk are not deleted, and profile content is unchanged.

## Touch zones (final)

`specy_road/bundled_scripts/refresh_profiles.py`, `specy_road/model_profiles.py`, `tests/`. No new modules. `file-limits` passes.

Note, outside the zones and left unchanged: when nothing is written, `upgrade.py` prints `model-profiles/ already has every profile this version ships`. Under the roster default that wording is a little broad, and upgrade does not print the `--profiles all` hint; only the `refresh-profiles` CLI does. A follow-up could change `upgrade.py` if wanted.

## Existing tests updated (behaviour change from A1, not a weakening)

These tests relied on "every profile" being the default, so they now pass `profiles="all"` / `--profiles all`:
- `tests/test_models_and_prompt.py::test_refresh_profiles_adds_missing_and_keeps_edited`
- `tests/test_init_profiles_subset.py::test_refresh_profiles_without_only_still_adds_every_missing`
- `tests/test_review_round6_policy.py::test_refresh_profiles_refuses_a_symlinked_destination` (it needs `anthropic-claude/` files to be written so the symlink check is reached)

## Verification

- `python -m pytest -q -n 4`: 3966 passed
- `specy-road file-limits`: OK
- `ruff check` on the changed files: clean
- Red/green: with only the `model_profiles.py` change reverted, both near-miss parametrized tests in `tests/test_refresh_profiles_roster.py` fail.

## Added

- `refresh_profiles._roster_rels`: collects the bundled profile paths that roster entries name, by id, alias or `profile:` (A1).
- `refresh_profiles(profiles=…)` parameter, plus a ValueError guard for values other than roster/all (A1).
- Roster branch in `refresh_profiles` that also adds README and `--force` paths: README always ships, and `--force` must still reach a profile outside the roster (A1).
- `--profiles roster|all` CLI flag, and the check that refuses it together with `--check/--render/--capture` (same rule as `--only`) (A1).
- `_copy_missing` no-roster hint line naming `--profiles all`, and the "already has every profile the roster names" wording (A1).
- `model_profiles._ID_PREFIXES` / `_ID_SUFFIXES`: the vendor/harness prefixes and effort suffixes that get stripped (A2).
- `model_profiles._norm_id`, `_id_forms`: normalise punctuation and case, and strip the affixes (A2).
- `model_profiles.near_miss_profile`: the unique bundled profile that matches after normalising, else None (A2).
- `model_profiles._near_miss_fix`: builds the `profile:` roster line, plus the refresh hint when the file is missing (A2).
- `model_profiles.bundled_profiles_root`: package template root without importing `init_project` (that import would be circular) (A2).
- `tests/test_refresh_profiles_roster.py`: covers roster-only writes (id, alias and `profile:`), no roster → README plus hint, `--profiles all` → full set, `--force` outside the roster, the two near-miss examples, and an unrelated id keeping today's text (A1, A2).
