# Implementation summary: M11.11 `one-readiness-rule`

## What changed

- **A1, one readiness rule.** `orchestrate plan` (`specy_road/orchestrate_plan.py`) now gets its batches
  from `session_plan_git.gather_session_plan`, the function `grind-session --plan` already uses, instead of calling the bare
  `compute_session_plan`. Before this change it applied only `do_next_available._available`. Like pickup, it
  now also drops unauthored leaves (`planning_sheet_bootstrap.placeholder_sheet`, via `unauthored_leaves`)
  and leaves already Complete on an unmerged `feature/rm-*` tip (`finished_unmerged_ids`). It also follows
  `prefer_agentic` from `git-workflow.yaml`. All three commands now run the same steps:
  `_available` → finished-unmerged filter → `placeholder_sheet`. `OrchestrationPlan` gains `unauthored`
  (in `--json` too), and the CLI prints `unauthored (not assigned; pickup skips them): …`.
- **A2, executor ranking.** `_pick_executor` sorts by `Candidate.executor_key`: roster `class` rank
  (`cheap` 0, untagged or other 1, `senior` 2), then list price (unknown last), then `billing_route` rank
  (a label containing `subscription`/`oauth` 0, unset 1, any other, such as `api_key`, 2), then executor score.
  A roster with no classes and no billing routes ranks exactly as before, by price and then score. The
  executor note appends `[class …, billing_route …]` when either is set.
- **Docs.** `docs/orchestration.md` (under "Choosing and prompting models") states the shared readiness rule and the ranking.

## Touch zones (confirmed)

Changed: `specy_road/orchestrate_plan.py`, `specy_road/bundled_scripts/orchestrate_cli.py`,
`docs/orchestration.md`, `tests/test_orchestrate_plan.py`, `tests/test_one_readiness_rule.py`,
`tests/unauthored_repo_helpers.py` (new), `tests/test_unauthored_leaf_guard.py` (helpers moved out).
Not changed: `session_plan.py` and `do_next_available.py`. Pickup and `grind-session --plan` already
shared the rule, so only `orchestrate plan` had diverged.

Follow-up outside the touch zones: the `Cost` bullet in `docs/orchestration-models.md`
(§ "Planning assignments") still says only "the cheapest list price wins". It should cite the class and
billing order now described in `docs/orchestration.md`.

Design choice for review: `class` ranks **before** price, not only when price is unknown. In the field
case, the senior model had a profile price and the cheaper classes had none. Any order that puts known
prices first keeps choosing that one model. The `cheap`/`senior` tags are the roster author's own
statement, and the schema already names them as examples.

## Verification

- `pytest tests/test_orchestrate_plan.py tests/test_one_readiness_rule.py tests/test_unauthored_leaf_guard.py tests/test_session_plan.py tests/test_session_plan_git.py tests/test_grind_session.py tests/test_do_next_queue.py`: 93 passed.
- The new agreement test fails against the base `orchestrate_plan.py` (`['M2','M3'] == ['M1','M2','M3']`).
- `specy-road file-limits`: OK.
- Full `pytest`: 2963 passed, 2 skipped (before the review fix below).

## Review fix (gpt-6.1-sol, E1)

`tests/test_one_readiness_rule.py` imported `_pick`, `_plan` and `_repo` from another test module. Those helpers, with `FILLED`, `_node`, `_git` and `_Picked`, now live in `tests/unauthored_repo_helpers.py` as `pick_leaf`, `plan_json`, `unauthored_repo`, `FILLED`, `leaf_node`, `git` and `Picked`. Both test modules import them from there. They were moved and renamed only, and every assertion is unchanged (the guard file still has 18 tests).

- `pytest tests/test_unauthored_leaf_guard.py tests/test_one_readiness_rule.py tests/test_orchestrate_plan.py`: 35 passed.
- `python scripts/check_test_private_imports.py`: exit 0, 0 new.
- `specy-road file-limits`: OK.

## Added

- `orchestrate_plan.CLASS_RANK`, `FLAT_RATE_ROUTES`: the class and billing orders, defined once and documented.
- `Candidate.class_rank`, `Candidate.billing_rank`, `Candidate.executor_key`: the A2 sort key.
- `OrchestrationPlan.unauthored` (+ `to_dict` key): lets the plan say which leaves it left out because pickup skips them.
- `orchestrate_cli.render` branch for `unauthored`: prints those leaves so a coordinator sees why they are missing.
- Executor note suffix `[class …, billing_route …]`: shows why a model was chosen when price is unknown.
- `tests/test_one_readiness_rule.py::test_pickup_grind_plan_and_orchestrate_plan_agree` (A1/A3): the three commands agree on one fixture.
- `tests/test_one_readiness_rule.py::test_orchestrate_plan_names_the_leaves_pickup_skips` (A1): CLI text and JSON.
- `tests/test_orchestrate_plan.py::test_cheap_class_beats_a_priced_senior_and_billing_breaks_the_tie` (A2/A3): the field roster shape.
- `tests/test_orchestrate_plan.py::test_senior_eligibility_still_gets_the_senior_class` (A2): eligibility still overrides the ranking.
- `tests/test_orchestrate_plan.py::test_executor_order_class_then_price_then_billing` (A2): unit test of the full order.
- `tests/unauthored_repo_helpers.py`: shared, public-named home for the unauthored-repo fixture and the pickup and `--plan` drivers (review E1). It moves existing helpers and adds no new logic.
- Mocks: none new. The agreement test reuses `pick_leaf`'s existing monkeypatches, which moved with it.
