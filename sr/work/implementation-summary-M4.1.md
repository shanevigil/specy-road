# Implementation summary: `M4.1` — promote carries the converge judgement into sheets and writes an authoring prompt

Branch `feature/rm-promote-judgement`, base `d703de1`.

## What changed

- **A1 — References and Approach.** `seed_planning_sheet` now prepends, under
  `## Approach`, a "Constraints from the brainstorm's converge pass:" list with
  one line per critic (`- <role> critic: <objection>`) and the verdict
  reasoning (`- Verdict (<recommendation>): <why>`); the scaffold's Approach
  line stays below it. `## References` now opens with one
  `- Overlaps existing node <id> (<relation>)` line per recorded overlap, ahead
  of the existing source, hypothesis, assumption and alternative lines. With no
  critics or verdict, Approach is untouched. The Intent placeholder is kept, so
  pickup and `validate` still treat the node as unauthored until it is written.
- **A2 — frame on the anchor.** New `seed_anchor_frame` writes
  `## Brainstorm frame` (session slug + one `- **key:** value` line per frame
  answer) into the anchor's sheet when the session has a frame and an anchor.
  It appends the section, or replaces it on a later promote. It runs inside the
  existing `TreeSnapshot` before deferred validation, so a failed batch restores
  the anchor sheet too. Dry runs and root-level promotes write nothing.
- **A3 — authoring prompt.** New `render_authoring_prompt` in
  `brainstorm_prompt.py` (rendered like the other passes, written with
  `write_prompt(..., pass_name="authoring")`) →
  `work/brainstorm-<slug>-authoring-prompt.md`. It lists the session, anchor,
  governance files, agreed frame, and per promoted node its sheet path,
  rationale, sizing, critics, verdict, overlaps and sources; then asks for
  Intent, Approach steps, Tasks, acceptance (`edit-node --set acceptance=`),
  touch zones (`--set touch_zones=`) and References per node. Written only
  after validation succeeds; promote prints `authoring prompt: <path>` to
  stderr beside the existing missing-fields line. It covers the nodes of that
  promote call.
- **A4 — tests.** Existing promote tests unchanged and passing; new
  `tests/test_brainstorm_promote_judgement.py` covers each section.
- **Docs.** `docs/brainstorming.md` §5 and the prompt-file list;
  `specyrd-brainstorm.md` stub section 5.
- **Close archives the authoring prompt (review round 1 fix).**
  `brainstorm_close.PROMPT_PASS_RE` now matches `-authoring`, so
  `brainstorm close` moves `work/brainstorm-<slug>-authoring-prompt.md` into
  `work/brainstorm-closed/` with its session (gpt-6.1-sol's required change;
  `brainstorm_close.py` was added to the touch zones in `dc2d134`). The
  existing ownership rule still applies: an open session whose slug is
  `<slug>-authoring` keeps the bare prompt name it shares with `<slug>`'s
  authoring prompt.

`_reference_lines` moved from `brainstorm_promote.py` to `brainstorm_prompt.py`
as `reference_lines` (same output plus overlaps) so the sheet and the authoring
prompt share it, and because `brainstorm_promote.py` sat 4 lines under the
400-line file cap. To fit, a few multi-line `raise` / `_build_node(...)` calls
in that file were joined onto one line (formatting only). Path resolution in
`seed_planning_sheet` became `_sheet_path`, reused for the anchor.

## Verification

Fix round (at `c9dcb74`): the targeted suite below **404 passed** (the 403
plus the new close test), `specy-road file-limits` OK, `ruff check
specy_road tests` clean, dogfood `validate` / `export --check` /
`digest --check` OK. Full `pytest -q -p no:cacheprovider`: **2565 passed, 2 skipped**, exit 0 (18 min).

Round 1 (at `d35209c`):

- **Full `pytest` did not complete.** The machine was shared with several
  other agents' test runs (load average 40–78); three attempts were killed at
  the harness time limit (the last reached 2% in ~30 min). Not a test failure:
  no run reported a failure. Run the full suite before merge.
- Targeted `pytest -q -p no:cacheprovider` over every test file that imports
  the brainstorm modules or covers the changed templates, docs or file limits
  (`tests/test_brainstorm_*.py`, `test_gui_app_brainstorm.py`,
  `test_review_round6_brainstorm.py`, `test_unauthored_leaf_guard.py`,
  `test_finish_scaffold_planning.py`, `test_doc_links.py`,
  `test_validate_file_limits.py`, `test_review_round6_docs.py`,
  `test_specyrd_init.py`, `test_specyrd_skills.py`, `test_refresh_stubs.py`,
  `test_upgrade.py`, `test_agents_md_block.py`, `test_project_layouts.py`,
  `test_init_project_gitignore.py`, `test_prerelease_files.py`): **403 passed**, exit 0.
- Earlier, on the finished code: `pytest -k brainstorm` 227 passed (before the
  new file), then `tests/test_brainstorm_promote_judgement.py` 11 passed.
- `specy-road file-limits`: OK (`brainstorm_promote.py` 398, `docs/brainstorming.md` 393).
- `ruff check specy_road tests`: clean.
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK.

## Touch zones (final list)

Used: `specy_road/bundled_scripts/brainstorm_promote.py`,
`specy_road/bundled_scripts/brainstorm_prompt.py`,
`specy_road/bundled_scripts/brainstorm_close.py`,
`specy_road/templates/specyrd/commands/specyrd-brainstorm.md`,
`docs/brainstorming.md`, `tests/`.

Not touched, worth a follow-up: the CLI's `next_step` after promote
(`brainstorm_cli_v2.py`) does not mention the authoring prompt; promote's
stderr line does.

## Added

- `brainstorm_prompt.reference_lines` — moved from promote's `_reference_lines`, now also emits overlap lines (A1); shared by sheet and authoring prompt.
- `brainstorm_prompt._judgement_items` — critic and verdict lines, shared by the Approach seed and the authoring prompt.
- `brainstorm_prompt.constraint_lines` — the Approach block (lead line + items), empty when there is no judgement (A1).
- `brainstorm_prompt._authoring_node_lines` — per-node section of the authoring prompt (A3).
- `brainstorm_prompt.render_authoring_prompt` — the authoring prompt (A3).
- `brainstorm_promote._sheet_path` — planning-sheet path resolution, extracted from `seed_planning_sheet` and reused for the anchor.
- `brainstorm_promote._prepend_to_section` — generalises the existing References insertion so Approach uses the same code.
- `brainstorm_promote.seed_anchor_frame` — writes `## Brainstorm frame` on the anchor (A2).
- `_replace_section(..., append=True)` branch — appends a missing heading instead of skipping it; used only by the frame.
- Guard: frame skipped when the session has no frame, no anchor, or the anchor has no sheet.
- Guard: authoring prompt and frame not written on dry run; prompt written only after validation passes.
- Mock: `run_validate_raise` monkeypatched to fail in one test, to prove the frame is restored and no prompt is written.
- Tests (`tests/test_brainstorm_promote_judgement.py`):
  - `test_references_list_overlaps_by_id_and_relation` — A1 overlaps.
  - `test_approach_lists_critics_and_verdict_as_constraints` — A1 Approach.
  - `test_approach_is_left_alone_without_critics_or_verdict` — no empty constraint block.
  - `test_the_seeded_sheet_still_counts_as_unauthored` — pickup still skips the seeded leaf.
  - `test_the_anchor_sheet_gains_the_recorded_frame` — A2.
  - `test_a_second_promote_replaces_the_frame_section` — no duplicate section on rerun.
  - `test_no_frame_leaves_the_anchor_sheet_alone` — A2 negative.
  - `test_a_dry_run_writes_no_frame` — dry run writes nothing.
  - `test_promote_writes_the_authoring_prompt` — A3 path, content and stderr line.
  - `test_a_dry_run_writes_no_authoring_prompt` — dry run writes nothing.
  - `test_a_failed_validation_writes_no_authoring_prompt_or_frame` — rollback covers both.
  - `test_close_archives_the_authoring_prompt_with_its_session` — review fix: promote then close moves the authoring prompt.
- `brainstorm_close.PROMPT_PASS_RE` gains `-authoring` — review fix: close archives the new prompt pass.
- Test edits (`tests/test_brainstorm_cli.py`, extended, nothing removed):
  - `test_close_moves_the_session_and_its_prompts_and_nothing_else` — adds an `-authoring` prompt to the set close must move.
  - `test_close_leaves_a_name_another_open_session_could_own` — adds an open `a-authoring` session whose bare prompt name close of `a` must leave.
