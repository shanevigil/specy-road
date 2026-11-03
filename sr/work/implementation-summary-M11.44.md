# Implementation summary — M11.44 (`init-profiles-subset`)

## Goal

Adopters can limit which shipped model profiles `init project` copies, and `refresh-profiles` can add a single missing profile by `api_id`.

## Touch zones (confirmed)

- `specy_road/init_project.py`
- `specy_road/cli_init_argparse.py`
- `specy_road/bundled_scripts/refresh_profiles.py`
- `specy_road/cli.py` — one-line wiring of `--profiles` into `run_init_project` (required; omitted from the roadmap row)
- `tests/test_init_profiles_subset.py`
- `docs/orchestration-models.md`

## Behaviour

- **`init project --profiles SPEC`** (default `all`): unchanged default copies the full `model-profiles/` tree. `none` copies only `model-profiles/README.md` and `model-profiles/harness-facts.yaml`. A comma-separated list copies those two plus any profile whose family directory or `api_id` matches a token (no `harness-captures/` unless `all`). Unknown tokens exit 1.
- **`refresh-profiles --only API_ID`**: copies at most that profile when missing; rejects unknown `api_id` and combinations with `--check` / `--render` / `--capture`. Without `--only`, behaviour unchanged (every missing `*.md` under `model-profiles/`).

## Verification

- `pytest tests/test_init_profiles_subset.py`
- `pytest tests/test_models_and_prompt.py::test_refresh_profiles_adds_missing_and_keeps_edited`
- `specy-road file-limits`

## Added

- `_PROFILES_ALWAYS` — always scaffold README and harness-facts on subset init.
- `InitProfilesSelection` — parsed `--profiles` mode and token set.
- `bundled_profiles_template_dir()` — template `model-profiles/` path for validation.
- `index_bundled_profile_names()` — family names, api_ids, and api_id→rel map shared with refresh.
- `parse_init_profiles_spec()` — parse `all` / `none` / comma list.
- `validate_init_profiles_selection()` — fail on unknown subset tokens.
- `include_template_profiles_file()` — filter init copy loop under `model-profiles/`.
- `run_init_project(..., profiles=)` — validate and apply filter before copy.
- `refresh_profiles(..., only=)` — restrict missing-profile copy to one api_id.
- `--profiles` on init project parser; `--only` on refresh-profiles parser; `--only` mutual exclusion guard in `main`.
- `specy_road/cli.py` passes `profiles=ns.profiles` into `run_init_project`.
- `tests/test_init_profiles_subset.py` — default, none, one profile, CLI wiring, refresh `--only` vs full refresh.
- `docs/orchestration-models.md` — documents `--profiles` and `--only`.
