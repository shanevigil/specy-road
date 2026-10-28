# Implementation summary for M3.1

## Summary

An agent is no longer handed a leaf it has nothing to build from. A leaf is
**unauthored** when its node has no `acceptance` **and** its planning sheet still
has text the toolkit wrote itself: brainstorm promote's line ("Rewrite this
section once the slice is properly scoped.") under `## Intent`, or the
scaffold-planning template body under `## Intent` or `## Approach`. One helper,
`placeholder_sheet(root, node) -> str | None`, decides this and returns the
reason. Pickup, the session plan and validate all use it.

- **A1:** `do-next-available-task` drops unauthored leaves after sync (the sync
  may bring a written sheet) and prints `skipping <ID>: <reason>. Write the
  sheet or set acceptance (...), or pass --allow-unauthored ...` to stderr. If
  that empties the queue, the usual "No actionable leaf tasks" exit follows.
  `--allow-unauthored` restores the old behaviour.
- **A2:** `grind-session --plan` takes them out of `ready`/`parallel_batches`
  and lists them under a new `unauthored` bucket (`node_id`, `codename`,
  `reason`; `totals.unauthored` only when non-zero, like `finished_*`). The text
  plan shows them under "Not ready — placeholder planning sheet, no acceptance".
  They still get a wave, so their dependents stay in the layering.
  `--allow-unauthored` works on `--plan`, the loop and `--step pickup`, and is
  passed on to the `do-next-available-task` the loop runs.
- **A3:** `validate` prints one warning block that names every such open leaf
  (not Complete or Cancelled) with its reason. The block is capped at ten
  entries (the same `_WARN_CAP` as the acceptance warning), then shows "… and N
  more (specy-road validate --all lists every one)". `validate --all` lists all
  of them.
- **A4:** A leaf with a written sheet, or with `acceptance` set, is selected
  exactly as before. A missing or unreadable sheet is not reported here; other
  validators handle that. The dogfood fixture and the toolkit's `sr/` roadmap
  both have 0 unauthored leaves, so there are no false positives on real
  roadmaps.

No schema field was added. The detection depends only on strings the toolkit
writes: the template is read from `feature-sheet.md.template`, and promote's
line is now the `PROMOTE_PLACEHOLDER` constant that `brainstorm_promote` writes.

## Changes

Final touch-zone list: the original eight, plus the widened set from the
coordinator. Every changed path is inside it.

- `specy_road/bundled_scripts/planning_sheet_bootstrap.py`: `PROMOTE_PLACEHOLDER`,
  `placeholder_sheet`, `unauthored_leaves`, plus the private `_section_bodies` and `_scaffold_bodies`.
- `specy_road/bundled_scripts/brainstorm_promote.py`: writes `PROMOTE_PLACEHOLDER`
  instead of a literal copy of the same text.
- `specy_road/bundled_scripts/brief_acceptance.py`: `warn_unauthored` (one capped
  block, with `show_all`).
- `specy_road/bundled_scripts/validate_roadmap_checks.py` / `validate_roadmap.py`:
  `show_all` threaded through `run_validation` / `validate_at`; `--all` flag.
- `specy_road/bundled_scripts/do_next_task_leaf_guards.py`: `drop_unauthored`
  (the pickup guard).
- `specy_road/bundled_scripts/do_next_task.py` / `do_next_task_args.py`: guard
  after sync in `_resync_and_select`; `--allow-unauthored`; one paragraph added to `-h`.
- `specy_road/bundled_scripts/session_plan.py`: `UnauthoredLeaf`, an `unauthored`
  bucket/field/dict key, and an `unauthored=` parameter on `compute_session_plan`
  (kept pure: the caller reads the sheets).
- `specy_road/bundled_scripts/session_plan_git.py`: `gather_session_plan(...,
  allow_unauthored=False)` reads the sheets and passes the reasons in.
- `specy_road/bundled_scripts/session_plan_render.py`: "Not ready" section.
- `specy_road/bundled_scripts/grind_session.py` / `grind_session_args.py` /
  `grind_session_step.py`: `--allow-unauthored`, sent to the plan and to
  pickup. `grind_session.py` was at its 400-line cap, so the two boolean
  pass-through flags share one list comprehension instead of growing the file.
- `docs/grind-session.md` (the `unauthored` bucket plus a JSON example line; now
  exactly at its 500-line cap) and `docs/dev-workflow.md` (one paragraph under
  selection order).
- Tests: `tests/test_unauthored_leaf_guard.py` (new), stub signatures in
  `tests/test_grind_session.py`, `tests/test_grind_session_in_flight.py`,
  `tests/test_grind_session_step.py`.
- Review round 1 (gpt-5.6-sol-high, blocked `f491178`, A1–A4 pass):
  - This summary now sits at `sr/work/implementation-summary-M3.1.md`, the
    nested project's `work/`, and the git-root copy is gone, so review-packet and
    finish-this-task can find it and clean it up.
  - The `--allow-unauthored` step tests now check behaviour without pinning
    call history (`9deaf54`).
  - `WIP/improvements-0-3-1` is merged in (`bc7e89c`). This brings in the
    conftest fix `2611da2`, which clears `SPECY_ROAD_WORKER_ID`.

Not changed (outside the zones; possible follow-ups):

- `specy_road/orchestrate_plan.py` calls `compute_session_plan` without
  `unauthored=`, so it still counts unauthored leaves as ready.
- `specy_road/cli_usage.py` and `docs/roadmap-authoring.md` don't mention the
  new flags.
- `validate --strict` now fails a repo that has unauthored leaves, as it does
  for any warning.

## Verification

- `pytest` (after merging `WIP/improvements-0-3-1`): 2217 passed, 2 skipped,
  0 failed. Before the merge, two tests failed both here and on the base
  `ef2f4a4`. `SPECY_ROAD_WORKER_ID` leaked into the suite from the environment,
  and `2611da2` fixes that.
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `specy-road file-limits`: OK. `ruff check specy_road tests scripts`: clean.
- `scripts/check_test_private_imports.py`: 0 new.
  `scripts/check_clones.py` (pylint 4.1.3 via `uv tool run`, not installed in the env): 0 new.

## Walkthrough

1. `pytest tests/test_unauthored_leaf_guard.py`. The pickup tests run
   `do_next_task.main` on a real throwaway git repo and stop at the pickup
   header. The default run picks `M2` and says why `M1` was skipped;
   `--allow-unauthored` picks `M1`.
2. In a repo with a freshly scaffolded leaf (no acceptance), run
   `specy-road validate`, then `specy-road grind-session --plan`, then
   `specy-road do-next-available-task`. Each names the sheet and the section.

## Added

- `planning_sheet_bootstrap.PROMOTE_PLACEHOLDER`: one source for promote's line, so detection cannot drift from what promote writes.
- `planning_sheet_bootstrap.placeholder_sheet`: the single detection helper the plan asked for (A1–A4).
- `planning_sheet_bootstrap.unauthored_leaves`: the open-pickable-leaf scan that both validate and the session plan need (A2, A3).
- `planning_sheet_bootstrap._section_bodies` / `_scaffold_bodies` (cached): split a sheet into `##` sections and read the template's Intent/Approach bodies, so detection follows the template.
- `brief_acceptance.warn_unauthored`: validate's one capped block (A3).
- `do_next_task_leaf_guards.drop_unauthored`: the pickup guard, with the printed reason (A1).
- `session_plan.UnauthoredLeaf`, the `SessionPlan.unauthored` field, the `unauthored` bucket/dict key, and `totals.unauthored` when non-zero: the not-ready listing (A2).
- Branch in `_compute_waves`: unauthored leaves stay schedulable, so their dependents keep a wave.
- `unauthored=` on `compute_session_plan`; `allow_unauthored=` on `gather_session_plan`; `allow_unauthored=` on `_resync_and_select`; `show_all=` on `validate_at` / `run_validation`: plumbing for the flags.
- `--allow-unauthored` on do-next-available-task and grind-session, and `--all` on validate: the overrides required by A1–A3.
- Pickup forwarding of `--allow-unauthored` in `grind_session._pickup_args`: without it, the loop would plan a leaf that pickup then refuses.
- Mocks: `_Harness.gather_allow` (records the flag that reaches the plan) and keyword-tolerant `gather_plan` stubs in three grind test files, needed because the stubs had a fixed two-argument signature.
- Tests in `tests/test_unauthored_leaf_guard.py` (17): scaffolded / promote-skeleton / leftover-Approach sheets refused; filled sheet, acceptance, or missing sheet not refused; pickup skips with the reason, `--allow-unauthored` overrides, acceptance or filled sheet picked as before, an all-unauthored queue exits with the reason; `--plan` JSON and text list them, `--allow-unauthored` makes them ready, dependents keep their wave; validate prints one block, caps at ten, `--all` lists all, and stays silent for authored or closed leaves.
- Tests in `tests/test_grind_session_step.py`: with `--allow-unauthored`, at least one plan read and one pickup are observed, every plan read gets `allow_unauthored=True`, and every `do-next-available-task` call carries the flag. Without it, at least one plan read is observed, every plan read gets `False`, and no CLI call carries the flag (added to the existing pass-through test). No call count, order or position is pinned.
