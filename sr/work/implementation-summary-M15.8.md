# Implementation summary: M15.8

## What changed

- **A1 — placeholder.** `planning_sheet_bootstrap.PROMOTE_PLACEHOLDER` is now
  "Not written yet: pickup skips this leaf until this section is written.
  `specy-road author-approach <ID>` prints the prompt to write it." and promote
  writes it, with the node id substituted (`promote_placeholder(id)`), under
  `## Approach`. It used to go under `## Intent`. The critics' and verdict
  constraints stay above it, and it replaces the scaffold's Approach body. `## Intent` keeps the rationale and
  "Promoted from brainstorm idea …" and no longer has a placeholder line. The
  old line is `LEGACY_PROMOTE_PLACEHOLDER` and is still detected under
  `## Intent`. Every skip reason about `## Approach` (promote or scaffold), from
  both `placeholder_sheet` and `scaffold_sheet`, now ends with
  "; `specy-road author-approach <ID>` prints the prompt to write it", so
  pickup, `finish-this-task` and both plans show the command.
  `brainstorm_promote.py` stays at 400 lines and `docs/brainstorming.md` at 391,
  because both were reworded in place. Neither says Approach is filled in at pickup any more.
- **A2 — `specy-road author-approach <ID> [<ID>...]`.** This is the new
  `specy_road/bundled_scripts/author_approach.py`, wired into the `_SCRIPTS`
  map in `cli.py` and the usage text in `cli_usage.py`. For each leaf whose
  `## Approach` is still a placeholder, it prints the title, numbered
  acceptance, touch zones and each ancestor's Intent (root first). It then
  asks for the Approach (constraints, steps, how to verify), with no other
  section or file changed, and a `git commit --only <sheet>`. `-o` writes
  `work/prompt-approach-<ID>.md` instead. A leaf whose Approach is already
  written is reported on stderr and skipped. An unknown id, a non-leaf, or a
  missing sheet is an error (exit 1). It writes no file except with `-o`.
- **A3 — guard unchanged; plan line.** `do_next_task_leaf_guards.drop_unauthored`
  is untouched, and `--allow-scaffold-planning` still picks. `grind-session --plan`
  (`session_plan_render._render_misc`) and `orchestrate plan` text output
  (`orchestrate_cli.render`/`cmd_plan`, which calls
  `planning_scaffold_check.pickup_unauthored_leaves`) each print one line from
  `planning_scaffold_check.needs_approach_line`:
  `needs Approach (pickup skips them until ## Approach is written): <ids>; `specy-road author-approach <ids>` prints the prompt to write each`.
  `orchestrate_plan.py` and the JSON outputs are unchanged.

## Final touch zones

The listed zones plus `specy_road/bundled_scripts/orchestrate_cli.py`, which
the coordinator added. `do_next_task_leaf_guards.py` is in the zones but was
not changed: the reason it prints already carries the command.

## Tests changed because acceptance changed them

These now expect the promote placeholder under `## Approach` instead of
`## Intent`, and the author-approach hint on Approach reasons. Each assertion is
still exact.

- `tests/test_unauthored_leaf_guard.py`: `test_promote_skeleton_is_a_placeholder`
  and `test_a_leftover_scaffold_approach_is_a_placeholder`.
- `tests/test_finish_scaffold_planning.py`: the `_promote` expected reason.
- `tests/test_brainstorm_promote_judgement.py`: the Approach now ends with the
  promote placeholder instead of the scaffold body. The test
  `test_approach_is_left_alone_without_critics_or_verdict` was renamed to
  `…_is_only_the_placeholder_…` and asserts exact equality with it.

## Known gap outside the zones

`brief_dependency_context.is_placeholder_intent` (outside the zones) checks a
dependency's `## Intent` for `PROMOTE_PLACEHOLDER`. A new promoted sheet's
Intent is the seeded rationale, so it is inlined, which is fine. A dependency
sheet promoted before M15.8 still carries the legacy line, and it would now be
inlined into briefs where it used to be swapped out. The fix is a one-line
check for `LEGACY_PROMOTE_PLACEHOLDER` in that file. Also,
`suggested_prompts/` was not checked for wording about promote's placeholder,
because it is outside the zones.

## Verification

- `python -m pytest -q -n 4` (the full suite): 4124 passed.
- `specy-road file-limits`: OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.

## Added

- `planning_sheet_bootstrap.LEGACY_PROMOTE_PLACEHOLDER`: keeps detecting sheets promoted before M15.8.
- `planning_sheet_bootstrap._PROMOTE_MARK`: the id-independent part of the placeholder, used for detection.
- `planning_sheet_bootstrap.promote_placeholder(node_id)`: the placeholder naming the real id.
- `planning_sheet_bootstrap.approach_is_placeholder(bodies)`: author-approach's "still a placeholder" test (promote or scaffold Approach).
- `planning_sheet_bootstrap.sheet_placeholder(bodies)`: one detection order shared by `placeholder_sheet` and `scaffold_sheet`, replacing two copies.
- `planning_sheet_bootstrap.placeholder_reason(...)`: one reason format; adds the author-approach hint for `## Approach`.
- `planning_scaffold_check.needs_approach_line(reasons)`: the single "needs Approach" line both plans print.
- `orchestrate_cli.render(..., needs_approach=None)` parameter plus the `cmd_plan` lookup: prints that line in `orchestrate plan`.
- `session_plan_render._render_misc` branch: prints that line in `grind-session --plan`.
- `specy_road/bundled_scripts/author_approach.py` (`_sheet`, `_ancestor_intents`, `render_prompt`, `build_parser`, `main`): the new command (A2).
- `cli.py` `_SCRIPTS["author-approach"]` and the `cli_usage.py` lines: command wiring and help.
- Mocks: none new. Tests reuse `pick_leaf`'s existing monkeypatches.
- `tests/test_author_approach.py`:
  - `test_placeholder_text_says_pickup_skips_and_names_the_command`: A1 placeholder text.
  - `test_promote_writes_the_placeholder_under_approach_not_intent`: A1 placement.
  - `test_pickup_skip_reason_names_the_same_command`: A1 skip reason.
  - `test_guard_unchanged_allow_scaffold_planning_still_picks`: A3 guard.
  - `test_a_sheet_promoted_before_m15_8_is_still_detected`: legacy detection.
  - `test_author_approach_prints_the_prompt_and_changes_nothing`: A2 content and read-only.
  - `test_author_approach_skips_an_authored_leaf`: A2 skip.
  - `test_author_approach_o_writes_only_the_prompt_file`: A2 `-o`.
  - `test_both_plans_print_one_needs_approach_line`: A3 line in both plans.
  - `test_no_needs_approach_line_for_an_intent_only_placeholder`: the line lists only Approach skips.
