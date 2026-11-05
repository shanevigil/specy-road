# Implementation summary for M12.4.1

## Summary

Each leaf's gate commit (`mark-implementation-reviewed`) now ends with a `Review-tally: <ID> rounds=<n> blocks=<b> integrity=<i> rca=<r> findings=<cat>:<n>,…` trailer. The trailer is built in the new `specy_road/review_tally.py` from the leaf's local review records (`review_rca.loop_state`), the RCA records and `specy-road integrity`. `roadmap-context.md` gains a "Quality by area" section. It reads **only** those trailers from tracked git history (`git log --topo-order` from HEAD), so `digest --check` gives the same result on every checkout and in CI. For each touch-zone area (first `quality_area_depth` path components, relative to the project), it shows these numbers over the last `quality_window` landed leaves:

- leaves landed
- leaves with no tally (left out of the rates)
- mean review rounds
- block rate
- integrity findings
- RCA escalations

Areas whose block rate is above `quality_threshold` are marked **flagged** and listed first. Ties sort by name. A history with no tallies prints no section. With `policy.quality_routing: true` (default false), `orchestrate plan` adds a `quality_routing (area: …)` strong-review item to each ready leaf in a flagged area, satisfied by one reviewer from the strong set.

**Rework (this round):** the first commit (`ab4c6382`) added the trailer through `review_gate.commit_trailers`. A1 says `review_gate.py` is at its line cap and is not edited. Commit `9db695d8` restores `review_gate.py` byte-for-byte to the base and has `mark_implementation_reviewed.py` append `review_tally.tally_trailers(ROOT, gate)` after the `Reviewed-by` lines (leaf gate only; the milestone full-review commit is not a leaf landing). It also moves the "Quality by area" docs into the zoned `docs/orchestration-quality.md`, leaving a one-paragraph pointer in `docs/orchestration-review.md`.

## Changes

- `specy_road/review_tally.py` (new): `leaf_tally`, `format_tally`, `tally_trailers(repo_root, gate)`, `parse_tally`, `gate_history`, `leaf_areas`, `AreaQuality`, `area_quality`, `flagged_areas`, `quality_review`.
- `specy_road/bundled_scripts/mark_implementation_reviewed.py`: the leaf gate commit's trailers are `commit_trailers(gate) + tally_trailers(ROOT, gate)`; the module docstring says so.
- `specy_road/digest.py`: `_section_quality(root, nodes)`, rendered before the footer and capped at 30 areas (`_MAX_AREAS`).
- `specy_road/orchestrate_plan.py`: `assign_leaf(..., flagged=)` adds the quality-routing items and notes; `build_orchestration_plan` computes `flagged_areas` once.
- `specy_road/orchestration_config.py`: defaults `quality_window: 50`, `quality_area_depth: 1`, `quality_threshold: 0.5`, `quality_routing: false`.
- `specy_road/templates/project/schemas/orchestration.schema.json`: the four matching properties.
- `docs/orchestration-quality.md` (new): trailer, digest section and routing. `docs/orchestration-review.md`: a short "Quality by area" pointer.
- `specy_road/review_gate.py`: unchanged from the base (the first commit's edit is reverted).
- `tests/test_review_tally.py` (new), `tests/test_digest.py` (extended).

Final touch zones are the brief's list. `specy_road/review_rca.py`, `specy_road/bundled_scripts/digest_cli.py` and `specy_road/review_gate.py` are read but not changed (A1 says not to edit `review_gate.py`, and `digest_cli` gets no new flag per the planning sheet). No change was needed outside the zones.

## Verification

- `pytest -n 4`: 4033 passed.
- `specy-road digest --check` (this repo) and `specy-road digest --check --repo-root tests/fixtures/specy_road_dogfood`: both OK.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK (pre-existing warnings only).
- `specy-road file-limits`: OK.
- Red-green: with the `tally_trailers` call removed from `mark_implementation_reviewed.py`, `tests/test_review_tally.py::test_mark_implementation_reviewed_writes_the_tally_after_the_reviewed_by_lines` fails; with it, the test passes.

## Walkthrough

1. `git diff ab4c6382~1 -- specy_road/review_gate.py` is empty.
2. Read `specy_road/review_tally.py` top to bottom: write side (`leaf_tally` → `tally_trailers`), then read side (`gate_history` → `_window` → `area_quality`).
3. `tests/test_digest.py` (quality block) pins:
   - the section's rows
   - flagged-first ordering
   - window and threshold policy
   - byte identity across runs, a monkeypatched clock, extra gitignored records, and a clone
   - no section on empty or tally-less history
4. `tests/test_review_tally.py` pins the trailer's counts, the end-to-end gate commit, and routing on and off.

## Added

- `specy_road/review_tally.py`: a new module for the trailer and the per-area math. `review_gate.py` is at its cap, and A1 names this file.
- `leaf_tally`: counts rounds, blocking rounds, findings per category, integrity findings and RCA escalations from the local records when the gate commit is made.
- `format_tally` / `parse_tally`: write and read the one trailer line. `parse_tally` returns `None` on a malformed line, so a bad trailer is ignored rather than crashing the digest.
- `tally_trailers(repo_root, gate)`: the hook `mark_implementation_reviewed.py` calls. Its `except Exception` guard returns no trailer when the records can't be read, so a tally never blocks the gate (the leaf then counts as "no tally").
- The call in `mark_implementation_reviewed.main`: A1 requires the trailer to be added there, not in `review_gate.py`.
- `gate_history`: reads gate commits from tracked history only (determinism). It also matches untallied gate commits by subject (`chore(rm-<codename>): mark implementation reviewed`) so they count as "no tally".
- `leaf_areas`: area = first N components relative to the project root. It skips blank zones and keeps one entry per area.
- `AreaQuality` and its properties: the per-area row. The rates are `None` when there are no tallied leaves, which prints as "—".
- `_window`: the last N distinct live leaves with touch zones, in gate-commit order.
- `area_quality`: aggregates the window and sorts flagged areas first. It returns empty when nothing in the window is tallied (A2: empty history prints nothing).
- `flagged_areas`: returns an empty set unless `quality_routing` is on (A3: off leaves the plan unchanged).
- `quality_review`: the plan items over the strong set. When no strong set exists it returns a note instead, since there is no one to route to.
- `digest._section_quality` and `_MAX_AREAS = 30`: the digest section, bounded in length. Its `except Exception` guard keeps history context from ever failing the digest.
- `assign_leaf(flagged=)` and the `flagged_areas` call in `build_orchestration_plan`: A3 routing.
- Four `DEFAULT_POLICY` keys and schema properties: the policy knobs, with defaults from the planning sheet.
- Tests in `tests/test_digest.py`, with helpers `_gate_commit`, `_quality` and `_history` (A1/A2):
  - `test_quality_section_lists_flagged_areas_first_with_their_numbers`
  - `test_quality_policy_sets_window_and_threshold`
  - `test_quality_section_is_byte_identical_across_runs_clocks_and_checkouts`
  - `test_no_tallied_history_prints_no_quality_section`
- Tests in `tests/test_review_tally.py`, with helpers `TALLY`, `_two_rounds` and `_routing_repo`:
  - `test_tally_trailer_counts_the_leafs_review_records`: the trailer's counts.
  - `test_mark_implementation_reviewed_writes_the_tally_after_the_reviewed_by_lines`: end-to-end gate commit, red-green verified.
  - `test_parse_tally_rejects_a_malformed_line`
  - `test_leaf_areas_take_the_first_components_relative_to_the_project`
  - `test_quality_routing_off_leaves_the_plan_unchanged` / `test_quality_routing_on_routes_a_strong_reviewer_to_a_flagged_area`: A3, both settings.
- Mocks: `monkeypatch` of `time.time` in the byte-identity test, to show the clock has no effect. No others.
