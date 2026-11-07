# Implementation summary: M22.2 (move-rewrites-sheet-zones)

## What changed

- **A1, the move.** `stage_id_rewrite` (`roadmap_move_node.py`) now computes the sheet moves
  (`plan_planning_artifact_moves(scope)`) before rewriting zones, builds an old -> new sheet-path map in both forms with
  `sheet_path_map` (`roadmap_id_rewrite_staging.py`: `planning/<sheet>` and, when `project_prefix(root)` is non-empty,
  `<prefix>planning/<sheet>`), and passes it to `_rewrite_touch_zones` for the scope nodes and to `_stage_registry_ids`
  for the claims it already rewrites. A zone that equals a map key is replaced whole; every other zone keeps the
  existing whole-id-segment rewrite (`docs/M1.2.2/` -> `docs/M2.5/` still works). Everything stays in the same
  `AtomicWritePlan`. All callers (move-node, indent, outdent, group-nodes, the PM GUI move/indent/outdent/group/reorder)
  go through `stage_id_rewrite`, so their shapes are unchanged.
- **A2, the notice.** `notice_stale_sheet_zones` (`validate_touch_zones.py`), called from `run_validation` next to the
  existing zone checks, prints one stdout line per literal (non-glob) zone, on any node of any status, that names a
  `.md` directly under `planning/` in either form and does not exist in the working tree. When the file name ends in
  a live node's `_<node_key>.md`, the line names that node's current `planning_dir` (in the zone's form). stdout, so
  `--strict` does not count it. Existing zone diagnostics are untouched (an In Progress node still gets the stderr
  match-nothing warning for the same zone, as before).
- **A4.** `docs/roadmap-authoring.md` (move-node rewrite list, `touch_zones` row); CHANGELOG `[Unreleased]` Fixed entry.

Touch zones: the listed zones plus `tests/move_node_helpers.py`, which the coordinator added on WIP (`91703416`). My
own edit of the roadmap chunk and registry for that (`4d2e5083`) was reverted in `1b690e55` before merging WIP: this
branch changes no roadmap or registry file.
No golden/parity file changed (A6 not triggered). `specy-road file-limits` passes.

## Fix round 1 (review gpt-5.6-sol-high at a357b7b8)

- **Class: a zone readable in both forms** (a project directory itself named `planning`, so the checkout prefix is
  `planning/`). `_sheet_rel` stripped the prefix first, so the project-form zone `planning/missing.md` became
  `missing.md` and was never noticed. Fixed as one rule: the zone is read as project-relative first and only when that
  reading is no sheet path is the checkout prefix stripped; `_sheet_rel` now returns the form it matched, which the
  hint reuses (the old `zone != rel` comparison is gone). Docstring states the rule.
- **Class: duplicated test setup.** The two identical `_git` helpers became one public `git` in
  `tests/move_node_helpers.py`, imported by both test files.
- Merged `origin/WIP/improvements-0-3-1` first (no conflicts).

## Probes

- `_sheet_rel`, project at `<tmp>/planning`: `planning/gone.md` and `planning/planning/gone.md` noticed, both existing forms quiet (new regression test; fails on the previous `_sheet_rel`).
- `_sheet_rel` with an empty prefix (project at git root): the readings collapse to one (`dict.fromkeys`), behaviour unchanged; existing table test passes.
- Move side, same class: `sheet_path_map` keys for prefix `planning/` are `planning/<f>` (one slash) and `planning/planning/<f>` (two), disjoint; a direct `_rewrite_touch_zones` probe rewrote both forms and `docs/M1/` correctly. Lookup is exact, no prefix stripping anywhere else in the change.
- Hint form: taken from the matched reading, so a checkout-form zone gets a checkout-form hint (table test asserts both).
- Other duplicated git helpers added by this leaf: none left (grep for the helper body in tests/: only `move_node_helpers.git` from this leaf).
- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK.

## Verification

- `pytest -q tests/test_move_node_subtree.py tests/test_validate_touch_zones.py`: pass.
- Full suite `pytest -q -n 4`: 6199 passed.
- Red/green: with the package changes reverted, the new move test fails (zones not rewritten) and the validate test
  module fails to import `notice_stale_sheet_zones`.

## Added

### Helpers / branches / guards
- `sheet_path_map` (roadmap_id_rewrite_staging.py): old -> new sheet path in project and checkout form, from the sheet moves (A1).
- `_rewrite_zone` (roadmap_id_rewrite_staging.py): exact sheet-path match first, else the existing segment rewrite (A1, segment rewrite preserved).
- `sheets` parameter on `_rewrite_touch_zones` and `_stage_registry_ids`; early return in `_stage_registry_ids` now `not (renamed or sheets)` so a sheet-only rename still reaches claims (A1).
- `notice_stale_sheet_zones`, `_sheet_rel` (project form first, then checkout form; returns the matched form), `_sheet_exists`, `_SHEET_KEY` (validate_touch_zones.py): the stale-sheet stdout notice, the either-form planning-path test, a cannot-tell-reads-as-present existence check, and the node_key match for the hint (A2).
- Call in `run_validation` (validate_roadmap_checks.py), with the git root computed once for both zone checks (A2).

### Mocks
- none

### Tests
- `test_a_move_rewrites_zones_naming_the_moved_sheet_in_both_forms` (test_move_node_subtree.py): own-sheet zones in both forms plus `docs/<old id>/` on the node and its claim are rewritten, and validate shows no stale-sheet notice before and after `git add` (A3).
- `test_a_zone_naming_a_missing_planning_sheet_gets_a_stdout_notice` (test_validate_touch_zones.py), parametrized over Not Started/In Progress/Complete x staged/unstaged: only the absent literal sheet (both forms) is noticed, never an existing sheet or a `planning/*.md` glob; nothing on stderr about it; `--strict` exits 0 where no pre-existing warning applies (A3).
- `test_a_not_started_missing_non_sheet_zone_gets_no_new_notice` (test_validate_touch_zones.py): no new notice and empty stderr for a Not Started non-sheet zone (A3).
- `git` helper in `tests/move_node_helpers.py` (fix round 1, replaces two identical `_git` copies): git setup for the staged/unstaged cases.
- `test_a_project_directory_named_planning_reads_a_zone_as_project_form_first` (test_validate_touch_zones.py, fix round 1): regression for the both-forms reading rule.
