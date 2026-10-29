# Implementation summary for M4.8

## Scope

M4.8 covers A1–A3. A4 (branch cleanup after finish: `finish-this-task --delete-branch` and `specy-road branches prune`) was moved to its own leaf, M4.10, by the maintainer's decision, because it needs files outside these touch zones. This branch does not touch A4.

## Summary

- **A1:** `list-nodes --json` prints a JSON array with every node in full: all its fields, `rollup_status`, an untruncated title, and `chunk` (its chunk path in POSIX form, or `null`).
  - `--status` filters the JSON the same way it filters the table.
  - The table is unchanged, except that its chunk column is now always POSIX. That makes no difference on macOS or Linux.
- **A2:** `refresh-stubs --diff` implies `--dry-run` and prints a unified diff for each file a refresh would write: stubs, skills, `.specyrd/README.md`, and the managed blocks in `CLAUDE.md`, `.gitignore`, `.cursorindexingignore` and `AGENTS.md`.
  - Stub and skill text comes from `_content_for`.
  - Managed-block files are copied into a temp directory and the public `apply_*` functions run on those copies, so nothing in the repo is written.
  - Skill links, skips and refusals have no text to diff. They are printed as the usual `would write … (outcome)` lines, followed by the orphan report and `(dry-run; no files written)`.
- **A3:** `move-node` rewrites every touch-zone path segment equal to a renumbered display id. It matches whole segments only: `M1.10` and `M1.1-old` do not match `M1.1`.
  - It covers every node's zones, not just the moved node's, because a zone can name another node by its id. It also covers each registry claim's copy of the zones, which the finish check reads first.
  - Each segment is looked up once in the old→new map, so a chain (`M2.1`→`M2.2` while `M1.1`→`M2.1`) maps each zone to the node it originally named.
  - This runs inside the existing atomic plan, so the PM GUI's outline drag (`move_node_outline` → `move_node`) gets it too.
  - Directories on disk are not renamed. If an In Progress node's zone now names a path that does not exist, `validate` warns, as it does for any such zone.

## Changes

One commit per acceptance item, plus one for the docs:

- `2ee658d` A1: `specy_road/bundled_scripts/roadmap_crud_ops.py` (`cmd_list` builds the filtered rows first, then prints JSON or the table; the file stays within the 400-line cap), `specy_road/bundled_scripts/roadmap_crud_argparse.py` (`--json`, `dest="as_json"`), and the `list-nodes` row in `docs/pm-workflow.md`.
- `8499981` A2: `specy_road/bundled_scripts/refresh_stubs.py`: `--diff`, `_prefix`, `_block_previews` and `_print_diffs`. To stay within the 400-line cap, the existing argparse calls in `main` are reflowed onto fewer lines. Their behaviour is unchanged.
- `531d923` A3: `specy_road/bundled_scripts/roadmap_move_node.py`: `_rewrite_touch_zones`, called from `move_node` and from `_stage_registry_ids`. The CLI message and description now mention the zone rewrite.
- `3480f8b` docs: a `refresh-stubs --diff` row in the command table of `docs/pm-workflow.md`, linking to the upgrade section of `docs/install-and-usage.md`.
  - `docs/install-and-usage.md` is where `refresh-stubs` is documented, but it is already at the 400-line cap. Even a one-clause addition reflowed into an existing paragraph adds a line, so I left it unchanged.
- Tests: `tests/test_roadmap_crud.py`, `tests/test_refresh_stubs.py`, `tests/test_move_node_cli.py`.

**Final touch zones:** the listed zones were accurate for A1–A3. All changed paths are inside them.

## Verification

- `ruff check specy_road tests scripts`: all checks passed.
- `specy-road file-limits`: OK.
- `specy-road validate`, `export --check` and `digest --check` against the dogfood fixture: OK.
- `pytest tests/test_roadmap_crud.py tests/test_refresh_stubs.py tests/test_move_node_cli.py`: 49 passed.
- Full `pytest`: 2256 passed, 2 skipped, 2 failed. Both failures are in `tests/test_review_round6_evidence.py` (`test_committed_rename_into_the_zone_is_reported_on_both_sides`, `test_rename_out_of_the_zone_keeps_the_source_inside_it`), with `AttributeError: module 'specy_road.bundled_scripts.review_packet' has no attribute '_changed'`. They predate this branch: base commit `03f81a7` moved `review_packet` to `specy_road.git_changed_paths.diff_paths`, and this branch touches neither file.
- Manual checks (previous worker):
  - `list-nodes --json` and `--json --status Complete` on a copy of the dogfood fixture.
  - `refresh-stubs --diff` on a pre-0.3.0-style repo: diffs printed, and the repo was byte-for-byte unchanged afterwards.

## Added

- `cmd_list` `--json` branch: A1 output. Untruncated, every field, plus `chunk`.
- `roadmap_crud_argparse` `--json` argument: A1 flag.
- `refresh_stubs._prefix`: one source for the project prefix, used by both `refresh_stubs` and the diff so they cannot drift.
- `refresh_stubs._block_previews`: renders managed-block files on temp copies through the public `apply_*` functions, so the diff matches a real refresh without duplicating block logic.
- `refresh_stubs._print_diffs`: prints the A2 diffs and returns the entries that have no text to diff.
- `refresh_stubs` `--diff` argument and the `dry_run = args.dry_run or args.diff` line: A2 flag. The diff is a preview and writes nothing.
- `roadmap_move_node._rewrite_touch_zones`: A3, whole-segment rewrite over nodes and over registry entries.
- `_stage_registry_ids` calls it on claim entries: a claim's stale zone copy would otherwise strand the zones at finish.
- Docs row for `refresh-stubs --diff` in `docs/pm-workflow.md`: A2 needs to be discoverable, and `install-and-usage.md` has no room under the cap.
- Test `test_list_nodes_json_is_the_full_untruncated_list`: A1. Long title, fields, chunk, `--status`.
- Test `test_diff_previews_skills_and_managed_blocks_without_writing`: A2. Diffs present, links reported, nothing written.
- Test `test_the_diff_is_what_a_refresh_then_writes`: A2. Diff "+" lines equal what a real refresh writes.
- Test `test_diff_on_a_current_repo_shows_nothing`: A2. No-op case.
- Test helper `_diff_sections`: parses diff output by file for the A2 tests.
- Test `test_touch_zone_segments_naming_an_old_id_follow_the_node`: A3. Whole segments only, a chain, and another node's zone.
- Test `test_a_registry_claims_touch_zones_follow_the_new_id`: A3. Registry claim copy.
- Test helper `_set_zones`: sets fixture zones for the A3 tests.
- Mocks: none.
