# Implementation summary: M11.15 — pickup-refuses-scaffold-sheet

## What changed

Pickup, `grind-session --plan`, and `orchestrate plan` now treat a leaf as not ready when its planning sheet still has scaffold-planning's or brainstorm promote's placeholder under `## Intent` or `## Approach`, even if the node has `acceptance`. Pickup prints `skipping <ID>: <sheet> still has … under ## <section>` and names `--allow-scaffold-planning` to opt back into warn-and-pick (finish still needs the same flag). Leaves with no `acceptance` and a placeholder sheet are unchanged: `--allow-unauthored` still opts those in. `validate` still warns only on the no-`acceptance` placeholder set (`planning_sheet_bootstrap.unauthored_leaves`).

Shared readiness lives in `planning_scaffold_check.pickup_unauthored_leaves`, re-exported as `do_next_available.unauthored_leaves` for session plan (`session_plan_git` imports that). Pickup filtering is in `do_next_task_leaf_guards.drop_unauthored` with separate flags for the two skip reasons.

## Acceptance

- **A1:** Pickup skips scaffold/promote placeholders under Intent or Approach with acceptance set; `--allow-scaffold-planning` warns and picks as before.
- **A2:** `grind-session --plan` / orchestrate plan list those leaves under `unauthored`; test covers acceptance plus scaffold `## Approach`.

## Touch zones (confirmed)

PM list plus files required for A2 wiring:

- `specy_road/planning_scaffold_check.py`
- `specy_road/bundled_scripts/do_next_available.py`
- `specy_road/bundled_scripts/do_next_task.py`
- `specy_road/bundled_scripts/do_next_task_args.py`
- `specy_road/bundled_scripts/do_next_task_leaf_guards.py`
- `specy_road/bundled_scripts/session_plan_git.py`
- `specy_road/bundled_scripts/session_plan_render.py`
- `docs/roadmap-authoring.md`
- `tests/test_unauthored_leaf_guard.py`
- `tests/test_one_readiness_rule.py`

## Added

- `pickup_unauthored_leaves` in `planning_scaffold_check.py` — id→reason map for pickup and session plan (placeholder without acceptance, or scaffold/promote with acceptance).
- `unauthored_leaves` re-export on `do_next_available.py` — single import alias so plan and docs cite one module.
- `_add_planning_sheet_pick_flags` in `do_next_task_args.py` — keeps `parse_do_next_task_args` under the function line limit while adding `--allow-scaffold-planning`.
- `--allow-scaffold-planning` on do-next-available-task — opt-in warn-and-pick for acceptance plus unwritten sheet; finish unchanged.
- Second branch in `drop_unauthored` — scaffold skip when `acceptance_ids` non-empty and flag off.
- `session_plan_git` import from `do_next_available.unauthored_leaves` — plan/orchestrate match pickup without changing validate's bootstrap helper.
- `gather_session_plan` keeps acceptance+scaffold in `unauthored` when only `--allow-unauthored` is set — matches `drop_unauthored` / grind-session help.
- `--plan` unauthored heading no longer says "no acceptance" or that `--allow-unauthored` picks those rows.
- Restored `do_next_task._write_brief(node, nodes)` — `_finalize_pickup` call site the pickup tests patch.
- `test_filled_sheet_or_acceptance_with_scaffold_still_skipped_at_pickup` — A1 default refuse.
- `test_allow_scaffold_planning_warns_and_picks` — A1 flag restores prior pickup behaviour.
- `test_plan_lists_scaffold_approach_with_acceptance_as_unauthored` — A2 plan JSON lists leaf with scaffold Approach and acceptance.
- `test_plan_allow_unauthored_keeps_acceptance_scaffold_not_ready` — `--plan --allow-unauthored` still lists leftover scaffold Approach with acceptance as unauthored.
