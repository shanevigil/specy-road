# M15.20 — zones-missing-what-acceptance-needs-flagged

## Summary

Plan-time checks compare acceptance criteria to touch zones per **A1** in the roadmap (planner rule 2026-11-05, clarified on WIP). `uncovered_acceptance_paths` holds the full rule in its docstring; warnings include a best-effort hint. Brief importer cap: 20.

**Fix round (sol-low, URL + top-level dir):** `_strip_urls` removes complete `http(s)://…` spans before bare token regexes. `_top_level_dirs` uses only tracked git paths that contain `/` (directories with nested files), not root file names.

## A1 clause check (roadmap acceptance line 1)

| Clause | Implementation / test |
| --- | --- |
| orchestrate plan and grind-session `--plan` warn once per leaf | integration tests in `test_zone_coverage.py` |
| list uncovered paths; new paths as `new file outside zones: <path>` | `new_outside_label`; `a1-two-new-paths-each-named` |
| one covered + one uncovered path pin | `a1-one-covered-one-uncovered` |
| backtick with `/` or suffix → always candidate | backtick rows in table |
| bare: `/` + tracked top-level **directory**, or suffix; bare words prose | `_top_level_dirs`, `_BARE_*`, `_is_candidate`; `a1-bare-word-prose-not-path` |
| existing tracked file/dir listed by path | `_exists`; existing rows |
| ignore prose, URLs (including query suffixes) | `_strip_urls`; `a1-ignore-url`, `a1-ignore-url-query-with-suffix` |
| root file name is not a top-level directory | `a1-ignore-root-file-as-fake-directory` |
| best-effort hint | `BEST_EFFORT_HINT` |

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

- **A1:** Full rule in docstring; `test_a1_path_rule_table` covers each clause (positive and negative).
- **A2:** `IMPORTER_CAP = 20`; `test_two_hundred_importers_list_twenty_then_count`.

## Probes

- **URL span class:** `See https://example.com/?file=NOTES.txt next` → `[]`; query no longer scanned for `_BARE_SUFFIX`.
- **URL removal before all bare extractors:** applied on post-backtick scrub; slash/bare-dir/bare-suffix paths checked.
- **Top-level dir set class:** tracked `README.md` alone does not enter `_top_level_dirs`; `src/a.py` → `src`, `docs/api.json` → `docs`.
- **Fake directory slash token class:** `README.md/section` with sol-low tracked set → `[]`; not candidate (head not a directory).
- **Real directory paths:** `See docs/ next`, `Extend docs/contracts` table rows still pass.
- **Backtick / suffix / new-label / integration rows:** full `test_a1_path_rule_table` + planner integration tests green.
- **Direct-importer pytest set** (`rg` zone_coverage/orchestrate imports): all pass.
- **`_tracked_paths` None:** unchanged `[]`.

## Added

- `_URL`, `_strip_urls`; `_top_level_dirs` directory-only.
- Table rows `a1-ignore-url-query-with-suffix`, `a1-ignore-root-file-as-fake-directory`.
- none (mocks)
