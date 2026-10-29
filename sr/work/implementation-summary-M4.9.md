# Implementation summary: M4.9 — Opt-in auto-pick ordering by execution milestone (`pick-ordering`)

Two workers built this. `b02aebc` is the coordinator's checkpoint of the first worker's
uncommitted work, saved when that worker hit its usage limit. The second worker
(`claude-opus-5.5`) reviewed that checkpoint, fixed a broken test fake, brought five
file-limit overruns back under the caps without changing behaviour, rewrote the new
tests to use public APIs (the private-import gate flagged six new references), and wrote
this summary.

## Review round 1 (Sol, at `2e421bb`)

- I merged `origin/WIP/improvements-0-3-1` (`7e87da1`) first. It includes the
  coordinator's fix to the touch zones (B1): the schema zone is now project-relative.
- **R1:** `session_plan.py` re-exports `session_plan_to_dict` from
  `session_plan_render`, and an `__all__` now lists the public names (`BlockedLeaf`,
  `SessionPlan`, `UnauthoredLeaf`, `Wave`, `compute_session_plan`,
  `session_plan_to_dict`). To avoid an import cycle, `session_plan_render` imports
  `SessionPlan` only under `TYPE_CHECKING` (it is used only in annotations, and the
  module has `from __future__ import annotations`). Both import orders work in a fresh
  interpreter and return the same function object. `grind_session.py` imports from
  `session_plan` again, as it did at the base.
- **T1:** the three pre-existing tests (`test_session_plan.py`,
  `test_unauthored_leaf_guard.py`, `test_archive_dependencies.py`) are back to
  importing `session_plan_to_dict` from `specy_road.bundled_scripts.session_plan`. They
  now match WIP exactly. The new `test_pick_ordering.py` keeps importing it from
  `session_plan_render`.

## Acceptance

- **A1** — `do-next-available-task --prefer-agentic` (or `prefer_agentic_pick_order: true` in
  `roadmap/git-workflow.yaml`) keeps the existing tiers (Blocked, MR-rejected, the rest)
  and orders the leaves inside each tier `Agentic-led`, `Mixed`, unset, `Human-led`, with
  outline order as the tiebreak. The flag beats the YAML setting
  (`--no-prefer-agentic` overrides `true`). Without the flag or the setting, the order is
  the same as before. Which leaves are eligible never changes. I read "within the same
  tree position" as "within the same selection tier", for two reasons: the planning
  sheet asks for "a stable secondary key" next to the tiering, and outline order is a
  total order, so a milestone key placed after it would never change anything.
- **A2** — `grind-session --plan` prints ``**Next auto-pick:** `<id>` (<execution
  milestone>)``, or `(no execution milestone)` when the leaf has none. When the
  reordering is on, it adds a note that ready leaves are ordered Agentic-led first.
  `--json` adds `ready_execution` (an execution milestone for each ready leaf) and
  `prefer_agentic`. The plan, the loop and `--step` all resolve the same setting, and
  `grind-session` passes an explicit `--prefer-agentic` / `--no-prefer-agentic` through
  to pickup, so `ready` still matches what pickup claims.

## Changes

- `do_next_available.py`: adds `EXECUTION_PICK_RANK` and `execution_pick_rank`. The
  `_sort_by_outline` key is now `(rank, outline index)`, and `_available(...,
  prefer_agentic=)` sorts each tier with it.
- `git_workflow_config.py`: adds `resolve_prefer_agentic(repo_root, cli=)`, which uses
  the CLI value first, then the YAML setting, then off.
- Both `git-workflow.schema.json` copies (template and `sr/`) gain the boolean key
  `prefer_agentic_pick_order`.
- `do_next_task_args.py` and `do_next_task.py`: add the
  `--prefer-agentic/--no-prefer-agentic` option (via `_add_pick_order_arg`, to keep
  `parse_do_next_task_args` within 80 lines) and update the help text. The setting is
  resolved after sync.
- `session_plan.py`: `compute_session_plan` / `_classify` take `prefer_agentic=`, and
  `SessionPlan` gains `ready_execution` and `prefer_agentic`.
- `session_plan_git.py`: `gather_session_plan(..., prefer_agentic=None)` falls back to
  the YAML setting the same way pickup does.
- `session_plan_render.py`: the Next auto-pick line now shows the execution milestone.
  **`session_plan_to_dict` moved here from `session_plan.py`** without changes. That
  module's docstring says it exists to keep `session_plan.py` under the line cap, and
  `session_plan.py` was at 411 lines (cap 400). `session_plan.py` re-exports it, so the
  public import path and its importers are unchanged (review round 1).
- `grind_session_args.py` and `grind_session.py`: add the option. **`_pickup_args` /
  `_finish_args` moved without changes into `grind_session_args.py`** as `pickup_args` /
  `finish_args`, because `grind_session.py` was at 408 lines (cap 400).
  `grind_session.py` imports them under their old private names, so `gs._pickup_args`
  (used by `grind_session_step.py` and the tests) still works.
- `grind_session_step.py`: `--step pickup` plans with the same setting.
- Docs: `docs/dev-workflow.md` (the selection-order paragraph and the must-know bullet)
  and `docs/grind-session.md` (the `ready` bullet, the Next auto-pick sentence, one line
  in the plan-vs-pickup bullet, and the JSON example). `grind-session.md` was already
  exactly at its 500-line overlay cap at the base, so I shortened the checkpoint's
  wording until the file was back to 500 lines.

## Touch zones (final)

Every path I changed is inside the listed zones. I did not edit
`tests/fixtures/specy_road_dogfood/schemas/`: that directory has no
`git-workflow.schema.json`.

## Follow-ups outside the touch zones (not done)

- `specy_road/orchestrate_plan.py` calls `compute_session_plan` without `prefer_agentic`.
  With the YAML setting on, `orchestrate plan` still orders its batches by outline.
- The template `specy_road/templates/project/roadmap/git-workflow.yaml` and
  `docs/git-workflow.md` list optional keys but do not mention
  `prefer_agentic_pick_order`.

## Verification

- `pytest` (full suite, before the private-import rewrite): 3 failed, 2265 passed, 2 skipped.
  - `test_lean_gates::test_private_imports_pass_on_committed_baseline`: caused by this leaf's tests; fixed by the rewrite.
  - `test_review_round6_evidence::test_committed_rename_into_the_zone_is_reported_on_both_sides` and `::test_rename_out_of_the_zone_keeps_the_source_inside_it`: they also fail at the base (`d132b5f`), because they reference `review_packet._changed`, which does not exist on this line. Not touched by this leaf.
- `pytest` on the affected test files after the rewrite (pick_ordering, lean_gates, grind_session*, session_plan*, unauthored_leaf_guard, archive_dependencies, claim_traps, do_next*, prerelease_s7, dependency_rollup_satisfaction): 296 passed, 2 skipped
- `ruff check specy_road tests`: All checks passed
- `specy-road file-limits`: OK (all five overruns at `b02aebc` are fixed; the base was clean)
- `specy-road validate` / `export --check --repo-root tests/fixtures/specy_road_dogfood`: OK
- Round 1, after merging WIP `7e87da1`:
  - Focused tests (the list above plus `test_orchestrate*`): 307 passed, 2 skipped.
  - `tests/test_review_round6_evidence.py`: 14 passed (fixed on WIP).
  - `scripts/check_test_private_imports.py`: 117 current, 118 baselined, 0 new. It also lists a stale baseline entry for `review_packet._changed`; that is WIP's round6 fix, not this leaf.
  - `specy-road file-limits`, `ruff check specy_road tests scripts`, and validate/export on the fixture: OK.

## Added

### Helpers
- `EXECUTION_PICK_RANK` / `execution_pick_rank` (`do_next_available.py`): one rank table for the opt-in order, with unset ranked between Mixed and Human-led.
- `resolve_prefer_agentic` (`git_workflow_config.py`): one place for the CLI > YAML > off precedence, shared by pickup and the plan.
- `_add_pick_order_arg` (`do_next_task_args.py`): keeps `parse_do_next_task_args` within the 80-line function cap.

### Branches / guards
- `_sort_by_outline` uses rank 0 for every leaf when `prefer_agentic` is false, so the default order cannot change.
- `pickup_args` emits `--prefer-agentic` / `--no-prefer-agentic` only when the grind CLI set it (`None` passes nothing, and pickup then reads the YAML setting itself).
- `_render_next_pick` falls back to `no execution milestone` when the leaf has none, and adds the order note only when `prefer_agentic` is on.

### Moves (no behaviour change)
- `session_plan_to_dict` moved from `session_plan.py` to `session_plan_render.py`, because of the 400-line file cap. `session_plan.py` re-exports it and lists it in `__all__`, so the public path still works (R1).
- `TYPE_CHECKING` guard on `session_plan_render`'s `SessionPlan` import: breaks the cycle that the re-export would otherwise create (R1).
- `_pickup_args` / `_finish_args` moved from `grind_session.py` to `grind_session_args.py` (re-imported under the old names), because of the 400-line file cap.

### Mocks
- `test_pickup_claims_by_the_resolved_setting`: patches only `do_next_task.ROOT`, as `test_claim_traps.py`'s `--local` pickup test does. Everything else is a real `--local` pickup on a throwaway git repo, so there are no new private references (`scripts/check_test_private_imports.py`: 0 new).
- `fake_gather` in `tests/test_grind_session.py` and `tests/test_grind_session_in_flight.py` now accepts `prefer_agentic=None`, matching the new `gather_plan` keyword.

### Tests (`tests/test_pick_ordering.py`)
- `_ready` helper: reads the pickup order through the public `compute_session_plan(...).ready` instead of the private `_available`.
- `_pickup_repo` helper: a two-leaf repo (`M1` Human-led before `M2` Agentic-led in outline order) on `dev` for real `--local` pickups.
- `test_default_order_is_outline_regardless_of_execution_milestone`: the default order is unchanged.
- `test_prefer_agentic_orders_agentic_mixed_unset_human_then_outline`: A1 order, with outline as the tiebreak.
- `test_prefer_agentic_keeps_the_blocked_tier_first`: tiers still come before the milestone order.
- `test_prefer_agentic_does_not_change_eligibility`: reordering only.
- `test_schema_accepts_prefer_agentic_pick_order`: the schema accepts a boolean and rejects other types.
- `test_resolve_prefer_agentic_cli_beats_yaml_beats_default`: precedence.
- `test_do_next_and_grind_parse_the_flag`: both CLIs parse the flag to None / True / False.
- `test_pickup_claims_by_the_resolved_setting` (4 cases): a real `--local` pickup claims `M1` by default, `M2` with `--prefer-agentic` or the YAML setting, and `M1` with `--no-prefer-agentic` over the YAML setting.
- `test_grind_passes_an_explicit_setting_through_to_pickup`: grind's pass-through.
- `test_plan_carries_execution_for_every_ready_leaf`: `ready_execution` is filled in, and `prefer_agentic` reaches the JSON.
- `test_plan_text_shows_execution_milestone_beside_next_auto_pick`: A2 text.
- `test_gather_session_plan_reads_the_yaml_default`: `--plan` with no flag follows the YAML setting.
