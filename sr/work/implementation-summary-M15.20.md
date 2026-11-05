# M15.20 — zones-missing-what-acceptance-needs-flagged

## Summary

Plan-time checks now compare each ready leaf's acceptance criteria to its touch zones. `orchestrate plan` and `grind-session --plan` emit one warning per affected leaf, listing existing repo paths that no zone covers and grouping not-yet-tracked paths outside all zones as `new file outside zones`. Brief call-site listings cap at 20 importers per zoned file (was 10), with a count for the remainder.

## Touch zones (confirmed)

- `specy_road/zone_coverage.py` (new)
- `specy_road/orchestrate_plan.py`
- `specy_road/bundled_scripts/brief_call_sites.py`
- `specy_road/bundled_scripts/orchestrate_cli.py`
- `specy_road/bundled_scripts/session_plan.py`
- `specy_road/bundled_scripts/session_plan_git.py`
- `specy_road/bundled_scripts/session_plan_render.py`
- `tests/`

`generate_brief.py` was not changed; it already calls `brief_call_sites.call_site_lines`.

## Acceptance

- **A1:** `zone_coverage_warnings` runs from `build_orchestration_plan` (ready assignments) and `gather_session_plan` (ready queue). Warnings render with `!` in `orchestrate_cli.render` and in the grind plan text/JSON `zone_coverage` field. Pinned by `tests/test_zone_coverage.py`.
- **A2:** `IMPORTER_CAP = 20` in `brief_call_sites.py`; `tests/test_brief_call_sites.py::test_two_hundred_importers_list_twenty_then_count`.

## Added

- `specy_road/zone_coverage.py`: path token extraction, tracked-path lookup, uncovered labels, and `zone_coverage_warnings` — core A1 behaviour.
- `Assignment.warnings` on orchestrate assignments — carries plan-time zone gap text without affecting `ok`.
- `SessionPlan.zone_coverage` — JSON/text field for grind-session `--plan`.
- `tests/test_zone_coverage.py` — A1 unit and CLI coverage for orchestrate and grind-session.
- `tests/test_brief_call_sites.py::test_two_hundred_importers_list_twenty_then_count` — A2 bound with 200 synthetic importers.
- none (mocks)
