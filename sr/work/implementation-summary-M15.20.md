# M15.20 — zones-missing-what-acceptance-needs-flagged

## Summary

Plan-time checks compare each ready leaf's acceptance criteria to its touch zones. `orchestrate plan` and `grind-session --plan` emit one warning per affected leaf, listing existing repo paths (files or directories that already contain tracked files) that no zone covers, and grouping wholly new paths as `new file outside zones`. Brief call-site listings cap at 20 importers per zoned file (was 10), with a count for the remainder.

**Fix round (grok-4.7-low):** `_exists` now treats a path as present when it is a tracked blob or when any tracked path lies under it as a directory prefix (with or without a trailing slash on the token). Directory tokens no longer collapse into `new file outside zones`.

## Touch zones (confirmed)

- `specy_road/zone_coverage.py` (new)
- `specy_road/orchestrate_plan.py`
- `specy_road/bundled_scripts/brief_call_sites.py`
- `specy_road/bundled_scripts/orchestrate_cli.py`
- `specy_road/bundled_scripts/session_plan.py`
- `specy_road/bundled_scripts/session_plan_git.py`
- `specy_road/bundled_scripts/session_plan_render.py`
- `tests/`

`specy_road/orchestrate_assign.Assignment.warnings` was added during the WIP merge (assignment logic split in M15.11); not a separate product feature of this leaf.

## Acceptance

- **A1:** `zone_coverage_warnings` from `build_orchestration_plan` and `gather_session_plan`; warnings in orchestrate render and grind plan text/JSON. Directories and files at `HEAD` list by path when uncovered; only wholly new paths add `new file outside zones`.
- **A2:** `IMPORTER_CAP = 20`; `test_two_hundred_importers_list_twenty_then_count`.

## Probes

- **`_exists` / `_path_like` (existence class):** only definitions of “path exists at ref”; both now share directory-prefix detection — no other duplicate existence checks in the module.
- **`uncovered_acceptance_paths`:** sole caller of `_exists` for warning labels; behaviour verified for mixed `docs/` / `docs/api` / file / new-path acceptance (reviewer scenario).
- **`zone_coverage_warnings`:** passes one `ls-tree` set into `uncovered_acceptance_paths` per plan call — same existence rules for every ready leaf.
- **`in_zones`:** paths under a declared zone (e.g. `src/new/file.py` with zone `src/`) still produce no label — parametrized case.
- **`build_orchestration_plan` / grind `--plan`:** unchanged wiring; still one warning string per leaf when labels non-empty — existing CLI tests pass.
- **`_tracked_paths` returns None`:** still yields no warnings (unchanged); no second code path to patch for git read failure.

## Added

- `specy_road/zone_coverage.py`: `_path_forms`, directory-aware `_exists`, token extraction, `zone_coverage_warnings`.
- `Assignment.warnings` in `orchestrate_assign.py` (post–M15.11 split) — plan-time zone gap text without affecting `ok`.
- `SessionPlan.zone_coverage` — grind-session `--plan` JSON/text.
- `tests/test_zone_coverage.py` — CLI coverage plus parametrized existence cases and reviewer mixed-path fixture.
- `tests/test_brief_call_sites.py::test_two_hundred_importers_list_twenty_then_count` — A2 bound.
- none (mocks)
