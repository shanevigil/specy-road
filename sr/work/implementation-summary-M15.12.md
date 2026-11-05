# Implementation summary — M15.12 (shared-doc-zones-do-not-serialize-batches)

## What changed

- **A1 — rule and config.** New `specy_road/shared_zones.py`. If either of two
  overlapping touch zones is itself a configured shared zone (default
  `planning/`, `shared/`), the overlap does not count. Two leaves naming the same file (or subdirectory)
  under a shared zone still overlap. The set comes from `grind.shared_zones` in
  `roadmap/git-workflow.yaml`, added to `git-workflow.schema.json` as an object with
  `additionalProperties: false` and a unique string array; `[]` turns the rule off.
  An unreadable config falls back to the default, as the other git-workflow flags do.
- **Plan.** `session_plan_render.zone_clash` / `split_on_zone_overlap` / `zone_overlaps`
  take the shared set (`zone_clash` now delegates to `shared_zones.effective_overlap`;
  the normalization moved with it). `session_plan.py` (at 400 lines, the cap) only
  gained the `shared_zones` kwarg / field and call-site arguments. `session_plan_git`
  resolves the set from the repo root in `gather_session_plan` and reuses
  `plan.shared_zones` when it rebuilds the batches, so `grind-session --plan` and
  `orchestrate plan` both use the config.
- **A2 — validate.** `validate_registry_overlap.touch_zone_overlap` drops clashes
  through a shared zone (scoped and unscoped paths) and no longer prints the
  "shared zone 'planning/'" summary for configured shared zones.
  `validate_roadmap_checks` passes `repo_root=r` so validate reads the config.
- **A3 — output.** The text plan prints one line naming the shared zones the split
  ignored (only zones where two batched leaves met); JSON gains
  `shared_zones_ignored` (in `PLAN_FIELDS`). `docs/grind-session.md` changes by
  rewording one bullet and the JSON example, so it stays at 500 lines (its override).

Final touch zones (as widened by the coordinator, all used):
`specy_road/bundled_scripts/session_plan_render.py`, `specy_road/bundled_scripts/session_plan.py`,
`specy_road/shared_zones.py`, `specy_road/bundled_scripts/validate_registry_overlap.py`,
`docs/grind-session.md`, `tests/`, `specy_road/templates/project/schemas/git-workflow.schema.json`,
`specy_road/bundled_scripts/session_plan_git.py`, `specy_road/bundled_scripts/validate_roadmap_checks.py`.

Notes for reviewers:
- `sr/schemas/git-workflow.schema.json` (the toolkit roadmap's copy) is not refreshed
  here; it is outside the zones and has its own refresh-schemas chore.
- On this repo's own `sr/` roadmap the ready leaves still serialize because nearly
  all of them name `tests/`. That overlap is real, not a shared-documentation zone.
- The registry path keeps its own raw-string clash test (`_touch_zones_clash`) and
  only adds the shared filter, so no existing registry warning changes except the
  shared-zone ones.

## Verification

- `python -m pytest -q -n 4 tests/test_shared_zones.py tests/test_session_plan_touch_zones.py tests/test_session_plan.py tests/test_session_plan_git.py tests/test_registry_overlap_warnings.py tests/test_why_blocked_plan_holds.py tests/test_orchestrate_plan.py tests/test_grind_session.py tests/test_refresh_schemas.py tests/test_schema_revision.py`: pass
- `specy-road file-limits`: OK. `ruff check` on the changed files: clean. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.

## Added

- `shared_zones.DEFAULT_SHARED_ZONES`: the default set the acceptance names (`planning/`, `shared/`).
- `shared_zones.norm_zone`: moved from `session_plan_render._norm_zone` so both callers normalize the same way.
- `shared_zones.resolve_shared_zones`: reads `grind.shared_zones`; default on missing or unreadable config.
- `shared_zones.paths_overlap`: the existing plan overlap rule (same path or directory prefix), moved out of `zone_clash`.
- `shared_zones.shared_ignores`: the A1 rule (either zone is itself a shared zone, so the overlap does not count).
- `shared_zones.effective_overlap`: first overlapping pair after the shared rule; used by `zone_clash`.
- `shared_zones.ignored_shared_zones`: which shared zones the split actually ignored, for A3's output.
- `session_plan_render.shared_zones_ignored` + JSON key `shared_zones_ignored` + one text line in `_render_zone_overlaps`: A3 (plan names ignored zones once).
- `shared` parameter on `zone_clash` / `split_on_zone_overlap` / `_parallel_batches`, `shared_zones` kwarg on `compute_session_plan` and field on `SessionPlan`: carry the configured set; `session_plan_git` rebuilds batches with it.
- `validate_registry_overlap._counted_clash` and `shared` parameter on `touch_zone_overlap` / helpers, `repo_root` on `warn_registry_touch_zone_overlap`: A2 (validate applies the same rule from config).
- Guard in `_broad_zone_summaries`: skip the "shared zone" summary line for configured shared zones.
- Schema `grind.shared_zones` (object, `additionalProperties: false`): A1 schema-check.
- Mocks: none.
- Tests (`tests/test_shared_zones.py`): 30-leaf single batch and one-time ignored-zones line; same planning sheet kept apart; code overlap still splits next to shared zones; `shared_zones=()` restores the plain rule; config default/override/empty/schema rejection; registry warning ignores shared zones (unscoped and scoped); registry warning keeps the same planning sheet; validate reads configured zones via `repo_root`.
