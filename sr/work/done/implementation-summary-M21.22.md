# Implementation summary: M21.22 (rc4-small-code-fixes)

Branch `feature/rm-rc4-small-code-fixes`, base `672217421d031e12a96d9317269bc9fd37af2ad6`, change commit `54c94dbb`.
Touch zones as listed on the node; no change outside them was needed.

## A1: text fixes

- `specy_road/worker_adapters.py` module docstring: Cursor's default passes `--trust --sandbox enabled`; only
  `cursor_force: true` opts into `--trust --force` (the widest), pointing at `docs/orchestration-workers.md`
  (matches `worker_adapter_cursor.SANDBOX_FLAGS` / `FORCE_FLAGS`). A Claude Code reviewer runs bare (API key or
  `apiKeyHelper`) or in explicit settings mode (subscription), pointing at `docs/orchestration-reviewer-output.md`
  (matches `reviewer_auth.claude_reviewer_mode` and `worker_adapter_claude` reviewer launch).
- `git-workflow.schema.json` `on_complete` description and `specyrd-finish.md` step 7: `merge` / `auto` land per
  `land` (`push`, the default, pushes; `local` fetches and pushes nothing). Enum and properties unchanged.

## A2: dead code removed

Grep run before deleting (and again after), over `specy_road/ gui/ tests/ scripts/` (node_modules excluded):

```
$ grep -rn "persist_merged_nodes\|sync_registry_node_ids\|missing_work_template_rels" specy_road/ gui/ tests/ scripts/
specy_road/upgrade_templates.py:124:def missing_work_template_rels(existence_root: Path) -> list[str]:
specy_road/bundled_scripts/roadmap_outline_ops.py:17:def persist_merged_nodes(root: Path, merged: list[dict]) -> None:
specy_road/bundled_scripts/roadmap_outline_ops.py:269:def sync_registry_node_ids(root: Path, old_to_new: dict[str, str]) -> None:
specy_road/bundled_scripts/roadmap_id_rewrite_staging.py:26:    """Stage every chunk rewritten by the move, matching ``persist_merged_nodes``."""
tests/test_roadmap_outline_registry.py:9,12,27: (helper-only test of sync_registry_node_ids)
```

No caller besides the definitions, one docstring mention and the helper-only test. After the change the same grep
returns nothing (exit 1).

- Deleted `persist_merged_nodes` and `sync_registry_node_ids` from `roadmap_outline_ops.py`, plus the imports only
  they used (`load_json_chunk`, `roadmap_dir`, `write_json_chunk`, `manifest_includes`, `registry_path`). No other
  module imported those names via `roadmap_outline_ops`.
- `roadmap_id_rewrite_staging._stage_merged_nodes` docstring no longer cites the deleted writer.
- Deleted `upgrade_templates.missing_work_template_rels` (`work_template_ship_plan` remains, used by `upgrade.py`).
- Removed `tests/test_roadmap_outline_registry.py` (planned test change: `removed-test-file:` and `removed-test:`).
  Registry `node_id` rewrites stay asserted by the public move test
  `tests/test_move_node_cli.py::test_a_registry_claim_follows_the_new_id` (and
  `test_a_registry_claims_touch_zones_follow_the_new_id`).

## A3: pickup hint marker

`print_orchestration_hint` now calls `history_cache.ensure_cache_dir(marker.parent)` instead of a bare `mkdir`, so
the cache's own `.gitignore` of `*` exists before the marker is written. New test
`test_the_hint_marker_leaves_the_tree_clean`: git repo with a `.gitignore` lacking `.specyrd/cache/`, hint printed
once, `git status --porcelain --untracked-files=all` empty, second call prints nothing. Red without the fix
(restored HEAD's `on_complete_pickup.py`: the test fails, exit 1), green with it.

## A4: CHANGELOG

`[Unreleased]` → `### Fixed`: hint marker; `on_complete` / `land: local` wording. Internal writers not listed
(no user-facing change).

## A5: net line change

`git diff --stat` base..change: 10 files, +38 / −98. Package ≈ −62 (two writers, helper, imports, docstring), tests
≈ −9 (−29 removed file, +20 new test), docs/text +a few, CHANGELOG +9.

## Verification

- `python -m pytest -n 4 -q`: 5419 passed.
- `python -m pytest -q tests/test_pickup_orchestration_hint.py tests/test_move_node_cli.py`: pass.
- `ruff check specy_road/ tests/test_pickup_orchestration_hint.py`: clean.
- `specy-road file-limits`: OK.

## Added

- Import `ensure_cache_dir` in `on_complete_pickup.py`: needed by the A3 fix.
- Test `tests/test_pickup_orchestration_hint.py::test_the_hint_marker_leaves_the_tree_clean`: A3 regression (dirty
  tree in a repo without the managed `.gitignore` block).
- `import subprocess` in that test file: drives git for the new test.
- Helpers, branches, guards, mocks: none.
