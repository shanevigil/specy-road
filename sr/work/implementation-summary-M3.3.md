# Implementation summary for M3.3

Base: `b509adcd8a5a71978922a4d0a6dbc2692cd05b94`. Implementation commit: `f5a9235`.

## Summary

`specy-road rebalance-chunks --normalize` re-renders every included chunk in the canonical form every tool write already uses. It moves no node and leaves the manifest alone. `docs/roadmap-authoring.md` now explains why the first tool edit of a hand-authored chunk rewrites the whole file.

## Acceptance

- **A1** — `docs/roadmap-authoring.md`, new **Canonical key order** paragraph at the end of "Line-count policy (~500)" (next to the chunk-limit rules, as the sheet asks). It says every tool write re-renders the whole chunk it touches in one canonical form (`{"nodes": [...]}`, keys sorted inside every node, 2-space indent, UTF-8, trailing newline; nodes keep their chunk and position), so the first tool edit of a hand-authored chunk rewrites all of it and later diffs stay confined to changed fields. It then points at `rebalance-chunks --normalize [--dry-run]` for taking that rewrite on purpose in its own commit.
- **A2** — `specy-road rebalance-chunks --normalize` (`specy_road/bundled_scripts/roadmap_rebalance.py`). It skips the re-pack entirely: each chunk listed in `includes` is loaded and re-rendered with `render_json_chunk` (the same renderer every write uses) in place, so no node changes chunk or position, and `manifest.json` is not written. Only chunks whose bytes differ are staged, so already-canonical chunks produce `(every chunk is already canonical; nothing to do)` and no writes. Writes go through `AtomicWritePlan.commit(validate_callback(root))`, so a validation failure rolls back. `--dry-run` combines with it. The existing milestone-lock refusal runs first for both modes, unchanged.
- **A3** — `tests/test_roadmap_rebalance.py`: a hand-ordered chunk (keys reversed, bare top-level array, indent 4) is normalised to exactly `render_json_chunk(nodes)`, with node ids per chunk unchanged (including `M0.2` staying in `M1.json`, where a plain rebalance would move it), the manifest and the untouched chunk byte-identical, and dry-run writing nothing; a second test checks idempotence (empty plan, "already canonical" message, all `roadmap/**/*.json` bytes unchanged on the second run).

## Changes

Touch zones (final):

Changed: `specy_road/bundled_scripts/roadmap_rebalance.py`, `docs/roadmap-authoring.md`, `tests/test_roadmap_rebalance.py`.
Listed but not needed: `specy_road/bundled_scripts/roadmap_chunk_utils.py`. I first added an include-walking helper there, but `check_clones.py` showed `roadmap_chunk_router_pick.all_chunks_in_manifest_order` already does the same thing, and `roadmap_rebalance.py` already imports from that module, so I reused it and reverted the helper.

Not changed, outside the zones: `specy_road/cli_usage.py` line 82 still lists `rebalance-chunks` options as `--repo-root DIR --dry-run`. `--normalize` shows up in `rebalance-chunks --help` and in the authoring doc. Adding it to the top-level usage text is a follow-up if wanted.

## Verification

- `pytest`: 2221 passed, 2 skipped (full suite, after `rm -rf tests/fixtures/specy_road_dogfood/.specyrd`)
- `pytest tests/test_roadmap_rebalance.py`: 7 passed
- `specy-road validate / export --check / digest --check --repo-root tests/fixtures/specy_road_dogfood`: OK (run from this worktree via `python -m specy_road.cli`)
- `specy-road file-limits`: OK
- `ruff check specy_road tests scripts` (ruff 0.17.3): All checks passed
- `scripts/check_clones.py` (pylint 4.1.3): 12 current, 12 baselined, 0 new
- `scripts/check_test_private_imports.py`: 0 new

## Added

### Helpers
- `build_normalize_plan(root)`: returns the included chunks whose on-disk text differs from their canonical rendering, mapped to their nodes in place. An empty result is the no-op signal, and the tests use it directly.
- `_run_normalize(root, dry_run)`: prints the plan, handles the no-op and dry-run exits, and applies the plan atomically with validation and rollback.

### Branches / guards
- `--normalize` argparse flag, plus the `if args.normalize:` branch in `main`. It sits after the milestone-lock refusal, so normalising is refused while a milestone is in flight, same as a rebalance, because it rewrites chunk bytes under a locked subtree.
- No-op guard in `_run_normalize`: with nothing to rewrite, it says so and writes nothing (A2 idempotence).

### Mocks
- none

### Tests
- `_hand_order(chunk)`: test helper that rewrites a chunk the way a person might (reversed keys, bare array, indent 4) and returns the original nodes.
- `_ids_by_chunk(repo)`: test helper that maps each include to its node ids in order, to prove no node moved.
- `test_normalize_rewrites_hand_ordered_chunk_without_moving_nodes`: covers A2 and A3 (canonical output, no node movement, manifest and other chunks untouched, dry-run writes nothing).
- `test_normalize_is_idempotent`: covers A2 and A3 idempotence.
