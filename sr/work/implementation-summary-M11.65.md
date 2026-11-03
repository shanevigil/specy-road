# Implementation summary — M11.65 `why-blocked-plan-holds`

## What changed

`specy-road why-blocked <ID>` now asks the session plan whether it holds a
pickable leaf behind another for sharing a touch zone. Before, `grind-session
--plan` could list a leaf under "Held for the next batch" while `why-blocked`
said only that it was not blocked.

- For a leaf `explain()` reports as `ready`, `why-blocked` loads the plan
  `grind-session --plan` prints without `--under` (`gather_session_plan`:
  unauthored leaves out, `prefer_agentic` from config, git-enriched) and looks
  the leaf up in `session_plan_render.zone_overlaps`, the function behind the
  plan's "Held for the next batch" section. The two commands therefore read one
  computation.
- Text output adds two lines when held: which leaf holds it and which zones
  overlap, then that pickup does **not** honour the hold
  (`do-next-available-task` and the `grind-session` loop claim `plan.ready[0]`
  and never read `parallel_batches`; confirmed in `grind_session._run_loop`,
  `grind_session_step._step_pickup`, and the existing
  `test_shared_file_path_moves_later_leaf_to_next_batch` assertion "pickup order
  is untouched").
- `--json` gains a `plan_hold` key: `{"waits_for", "zones", "pickup_honours"}`
  or `null` (always present; `null` for non-ready states, where the plan is not
  computed).
- Exit codes are unchanged: a held leaf still exits 0, because pickup would
  still claim it. The `--help` description says so.

A scoped plan (`--plan --under X`) can hold fewer leaves than the unscoped one
`why-blocked` reads, since a holder outside the scope is not in it; noted in
the `plan_hold` docstring.

## Touch zones (final)

- `specy_road/bundled_scripts/roadmap_query_cli.py` — changed.
- `tests/` — new `tests/test_why_blocked_plan_holds.py`.
- `specy_road/bundled_scripts/session_plan.py` — listed, **not** changed: the
  hold computation already exists as `zone_overlaps` in `session_plan_render.py`
  and is imported, not duplicated.

## Verification

- `python -m pytest -q tests/test_why_blocked_plan_holds.py tests/test_cli_query_commands.py tests/test_roadmap_explain.py tests/test_session_plan_touch_zones.py` — 40 passed.
- `specy-road file-limits` — OK (`roadmap_query_cli.py` is 212 lines).
- Red-green: with `roadmap_query_cli.py` reverted to the base, all 5 new tests fail; restored, they pass.
- `python -m pytest -n auto -q -p no:cacheprovider` — full suite: 3324 passed, 2 skipped.

## Added

- `roadmap_query_cli.PICKUP_HONOURS_ZONE_HOLDS` — one named statement that pickup ignores zone holds, so the text, JSON and exit-code choice share it.
- `roadmap_query_cli.plan_hold(root, node_id)` — the hold `--plan` puts on one leaf, read from `gather_session_plan` + `zone_overlaps` so the two commands cannot disagree.
- `roadmap_query_cli._render_hold` — the two text lines naming holder, zones and whether pickup honours it.
- Branch in `cmd_why_blocked`: compute the hold only when `exp.state == "ready"` — other states are already explained and need no git/plan work.
- `hold` parameter on `_render_explanation` (default `None`) — appends the hold lines; existing callers unchanged.
- `plan_hold` key in `--json` output — machine-readable form of the same answer.
- `tests/test_why_blocked_plan_holds.py` `repo` fixture — a git repo (via `plan_repo`) with a zone-held leaf, a dependency-blocked leaf and a free leaf.
- `test_zone_hold_names_the_holder_and_zones_and_says_pickup_ignores_it` — A1 zone hold, text output and exit 0, and that the plan itself holds the leaf.
- `test_zone_hold_in_json` — A1 zone hold in JSON, matched against `zone_overlaps`.
- `test_dependency_block_reports_the_chain_and_no_hold` — A1 dependency block: exit 1, chain, no hold.
- `test_free_leaf_has_no_hold` — A1 free leaf: exit 0, no hold lines, `plan_hold` null.
- `test_the_holder_itself_is_not_held` — the leaf doing the holding is not reported as held.
- Mocks: none.
