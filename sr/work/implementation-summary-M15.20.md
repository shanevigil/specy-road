# M15.20 — zones-missing-what-acceptance-needs-flagged

## Summary

Plan-time checks compare each ready leaf's acceptance criteria to its touch zones. `orchestrate plan` and `grind-session --plan` emit one warning per affected leaf when **path candidates** (see module docstring) name existing uncovered paths or wholly new paths under an existing tracked directory / with a known suffix. Other slash prose is ignored. Warnings include a best-effort hint. Brief importer cap: 20 per zoned file.

**Fix round (grok, directories):** existence uses tracked blobs and directory prefixes.

**Design round (grok, prose slash):** one bounded candidate rule — backticks, or bare tokens under a tracked top-level directory name or with a fixed suffix list; `new file outside zones` only when the candidate has a suffix or its parent directory already contains tracked files. False negatives accepted and documented.

## Touch zones (confirmed)

- `specy_road/zone_coverage.py`
- `specy_road/orchestrate_plan.py`
- `specy_road/bundled_scripts/brief_call_sites.py`
- `specy_road/bundled_scripts/orchestrate_cli.py`
- `specy_road/bundled_scripts/session_plan.py`
- `specy_road/bundled_scripts/session_plan_git.py`
- `specy_road/bundled_scripts/session_plan_render.py`
- `tests/`

`specy_road/orchestrate_assign.Assignment.warnings` — post–M15.11 split.

## Acceptance

- **A1:** Plan-time warnings; existing dirs/files list by path; new paths grouped once as `new file outside zones`; prose like `input/output` not warned.
- **A2:** `IMPORTER_CAP = 20`; `test_two_hundred_importers_list_twenty_then_count`.

## Probes

- **`_path_candidate` / `_shape_ok` (prose-slash class):** sole gate before zone/existence checks; verified `input/output`, `read/write`, `M12/M13`, URLs produce no labels.
- **`_tokens`:** backtick vs bare slash regex paths; bare `docs/existing.md` and `docs/contracts` still candidates when top-level `docs` is tracked; lone `docs/` prose without backticks is not extracted (regex limit) — documented false negative.
- **`_report_as_new`:** only suffix or parent-dir-exists paths add `NEW_OUTSIDE`; backtick `input/output` with no suffix and no tracked `input/` parent stays silent.
- **`_exists`:** unchanged directory-prefix behaviour for listed existing dirs (`docs`, `docs/api`, `docs/contracts`).
- **`leaf_zone_coverage_warning`:** hint text matches module docstring rule.
- **`zone_coverage_warnings` / orchestrate / grind `--plan`:** wiring unchanged; CLI tests updated for hint suffix only.
- **`_tracked_paths` None:** still returns no warnings.

## Added

- `specy_road/zone_coverage.py`: bounded candidate rule, `_label_for_candidate`, `BEST_EFFORT_HINT`, directory-aware `_exists`.
- `Assignment.warnings` in `orchestrate_assign.py`.
- `SessionPlan.zone_coverage`.
- `tests/test_zone_coverage.py`: prose-slash ignores, path-candidate parametrization, mixed-path fixture, CLI checks.
- `tests/test_brief_call_sites.py::test_two_hundred_importers_list_twenty_then_count`.
- none (mocks)
