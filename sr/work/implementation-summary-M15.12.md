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
- **Rework (R1, `gpt-6.1-sol`).** The registry path no longer has its own raw-string
  clash test (superseded by fix round 1, below): `_counted_clash` uses `shared_zones.paths_overlap`, the plan's normalized
  rule, so `planning/same.md` vs `./planning/same.md` warns in validate (scoped and
  unscoped) exactly where the plan splits. `_touch_zones_clash` is removed; the
  broad-summary helpers (`_is_broad_touch_zone`, `_in_broad_zone_tree`, the equality
  check in `_clash_suppressed_by_broad_summary`, the summary key in
  `_broad_zone_summaries`) compare normalized paths, so a broad zone spelled `./src/`
  and `src/` is summarized once as `'src/'`. Plain-spelling input gives the same
  warnings as before (existing `test_registry_overlap_warnings.py` unchanged, passing).

## Probes

Class of R1: two spellings of one path (`./` prefix, trailing `/`, surrounding
whitespace) compared as raw strings in an overlap check.

- `validate_registry_overlap._counted_clash` (scoped and unscoped paths): was raw; now `paths_overlap`. Regression test covers both paths plus the plan split. Superseded in fix round 1: now `zones_overlap`.
- `_in_broad_zone_tree` / `_clash_suppressed_by_broad_summary` / `_claims_in_broad_zone_tree`: were raw; now normalized (else `./src/a.py` would escape a `src/` summary).
- `_broad_zone_summaries` key: was raw (`./src/` and `src/` two keys, no summary); now normalized; test `test_registry_broad_zone_spelled_two_ways_is_summarized_once`.
- `_is_broad_touch_zone`: now strips whitespace before the trailing-`/` check.
- `shared_zones.shared_ignores` / `effective_overlap` / `ignored_shared_zones` and `session_plan_render.zone_clash`: already normalized via `norm_zone`; no change. (Fix round 1 folds these into `zones_overlap`.)
- Configured `grind.shared_zones` values (e.g. `./notes/`): matched through `norm_zone`; no change.
- Other `rstrip("/")` zone code in `specy_road/` (`touch_zone_tracked.py`, `validate_touch_zones.py`): tracked-file checks, not overlap; out of this class.
- Red-green: both new tests fail against the previous `validate_registry_overlap.py` (exit 1), pass with the fix.

## Fix round 1: one overlap rule

Merged `origin/WIP/improvements-0-3-1` first (`d643aebb`). Class: the plan and
validate each had their own copy of the overlap comparison, so any spelling one
normalized and the other did not made them disagree. Removed by construction:

- `shared_zones.zones_overlap(a, b, shared)` is the only overlap comparison. It
  normalizes both zones with `norm_zone` (POSIX `normpath`: strips spaces and `./`,
  collapses `//` and `x/../`; keeps the trailing `/` of a directory zone), checks
  containment with `in_zone_tree`, then applies the shared-zone rule (`is_shared_zone`).
- Plan: `effective_overlap` (used by `session_plan_render.zone_clash`) calls it.
  Validate: `_first_independent_pair_clash` and `_first_touch_zone_clash` call it.
- Deleted: `shared_zones.paths_overlap`, `shared_zones.shared_ignores`,
  `validate_registry_overlap._counted_clash` and its local `_in_broad_zone_tree`
  (replaced by `shared_zones.in_zone_tree`). The broad-summary key is `norm_zone(zone)`.
- `test_plan_and_validate_apply_one_overlap_rule` feeds each pair to the plan,
  unscoped validate and scoped validate, and asserts all three agree with the expected answer.

Pairs checked (a, b → overlap), default shared zones `planning/`, `shared/`; all three callers agree on each:

- `src/a.py` vs `./src/a.py` → yes
- `src/a.py` vs `src/a.py` → yes
- `src/` vs `src` → yes
- `src/` vs `./src/` → yes
- `src/` vs `src/a.py` → yes
- `./src/` vs `src/a/b.py` → yes
- `src/a/../b.py` vs `src/b.py` → yes
- `src//b.py` vs `src/b.py` → yes
- ` src/b.py ` vs `src/b.py` → yes
- `src/a.py` vs `src/b.py` → no
- `src-old/x.py` vs `src/` → no
- `planning/` vs `planning/x.md` → no (shared)
- `./planning/` vs `planning/x.md` → no (shared)
- `planning` vs `planning/x.md` → no (shared, no trailing slash)
- `planning/` vs `planning/` → no (shared)
- `shared/` vs `./shared//` → no (shared)
- `planning/x.md` vs `./planning/x.md` → yes
- `planning/x.md` vs `planning//x.md` → yes
- `planning/a/../x.md` vs `planning/x.md` → yes
- `planning/x.md` vs `planning/y.md` → no
- `shared/api/` vs `shared/api/x.md` → yes (subdirectory under a shared zone)
- `shared/api/` vs `shared/web/` → no

Red-green: against the previous tip (`5159ce9f`) 4 of these pairs fail (the `//` and
`x/../` ones); against the reviewed commit `70f35d8d`, 11 tests in the file fail.

## Fix round 2: aliased shared zones reported once

Merged `origin/WIP/improvements-0-3-1` first. Class: a list of zones taken from
configuration and reported or counted without going through the normaliser, so two
spellings of one directory showed up twice.

- `shared_zones.unique_zones` collapses spellings by `zone_key` (the key
  `zones_overlap` compares by), keeping the first configured spelling.
  `resolve_shared_zones` returns the deduplicated set, and `ignored_shared_zones`
  dedups again for a set passed straight to `compute_session_plan`.
- Test `test_aliased_shared_zone_is_reported_once_in_text_and_json`: configured
  `[notes/team/, ./notes/team/]`, `[notes/team/, notes//team/, " notes/team "]`,
  `[notes/team/, notes/x/../team/]`. For each, both the config-resolved set and the raw
  set give one `notes/team/` in the `shared_zones_ignored` JSON and in the one text line.
  3 of these fail against the previous tip's `shared_zones.py`.

Probes (grep for raw zone strings in the zoned modules):
- `shared_zones.is_shared_zone`, `zones_overlap`, `in_zone_tree`, `ignored_shared_zones` comparisons: all through `zone_key`; ok.
- `shared_zones.ignored_shared_zones` iteration over `shared`: was raw (the finding); now `unique_zones`.
- `shared_zones.resolve_shared_zones` result: was raw; now `unique_zones`.
- `validate_registry_overlap._is_broad_touch_zone`: was `zone.strip().endswith("/")`; now `norm_zone(zone).endswith("/")`.
- `validate_registry_overlap` summary keys and `summarized_broad`: already `norm_zone`; ok. Same-file check in `_clash_suppressed_by_broad_summary`: `norm_zone` equality; ok.
- `validate_registry_overlap` `sorted(touch_zones)`: only orders the loop, compares nothing; ok.
- `validate_registry_overlap._claims_in_broad_zone_tree`: a rename in fix round 1 had mangled it to `_claimsin_zone_tree`; now `_claims_in_zone_tree`.
- `session_plan_render` `zone_clash` / `zone_overlaps` / `shared_zones_ignored`: delegate to `shared_zones`; no raw comparisons.
- `session_plan.py` `touch_zones` dict and the `shared_zones` field: only stored and passed on, never compared (the file is at its line cap); ok.
- `session_plan_git.py`: passes `plan.shared_zones` on; no zone comparisons.

## Verification

- `python -m pytest -q -n 4 tests/test_shared_zones.py tests/test_registry_overlap_warnings.py tests/test_session_plan_touch_zones.py tests/test_session_plan.py tests/test_session_plan_git.py tests/test_why_blocked_plan_holds.py tests/test_orchestrate_plan.py tests/test_grind_session.py tests/test_validate_roadmap.py tests/test_refresh_schemas.py tests/test_schema_revision.py tests/test_pick_ordering.py tests/test_grind_session_in_flight.py tests/test_grind_session_step.py tests/test_unauthored_leaf_guard.py`: 238 passed (fix round 2)
- `specy-road file-limits`: OK. `ruff check` on the changed files: clean. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.

## Added

- `shared_zones.DEFAULT_SHARED_ZONES`: the default set the acceptance names (`planning/`, `shared/`).
- `shared_zones.norm_zone`: moved from `session_plan_render._norm_zone`; fix round 1 makes it POSIX-normalize (`//`, `x/../`) and keep a directory's trailing `/`.
- `shared_zones.zone_key` / `in_zone_tree` / `is_shared_zone` (fix round 1): the pieces of the one rule; `in_zone_tree` also replaces the registry's own `_in_broad_zone_tree`.
- `shared_zones.zones_overlap` (fix round 1): the single overlap comparison both the plan and validate call.
- `shared_zones.resolve_shared_zones`: reads `grind.shared_zones`; default on missing or unreadable config.
- `shared_zones.effective_overlap`: first overlapping pair after the shared rule; used by `zone_clash`.
- `shared_zones.ignored_shared_zones`: which shared zones the split actually ignored, for A3's output.
- `session_plan_render.shared_zones_ignored` + JSON key `shared_zones_ignored` + one text line in `_render_zone_overlaps`: A3 (plan names ignored zones once).
- `shared` parameter on `zone_clash` / `split_on_zone_overlap` / `_parallel_batches`, `shared_zones` kwarg on `compute_session_plan` and field on `SessionPlan`: carry the configured set; `session_plan_git` rebuilds batches with it.
- Registry clash checks call `shared_zones.zones_overlap` (fix round 1; the raw `_touch_zones_clash` and the interim `_counted_clash` are removed) and `shared` parameter on `touch_zone_overlap` / helpers, `repo_root` on `warn_registry_touch_zone_overlap`: A2 (validate applies the same rule from config).
- Guard in `_broad_zone_summaries`: skip the "shared zone" summary line for configured shared zones.
- `norm_zone` in `_in_broad_zone_tree`, `_clash_suppressed_by_broad_summary`, `_broad_zone_summaries` key, `.strip()` in `_is_broad_touch_zone`: R1 class (one path spelled two ways) in the summary path.
- Schema `grind.shared_zones` (object, `additionalProperties: false`): A1 schema-check.
- Mocks: none.
- Tests (`tests/test_shared_zones.py`): 30-leaf single batch and one-time ignored-zones line; same planning sheet kept apart; code overlap still splits next to shared zones; `shared_zones=()` restores the plain rule; config default/override/empty/schema rejection; registry warning ignores shared zones (unscoped and scoped); registry warning keeps the same planning sheet; validate reads configured zones via `repo_root`.
- Tests (rework, `tests/test_shared_zones.py`): `test_same_file_spelled_two_ways_warns_scoped_and_unscoped_and_splits` (R1: `planning/same.md` vs `./planning/same.md` warns once unscoped, once scoped, and the plan splits); `test_registry_broad_zone_spelled_two_ways_is_summarized_once` (summary key normalized).
- Tests (fix round 1, `tests/test_shared_zones.py`): `test_plan_and_validate_apply_one_overlap_rule`, parametrized over 22 zone pairs; the plan, unscoped validate and scoped validate must all agree.
- `shared_zones.unique_zones` (fix round 2): dedups a zone list by `zone_key`, keeping the first spelling, so an aliased shared zone is reported once.
- Tests (fix round 2): `test_aliased_shared_zone_is_reported_once_in_text_and_json`, 3 alias configurations, through the public plan text and JSON.
