# Implementation summary: M4.11

grind-session --plan keeps ready leaves with overlapping touch zones out of the same parallel wave.

## What changed

- `session_plan._parallel_batches` now splits each wave's dispatchable set in pickup order: a leaf whose touch zone matches a leaf already in the set (the same path, or one a directory prefix of the other, after trimming `./` and a trailing `/`) moves to the next set, which is split the same way. `ready` and pickup order are unchanged; only the dispatch sets change.
- `Wave` carries `touch_zones` (leaf id to its zones). The split had to live inside `_parallel_batches` with its two-argument signature: `session_plan_git.enrich_session_plan_with_git` (the path `grind-session --plan` takes, outside the touch zones) rebuilds the batches with `_parallel_batches(plan.waves, new_ready)` after dropping leaves finished on a branch, so the zones travel on the waves.
- The overlap is named, not stored: `session_plan_render.zone_overlaps(plan)` re-derives, for each leaf in a set after the first, which leaf in the set before it it shares a zone with. Deriving it keeps it right after the git rebuild above. Text output adds a "Held for the next batch" block (`` `M1.3` waits for `M1.1`: `./src/a.py` overlaps `src/a.py` ``); JSON adds `zone_overlaps: [{node_id, waits_for, zones}]`. JSON `waves` still emit only `index` and `node_ids`.
- `orchestrate plan` builds its batches from `compute_session_plan(...).parallel_batches`, so it applies the same split with no code change there (A2); the held leaf shows up as the next `batch N:`.
- Docs: `docs/grind-session.md` (`parallel_batches` bullet, JSON example) and `docs/orchestration.md` (shared-checkout presence paragraph). Both files are exactly at their line caps (500 and 400), so the edits do not add lines.

## Acceptance

- **A1:** `parallel_batches[0]` (Dispatch now) never holds two leaves that share a zone; the later one in pickup order moves to the next set, and the text and JSON name the overlap. Tests: `test_shared_file_path_moves_later_leaf_to_next_batch`, `test_shared_directory_prefix_moves_later_leaf_either_way_round`.
- **A2:** `test_orchestrate_plan_applies_the_same_split` runs `build_orchestration_plan` on a git repo with two ready leaves (`src` and `src/a.py`) and gets two batches. The `orchestrate plan` output shows the split but does not name the overlap; naming it there would mean editing `specy_road/orchestrate_plan.py` / `orchestrate_cli.py`, which are outside the touch zones (see below).
- **A3:** a shared file path (`src/a.py` and `./src/a.py`) and a shared directory prefix (`src/pkg/mod.py`, `src/pkg/`, `src`), plus a negative case (`src/pkg` vs `src/pkg2/x.py` / `src/pkg.py` do not overlap).

## Touch zones (final list)

- `specy_road/bundled_scripts/session_plan.py`, `specy_road/bundled_scripts/session_plan_render.py`, `docs/grind-session.md`, `docs/orchestration.md`, `tests/` — changed.
- `specy_road/bundled_scripts/orchestrate_plan.py` — **does not exist**; the module is `specy_road/orchestrate_plan.py`. Not needed for the rule; it would be needed to name the overlap in `orchestrate plan`'s own output.
- `specy_road/bundled_scripts/session_plan_git.py` — should be listed: it is why the split sits inside `_parallel_batches`. Not edited.

## Placement note

The comparison and split (`zone_clash`, `split_on_zone_overlap`) live in `session_plan_render.py`, not `session_plan.py`, because `session_plan.py` was at 394 of its 400-line cap, an exemption is not allowed, and a new module would be outside the touch zones. The render module already holds `session_plan_to_dict`, which `session_plan` re-exports; its docstring now says it also holds the overlap rule. Moving the helpers to a dedicated `session_plan_zones.py` would be cleaner if the zone list allows it.

## Not covered

- A ready leaf whose zone overlaps an **in-flight** (claimed) leaf is still offered; the criteria name two ready leaves. Pickup already warns on that overlap.
- Zones are compared as literal paths; a glob zone (`src/**`) is not expanded, the same as the registry overlap warning.

## Verification

- `pytest tests/test_session_plan_touch_zones.py` — 5 passed; with the split replaced by the old one-set-per-wave code, the 3 positive tests fail.
- `pytest` on the session-plan, session-plan-git, orchestrate-plan and grind-session tests — 169 passed.
- Full `pytest` (first run): 2324 passed, 2 skipped, 1 failed — `test_lean_gates.py::test_private_imports_pass_on_committed_baseline`, because the batch-rebuild test imported the private `_parallel_batches`. I rewrote that test to go through the public `enrich_session_plan_with_git` instead of updating the baseline; `pytest tests/test_session_plan_touch_zones.py tests/test_lean_gates.py` then gave 16 passed, 2 skipped. I did not re-run the full 10-minute suite after that test-only change.
- `specy-road file-limits` — OK. `ruff check` on the changed Python — clean.

## Added

- `session_plan_render._norm_zone` — trims whitespace, a leading `./` and a trailing `/` so `./src/a.py` and `src/` compare as paths.
- `session_plan_render.zone_clash` — the overlap rule (same path or directory prefix), shared by the split and its naming so they cannot disagree.
- `session_plan_render.split_on_zone_overlap` — the greedy per-wave split that `_parallel_batches` calls (A1, A2).
- `session_plan_render.zone_overlaps` — names each held leaf, what it waits for and the two zones; derived so it survives `session_plan_git`'s batch rebuild.
- `session_plan_render._render_zone_overlaps` — the "Held for the next batch" text block (A1 "the overlap is named").
- `session_plan_to_dict`: `zone_overlaps` key, and `waves` emitted as `index` + `node_ids` explicitly so the new `Wave.touch_zones` does not change the JSON wave shape.
- `Wave.touch_zones` field — carries zones to `_parallel_batches`, whose signature `session_plan_git` depends on.
- `_compute_waves`: the `zones` map that fills `Wave.touch_zones`.
- `tests/test_session_plan_touch_zones.py` — five tests: shared file path, shared directory prefix both ways, non-overlapping prefix strings, batch rebuild releasing a held leaf, and `orchestrate plan` on a real git repo (built with `tests.test_orchestrate_plan.plan_repo`).
- Mock: in the rebuild test, `session_plan_git.finished_unmerged_ids` is monkeypatched to report M1.1 as finished on its branch, so the test drives the real `enrich_session_plan_with_git` rebuild without a git repo holding a finished feature branch.
