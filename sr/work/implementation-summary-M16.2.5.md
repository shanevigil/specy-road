# Implementation summary — M16.2.5

Library modules imported by the package move out of `bundled_scripts`.

## What changed

The rule was applied to the tree at `ed2eb59f`, before any move, and committed on this leaf's planning sheet (`b8c0d0ad`). A module under `specy_road/bundled_scripts/` moves when a `specy_road` module outside `bundled_scripts` imports it. Modules named by `cli.py`'s `_SCRIPTS` or `_FORWARDED` stay, and so does `review_node.py`. That is 33 modules. Each `git mv` lands on the same filename in `specy_road/`. No other module moves. The old path to new path table is on the sheet.

Imported and left in place: `chore_cli.py`, `export_roadmap_md.py`, `generate_brief.py`, `refresh_stubs.py`, `review_cli.py`, `review_node.py`, `review_packet.py`, `roadmap_outline_group.py`, `role_prompt.py`, `scaffold_planning.py`.

No re-export is kept. Console entry points are `specy_road.cli:main` and `specy_road.specyrd_cli:main`. No shipped template names a moved path. No documented `python specy_road/bundled_scripts/...` command names a moved path (the commands that form does name are not in the move list).

Imports of the moved modules now use `specy_road.<module>`. A `from specy_road.bundled_scripts import` that named both a moved module and one that stays is split into two import lines. Patch-target strings and the private-import baseline use the new dotted path. Two path strings that the tests compare with a scanned file were updated with the move: `INDEX_MODULE` in `tests/test_graph_lookup_count.py`, and the `brainstorm_session.py:write_session` row in `tests/test_clock_and_atomic_write.py`. Docstrings that still name the old path were left as they were:

- `specy_road/worker_state.py`
- `specy_road/reviewer_run_failure.py`
- `tests/test_graph_lookup_count.py` (the module docstring)

`docs/roadmap-authoring.md` still links `specy_road/bundled_scripts/roadmap_load.py` and `planning_artifacts.py`. Those are markdown links, not a documented `python specy_road/bundled_scripts/...` command, and `docs/` is outside the touch zones, so they were not edited and no re-export was added.

Baselines, path rewrites only:

- `scripts/line_width_baseline.py --transfer` and `scripts/ruff_quality_baseline.py --transfer` for each moved file
- `constraints/test-private-imports-baseline.txt`: the six entries for `roadmap_gui_settings`, `roadmap_gui_remote`, `roadmap_layout` and `brainstorm_research`
- `constraints/clone-baseline.json`: `brainstorm_chat`, `roadmap_chunk_router_pick`, `roadmap_chunk_utils`

The move is two commits because `git commit --only` recorded the new files and the import edits while the deletions of the old paths stayed staged. `198709f0` removes those old paths. From the list commit to HEAD, all 33 show as renames whose hunks are import lines.

## Checks

- Targeted pytest, the 135 test files whose imports or path strings changed: 1992 passed (`pytest -n 4`).
- `ruff check specy_road tests scripts`: all checks passed.
- `specy-road file-limits`: OK. The three existing 750-line warnings (`docs/release-runbook.md`, `review_node.py`, `tests/test_upgrade_preview.py`) are unchanged.
- `scripts/check_test_private_imports.py`: 0 new. Nine stale entries were already stale and are not on the moved modules; they were left in place.
- `scripts/check_clones.py`: 9 current, 9 baselined, 0 new.
- Package line change against `ed2eb59f`, rename-aware: +332 −332, net 0. The informational estimate was about −40. Tests gained 6 lines from the split imports.

## Final touch zones

The zones the coordinator recorded, including this leaf's planning sheet.

## Fix round 1

Finding class: `--transfer` stores the new path and leaves `commit` at the pickup commit, then a test requires every listed path to be in that commit's tree. The ruff baseline still records `542aa46c`. `--transfer` does not change `commit` (`test_transfer_sums_old_families_onto_new` asserts the written commit stays), and changing `PICKUP` would drop the "still the pickup commit" check. The tree check now has one rule: a listed path is in the pickup tree, or the committed move table maps it from an old path that is in that tree. A path that is neither still fails.

The same class reaches `scripts/line_width_baseline.json` (commit `361a5c73`, 24 new paths absent from that tree, all of them new sides of the same move). The review records that as not a defect, because no test or gate checks that file against its commit tree. That file was not rewritten and no line-width test was added.

## Probes

- Ruff quality baseline against `542aa46c`: 27 `specy_road/<module>.py` paths were absent; each old path is in that tree. After the move-table rule the pickup test passes, and a path that is not in the tree and not on the table still fails.
- Line-width baseline against `361a5c73`: 24 paths absent, all new sides of the same move. No test reads that commit tree. Left as the review recorded.
- Private-import baseline and clone baseline: neither file has a `commit` field, so this class does not apply.
- `--transfer` contract: `test_transfer_sums_old_families_onto_new` still requires the recorded commit to stay put. The ruff baseline commit was not rewritten.

## Fix round 2

Finding class: the pickup-tree check read the move list from a file under the planning tree. Promotion removes that tree, so the check raises `FileNotFoundError` in a release worktree that still has the pickup commit. The move list now lives in the test, which promotion keeps. One rule: a listed path is in the pickup tree, or `_MOVED_FROM` maps it to a path that is. The 33 names are the same filename move, and they match the planning sheet. The baseline JSON was not given a new key: its entries stay path rewrites only.

## Probes

- `tests/test_ruff_quality_baseline.py` no longer names the planning sheet or reads it. The 33 in-test pairs equal the sheet's table. All 27 baseline paths that are absent from `542aa46c` resolve through that table, and their old paths are in that tree.
- Other `sr/planning` mentions in `tests/`, `scripts/` and `specy_road/` are existing examples and docstrings. None of them open this leaf's move sheet. This class does not reach them.
- Line-width baseline: no test reads the planning tree for it. The ungated path mismatch from fix round 1 is unchanged.
- A path that is not in the pickup tree and not in `_MOVED_FROM` still fails. The recorded commit is still `542aa46c`.

## Unanswered

none

## Added

- Helpers: `_MOVED_FROM` is the move table the suite keeps after promotion; `_in_pickup_tree` is the one rule the pickup-tree check uses
- Branches or guards: none
- Mocks: none
- Tests: none added. `test_baseline_records_the_pickup_commit_and_only_its_files` still requires the pickup commit, and a transferred path passes only when its old path is in that tree
