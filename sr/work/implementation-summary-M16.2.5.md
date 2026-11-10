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

## Unanswered

none

## Added

- Helpers: none
- Branches or guards: none
- Mocks: none
- Tests: none
