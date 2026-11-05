# M15.20 — zones-missing-what-acceptance-needs-flagged

## Summary

Plan-time checks compare acceptance criteria to touch zones per **A1** in the roadmap (planner rule 2026-11-05, **clarified on WIP**). `uncovered_acceptance_paths` holds the full rule in its docstring; warnings include a best-effort hint. Brief importer cap: 20.

**Fix round (gpt-6.1-sol-low, clarified A1):** Nonexistent uncovered paths are listed as `new file outside zones: <path>` (each path named). Bare candidacy requires `/` with a tracked top-level first segment or a known suffix; bare words like `docs` are prose. `_is_candidate` uses `had_slash` so `docs/` stays a candidate. `test_worker_cli_fixes` fixture acceptance uses `src/a.py` in zone.

## A1 clause check (clarified roadmap acceptance line 1)

| Clause | Implementation / test |
| --- | --- |
| orchestrate plan and grind-session `--plan` warn once per leaf | `zone_coverage_warnings`; `test_orchestrate_and_grind_warn_once_per_leaf`, `test_two_new_paths_in_both_planner_outputs` |
| list uncovered paths; new paths as `new file outside zones: <path>` | `new_outside_label`; table + two-path planner test |
| one covered + one uncovered path pin | `a1-one-covered-one-uncovered` |
| backtick with `/` or suffix → always candidate | backtick branch of `_is_candidate`; table backtick rows |
| bare: `/` + tracked top-level first segment, or suffix; bare words prose | `_BARE_DIR`, `_BARE_SUFFIX`, `_is_candidate` + `had_slash`; `a1-bare-word-prose-not-path` |
| existing tracked file/dir listed by path | `_exists`; existing rows in table |
| ignore and/or, read/write, M12/M13, URLs | table ignore rows |
| best-effort hint on warning | `BEST_EFFORT_HINT` |

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

- **A1:** Rule in docstring; named new paths; one warning per leaf on both planners; `test_a1_path_rule_table` + integration tests.
- **A2:** `IMPORTER_CAP = 20`; `test_two_hundred_importers_list_twenty_then_count`.

## Probes

- **Bare word prose class:** `Update docs today` with tracked `docs/api.json` → `[]`; aligns with clarified A1 (not sol-low’s pre-clarification expectation).
- **`had_slash` + top-level dir class:** `See docs/ next` → `{docs}`; `Extend docs/contracts` unchanged.
- **`_is_candidate` bare without slash/suffix:** top-level dir name alone not candidate after normalize.
- **Per-path new label class:** `Add \`new/a.py\` and \`new/b.py\`` → two `new_outside_label` entries; orchestrate render + grind JSON both show full message.
- **Single new paths:** backtick/bare suffix rows use `_new(<path>)` in table.
- **`test_text_plan_always_names_the_roster_ref`:** acceptance `src/a.py exists` in `src/` zone → no `!` zone warning; roster lines unchanged.
- **Direct-importer pytest set** (`rg` on zone_coverage/orchestrate imports): all pass.
- **`leaf_zone_coverage_warning` / `zone_coverage_warnings`:** still join all labels; integration paths unchanged aside from label text.
- **`_tracked_paths` None:** still returns `[]`.

## Added

- `new_outside_label`, `_is_candidate` bare rule with `had_slash`.
- `tests/test_zone_coverage.py`: clarified A1 table, `test_two_new_paths_in_both_planner_outputs`.
- `tests/test_worker_cli_fixes.py`: localized acceptance fix for roster-ref test.
- none (mocks)
