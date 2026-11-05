# M15.20 — zones-missing-what-acceptance-needs-flagged

## Summary

Plan-time checks compare acceptance criteria to touch zones per **A1** in the roadmap (planner rule 2026-11-05). `uncovered_acceptance_paths` holds the full rule in its docstring; warnings include a best-effort hint. Brief importer cap: 20.

**Fix round (grok, bare suffix extraction):** `_BARE_SUFFIX` extracts bare tokens ending in a known suffix; `_normalize` strips `(` with other punctuation. `_is_candidate` already treated bare+suffix as candidates; the failure class was **bare suffix token extraction** in `_tokens` only.

## A1 clause check (roadmap acceptance line 1)

| Clause | Implementation / test |
| --- | --- |
| orchestrate plan and grind-session `--plan` warn once per leaf | `zone_coverage_warnings` → `Assignment.warnings`; `test_orchestrate_and_grind_warn_once_per_leaf` |
| lists paths outside zones; nonexistent uncovered → `new file outside zones` | `uncovered_acceptance_paths` labels; table rows `a1-backtick-slash-new`, `a1-bare-suffix-new` |
| one covered + one uncovered path pin | `a1-one-covered-one-uncovered` |
| backtick span with `/` or known suffix → always candidate | `_is_candidate` backtick branch; `a1-backtick-slash-*`, `a1-backtick-suffix-new` |
| bare token: tracked top-level dir name **or** known suffix | `_BARE_DIR` + `_BARE_SUFFIX`; `_is_candidate` bare branch; `a1-bare-top-level-*`, `a1-bare-suffix-new` |
| existing = tracked file or directory (optional trailing `/`); else new | `_exists`; existing uncovered by path label; new → `NEW_OUTSIDE` |
| ignore and/or, read/write, M12/M13, URLs | no candidate extraction for those shapes; table ignore rows |
| warning cites best-effort hint | `BEST_EFFORT_HINT` in `leaf_zone_coverage_warning` |

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

- **A1:** Rule in `uncovered_acceptance_paths` docstring; one warning per leaf via orchestrate and grind `--plan`; `test_a1_path_rule_table` parametrizes every clause (positive and negative).
- **A2:** `IMPORTER_CAP = 20`; `test_two_hundred_importers_list_twenty_then_count`.

## Probes

- **`_BARE_SUFFIX` / `_tokens` (bare suffix class):** `Ship NOTES.txt today` and `Ship (NOTES.txt) today` → `{NEW_OUTSIDE}`; grok repro empty list fixed.
- **`_is_candidate` bare branch:** suffix-only bare still candidate when extracted; top-level dir head unchanged.
- **`_BARE_DIR` (bare dir class):** `See docs/ next` → `{docs}`; no regression.
- **`_SLASH_TOKEN` (prose slash class):** `Compare input/output` still `[]`.
- **`_normalize` punctuation:** `(` stripped with `.,;:)`.
- **Non-existing label (new-path class):** backtick and bare suffix nonexistent paths → `NEW_OUTSIDE`.
- **`_exists` (existing class):** in-zone and existing uncovered paths unchanged in table.
- **`in_zones`:** covered paths silent.
- **`zone_coverage_warnings` / integration:** one warning on orchestrate, session plan text/JSON, grind `--plan`.
- **`_tracked_paths` None:** still returns `[]` (unchanged code path).

## Added

- `specy_road/zone_coverage.py`: `_BARE_SUFFIX`, punctuation strip, docstring bare clause.
- `tests/test_zone_coverage.py`: A1 table rebuilt clause-by-clause; bare suffix + paren rows.
- `tests/test_brief_call_sites.py::test_two_hundred_importers_list_twenty_then_count`.
- none (mocks)
