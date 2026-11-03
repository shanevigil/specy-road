# Implementation summary: M11.46 — Placeholder leaves neither fail validate --strict nor pad briefs

Branch `feature/rm-placeholder-leaves-strict-brief`, merged with `origin/WIP/improvements-0-3-1` at `630f55d7` (which added `generate_brief.py` and `validate_roadmap_checks.py` to the touch zones). Implementation commit `1ae7162a`.

## A1 — validate --strict and unauthored leaves

- An open leaf that pickup skips as unauthored (placeholder sheet, no `acceptance`) used to raise two stderr warnings: the unauthored block and, with the review gate on (the `init project` default), the missing-acceptance warning. Both counted toward `--strict`, so a fresh project plus one `add-node` leaf failed the starter M1.1's "`specy-road validate --strict` passes".
- Now, by default, `validate` prints the unauthored block as a `notice:` on stdout (the same convention as the Complete-scaffold and no-roster notices, which `--strict` does not count), and the missing-acceptance warning leaves out the leaves that block already names. Leaves with no acceptance and an authored sheet still warn.
- `--strict-authoring` turns on `--strict` and also keeps both blocks as stderr warnings, so they count again.
- Plumbing: `validate_at(..., strict_authoring=False)` → `run_validation(..., strict_authoring=False)` → the new `warn_authoring_gaps` helper. The edit in `validate_roadmap_checks.py` is one new function, one keyword argument and one call line replacing two, because M11.41 is changing that file in parallel.

## A2 — briefs and placeholder intents

- When a dependency's `## Intent` (section 6) or an ancestor's `## Intent` (section 3) is still scaffold-planning's template body or contains brainstorm promote's `PROMOTE_PLACEHOLDER` line, the brief prints one line instead: ``_`<id>` (<title>): its planning sheet is not written yet._``.
- Detection reuses `planning_sheet_bootstrap.PROMOTE_PLACEHOLDER` and `_scaffold_bodies()` (already imported the same way by `planning_scaffold_check`) and matches on collapsed whitespace, as `placeholder_sheet` does.
- For an ancestor, only the `## Intent` body is replaced. The ancestor's other sections are still inlined, as A2 specifies. A dependency still contributes only its Intent.
- Gate dependencies, whose first section is `## Why this gate exists`, are untouched.
- This node's own sheet is unchanged; A2 covers dependencies and ancestors only.

## Behaviour change to note

Without `--strict-authoring`, the unauthored block moved from stderr to stdout and starts with `notice:` instead of `warning:`. Existing tests that asserted the stderr warning now call `validate_at(..., strict_authoring=True)`, which is still the stderr-warning path, so their assertions are unchanged. One new test covers the default notice.

`test_validate_notes_complete_leaves_still_on_the_scaffold` read every stdout line starting with `  M`, which now picks up the open leaf M4's notice lines as well. It now reads only the lines after the Complete notice, and its expected list is unchanged.

## Final touch zones

Used: `specy_road/bundled_scripts/validate_roadmap.py`, `validate_roadmap_checks.py`, `brief_acceptance.py`, `brief_dependency_context.py`, `generate_brief.py`, `tests/`, `docs/roadmap-authoring.md`.

Not needed: `specy_road/templates/project/roadmap/phases/M1.json` and the M1.1 planning template. The starter's stated check now passes as written. No new module was needed; `specy-road file-limits` passes. `generate_brief.py` is 427 lines, under its 450 override. `validate_roadmap.py` is 397 and `docs/roadmap-authoring.md` is 400, both against the 400 cap, so the doc note extends an existing paragraph.

`suggested_prompts/` needs no change: none of the prompts describes `--strict` or unauthored leaves.

## Verification

- `python -m pytest -q tests/test_brief_placeholder_intent.py tests/test_validate_strict.py tests/test_unauthored_leaf_guard.py tests/test_validate_acceptance_coverage.py`: 40 passed.
- Broader regression across 18 test files that exercise validate, brief, init and promote (`test_generate_brief`, `test_brief_dependency_context`, `test_validate_roadmap`, `test_one_readiness_rule`, `test_init_project`, `test_brainstorm_*`, `test_project_layouts` and others): 283 passed.
- `specy-road file-limits`: OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0, and it left no `.specyrd/cache` behind.

## Added

### Helpers
- `brief_dependency_context.is_placeholder_intent`: decides whether an `## Intent` body is still scaffold-planning's or brainstorm promote's placeholder, reusing `planning_sheet_bootstrap`'s detectors.
- `brief_dependency_context.unwritten_sheet_line`: the single line that names the node and says its sheet is not written yet (A2).
- `brief_dependency_context.without_placeholder_intent`: replaces only the `## Intent` body of a whole inlined sheet; used for ancestors.
- `generate_brief._sheet_owners`: maps a normalised `planning_dir` to its ancestor node, so the inlined ancestor sheet can name that node.
- `validate_roadmap_checks.warn_authoring_gaps`: a new helper that pairs the missing-acceptance warning with the unauthored block and applies the A1 split, instead of reshaping `run_validation`, because M11.41 edits it in parallel.

### Branches and guards
- `brief_acceptance.warn_acceptance_missing(..., skip=)`: leaves out leaves the unauthored notice already names, so `--strict` does not count them through the missing-acceptance warning.
- `brief_acceptance.warn_unauthored(..., as_notice=)`: prints the block as a stdout `notice:` that `--strict` does not count.
- `validate_at` / `run_validation` `strict_authoring=` keyword: carries the flag from the CLI to the helper.
- `validate --strict-authoring` CLI flag: turns on `--strict` and keeps the unauthored block counted (A1).
- `_render_one_dep`: one-line branch for a non-gate dependency whose Intent is a placeholder (A2).
- `_inline_planning`: ancestor sheets go through `without_placeholder_intent` (A2).

### Mocks
- none

### Tests
- `test_validate_strict.test_a_placeholder_leaf_passes_the_starter_strict_check`: A1's required test. A fresh `init project` plus one `add-node` leaf passes `validate --strict` with empty stderr, and the test confirms M1.1's acceptance states that check.
- `test_validate_strict.test_strict_authoring_counts_the_placeholder_leaf_again`: A1. `--strict-authoring` exits 1, and both warnings are on stderr.
- `test_unauthored_leaf_guard.test_validate_without_strict_authoring_makes_the_block_a_stdout_notice`: A1's default path at the `validate_at` level.
- `test_brief_placeholder_intent.test_placeholder_intents_become_one_line_each`: A2's required test. Scaffold and promote placeholder text is absent from the brief for an ancestor and two dependencies, and each one gets its own line.
- `test_brief_placeholder_intent.test_written_intents_are_inlined_as_before`: control case. Authored intents are still inlined.
- `test_brief_placeholder_intent.test_is_placeholder_intent_matches_both_writers_only`: the detector matches both placeholders and does not match authored text.
- `test_brief_placeholder_intent.test_without_placeholder_intent_swaps_only_the_intent_body`: the other sections stay byte-identical, and an authored sheet comes back unchanged.
- `tests/_validate_err` helper: now passes `strict_authoring=True` so the existing warning-path tests keep asserting stderr.
