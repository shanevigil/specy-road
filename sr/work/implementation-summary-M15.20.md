# M15.20 — zones-missing-what-acceptance-needs-flagged

## Summary

Plan-time checks compare acceptance criteria to touch zones per **A1** in the roadmap (planner rule 2026-11-05). `uncovered_acceptance_paths` holds the full rule in its docstring; warnings include a best-effort hint. Brief importer cap: 20.

**Fix round (grok, A1 alignment):** Backtick spans with ``/`` or a known suffix are always candidates; any non-existing candidate outside zones adds `new file outside zones` (including ``brand/newdir``). Bare ``docs/`` is extracted and lists tracked directory ``docs``. Non-existing candidates no longer require a tracked parent.

## Touch zones (confirmed)

- `specy_road/zone_coverage.py`
- `specy_road/orchestrate_plan.py`
- `specy_road/bundled_scripts/brief_call_sites.py`
- `specy_road/bundled_scripts/orchestrate_cli.py`
- `specy_road/bundled_scripts/session_plan.py`
- `specy_road/bundled_scripts/session_plan_git.py`
- `specy_road/bundled_scripts/session_plan_render.py`
- `specy_road/orchestrate_assign.py`
- `tests/`

## Acceptance

- **A1:** Rule in `uncovered_acceptance_paths` docstring; one warning per leaf via orchestrate and grind `--plan`; `test_a1_path_rule_table` parametrizes every clause.
- **A2:** `IMPORTER_CAP = 20`; `test_two_hundred_importers_list_twenty_then_count`.

## Probes

- **`_is_candidate` (candidate class):** only gate for backtick vs bare; backtick `brand/newdir` and bare `docs/` cases covered in A1 table.
- **`_tokens` / `_BARE_DIR` (bare dir class):** `See docs/ next` yields ``docs``; slash-token regex still ignores lone prose slashes.
- **Non-existing label (new-path class):** any uncovered non-existing candidate sets `NEW_OUTSIDE` once; no `_report_as_new` parent gate left.
- **`_exists` (existing class):** tracked files and directory prefixes unchanged; existing uncovered paths still listed by path.
- **`in_zones`:** covered-path cases in A1 table still silent.
- **`zone_coverage_warnings` / `leaf_zone_coverage_warning`:** hint references docstring rule; integration test checks one warning on three surfaces.
- **`_tracked_paths` None:** still returns `[]`.

## Added

- `specy_road/zone_coverage.py`: A1 rule in `uncovered_acceptance_paths`, `_BARE_DIR`, `_is_candidate`.
- `tests/test_zone_coverage.py`: `test_a1_path_rule_table`, orchestrate/grind integration test.
- `tests/test_brief_call_sites.py::test_two_hundred_importers_list_twenty_then_count`.
- none (mocks)
