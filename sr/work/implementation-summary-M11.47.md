# Implementation summary — M11.47 (`validate-zones-git-root`)

## What changed

`specy-road validate`'s touch-zone advisory check now resolves each zone against both the project root and the enclosing git root, matching `finish-this-task` and the review packet (`in_zones` / two-root zones in nested layouts).

- `warn_touch_zones_match_nothing` takes an optional `git_root`; `run_validation` passes `git_root(repo_root) or repo_root`.
- `_zone_matches_either_root` tries the project root first, then the git root when it differs.
- Guidance text and `docs/roadmap-authoring.md` document that zones may be written from either root, with a nested `specy_road/` example.

## Acceptance

- **A1:** Covered by `test_a_git_root_zone_outside_the_project_is_quiet` and `test_a_misspelled_git_root_zone_still_warns` in `tests/test_validate_touch_zones.py`.
- **A2:** `docs/roadmap-authoring.md` `touch_zones` row updated.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/validate_touch_zones.py`
- `specy_road/bundled_scripts/validate_roadmap_checks.py`
- `tests/test_validate_touch_zones.py`
- `docs/roadmap-authoring.md`

## Verification

- `pytest tests/test_validate_touch_zones.py -q`
- `specy-road file-limits`

## Added

- `_zone_matches_either_root` — tries `_zone_matches` on project root then git root so nested git-root zones resolve like finish/review-packet.
- `warn_touch_zones_match_nothing(..., git_root=)` keyword — caller supplies enclosing git root; embedded layout passes the same path twice via `git_root(r) or r`.
- `nested_project` pytest fixture — minimal `sr/` project beside `specy_road/` at git root for two-root tests.
- `test_a_git_root_zone_outside_the_project_is_quiet` — A1: In Progress node, existing git-root zone, no warning.
- `test_a_misspelled_git_root_zone_still_warns` — A1: typo under git-root zone still reported.
