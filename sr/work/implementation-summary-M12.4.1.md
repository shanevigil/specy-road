# Implementation summary for M12.4.1

## Summary

Each leaf's gate commit (`mark-implementation-reviewed`) now ends with a `Review-tally: <ID> rounds=<n> blocks=<b> integrity=<i> rca=<r> findings=<cat>:<n>,…` trailer (fix round 1 adds `approvals=<a>`). The trailer is built in the new `specy_road/review_tally.py` from the leaf's local review records (`review_rca.loop_state`), the RCA records and `specy-road integrity`. `roadmap-context.md` gains a "Quality by area" section. It reads **only** those trailers from tracked git history (`git log --topo-order` from HEAD), so `digest --check` gives the same result on every checkout and in CI. For each touch-zone area (first `quality_area_depth` path components, relative to the project), it shows these numbers over the last `quality_window` landed leaves:

- leaves landed
- leaves with no tally (left out of the rates)
- mean review rounds
- block rate
- integrity findings
- RCA escalations

Areas whose block rate is above `quality_threshold` are marked **flagged** and listed first. Ties sort by name. A history with no tallies prints no section. With `policy.quality_routing: true` (default false), `orchestrate plan` adds a `quality_routing (area: …)` strong-review item to each ready leaf in a flagged area, satisfied by one reviewer from the strong set.

**Rework (this round):** the first commit (`ab4c6382`) added the trailer through `review_gate.commit_trailers`. A1 says `review_gate.py` is at its line cap and is not edited. Commit `9db695d8` restores `review_gate.py` byte-for-byte to the base and has `mark_implementation_reviewed.py` append `review_tally.tally_trailers(ROOT, gate)` after the `Reviewed-by` lines (leaf gate only; the milestone full-review commit is not a leaf landing). It also moves the "Quality by area" docs into the zoned `docs/orchestration-quality.md`, leaving a one-paragraph pointer in `docs/orchestration-review.md`.

## Fix round 1: population and sources

The reviewer `gpt-6.1-sol` blocked `052cad44` (R1–R6). The shared root cause was that the tally's population and inputs were never defined precisely. Commit `8fc1bd76` defines them once, in `specy_road/review_tally.py`, from tracked data only. It also merges `origin/WIP/improvements-0-3-1` (`86ab32d8`; one import conflict in `orchestrate_plan.py`, resolved by keeping both imports).

| Input | Tracked source | Covered by |
| --- | --- | --- |
| Population (completed leaves) | Each codename's `chore(rm-<codename>): complete, deregister` commit reachable from `HEAD` (eligibility only), ordered by gate commit since fix round 2. Never node status (R2). | `test_digest_quality.py::test_a_gated_leaf_that_has_not_completed_is_not_counted_and_evicts_nothing`, `::test_a_leaf_whose_branch_nets_no_change_under_the_project_still_counts` |
| Zones | The live graph by codename. For an archived leaf, the graph at its completion commit (`load_roadmap_nodes_at_ref`) (R4). | `::test_an_archived_completed_leaf_keeps_its_place_in_the_window` (public `archive_node`) |
| Tally | The newest `Review-tally` trailer on the codename's gate commit. A completed leaf without one counts as landed with no tally, so legacy-only history still prints rows (R3). | `::test_legacy_only_history_counts_its_leaves_with_no_rates`, `::test_quality_section_lists_flagged_areas_first_with_their_numbers` |
| Reviewer kinds | The review history merged with every record the passing gate counted (`gate.approvals + gate.blocks`), keyed by (resolved commit, model) the way `review_rounds` keys them. A human `REVIEW-human.md` with no history copy is therefore a round. The trailer gains `approvals=` (R1). | `test_review_tally.py::test_a_human_approval_with_no_history_copy_is_one_round` (runs `mark_implementation_reviewed.main --yes`: rounds=1, approvals=1), `::test_tally_trailer_counts_the_leafs_review_records` (history and live copy of the same record counted once) |
| Policy | `roadmap/orchestration.yaml` as committed at `HEAD` (`quality_policy`), with defaults when absent or invalid there. Never `orchestration.local.yaml` or the working tree (R5). | `test_digest_quality.py::test_a_local_overlay_cannot_change_the_committed_quality_policy`, `::test_quality_section_is_byte_identical_across_runs_clocks_overlays_and_checkouts` (malformed and valid overlay) |

R6: `tests/test_review_tally.py` no longer imports `_repo`/`_run`. It builds its repo with the public `make_review_repo` and calls `mark_implementation_reviewed.main(["--yes", ...])` directly.

Two further changes:

- **History simplification.** `--full-history` was added after a probe showed that git's default history simplification under the project pathspec drops a feature branch whose net change under the project is zero (claim, approve, deregister). That is the usual case in the nested `sr/` layout. A regression test pins it, and it fails without the flag.
- **Routing.** It now matches a zone to a flagged area by path prefix (`quality_review`), so it does not depend on the plan's own `quality_area_depth`. The areas themselves come from the HEAD policy.

**Generated file outside the zones:** with R3, this repo's `sr/roadmap-context.md` now gains a "Quality by area" section listing its 50 completed legacy leaves as no-tally rows, so `specy-road digest --check` (repo root) reports drift until `finish-this-task` regenerates it. I did not edit it: it is generated, outside the touch zones, and finish regenerates it on landing. The dogfood fixture's digest is unaffected.

## Probes

- Class R1 (a record the gate counts but history lacks): `_counted_rounds` adds every counted approval and block under its own record commit. That covers delta/carry records, substitutes and the interactive human approval. The milestone close path writes no tally (not a leaf landing). Result: one code path, tested.
- Class R1 (a duplicate history and live copy): `_two_rounds` writes `history/002.md` and `REVIEW-human.md` for the same commit and model. Result: rounds=2, not 3.
- Class R2 (a not-completed leaf in the population): the digest and `quality_routing` both use `area_quality`, which uses `completed_leaves`. No other reader. Result: covered by one test.
- Class R2/R4 (merge topology dropping completions): with no `--full-history`, the TREESAME-merge test fails. With it, the test passes.
- Class R3 (a non-empty window with no tallies): `area_quality` returns rows whenever the window is non-empty, with rates `None` printed as `—`. Result: legacy-only test passes. The section is absent only with no completed leaf.
- Class R4 (a leaf absent from the live graph): an archived or renamed codename falls back to the graph at its completion commit. A codename found in neither (for example a chore) is skipped. Result: archive test passes, with the same rows as before archiving.
- Class R5 (a per-checkout input): the inputs are the policy (now HEAD), review records (never read by the digest), the overlay (never read), the clock (never read) and the live graph (the same working-tree graph the whole digest renders and `--check` compares). Result: the byte-identity test covers a clock mock, extra local records, malformed and valid overlays, and a clone.
- Class R6 (private cross-module test imports): `grep` of the new tests finds imports only from `tests.review_repo_helpers`, `tests.test_orchestrate_plan` (public `ROSTER`, `only_assignment`, `plan_repo`), `tests.test_digest` (public `headings`) and `tests.test_history_walk` (public `commit`, `git`, `repo`).
- Red-green against `052cad44`'s `review_tally.py` and `digest.py`: the R1, R2, R3, R4, R5 and merge-topology regressions all fail there and pass at `8fc1bd76`.
- Runtime: `specy-road digest` on `sr/` (50 completed leaves) runs in about 1.75 s.
- `specy-road file-limits`: OK. `tests/test_digest.py` would have hit 418 lines, so the quality tests moved to the new `tests/test_digest_quality.py`.

## Fix round 2: window order

The reviewer `gpt-6.1-sol-low` blocked `9535b15a` with one finding, R1: the window followed completion-commit order, but the planning sheet specifies gate-commit order. With a window of one, the sequence gate A, gate B, complete B, complete A selected A instead of B. (`cursor-grok-4.6-high` approved `9535b15a`; `gpt-6.1-sol`'s R1–R6 apply to `052cad44` and were fixed in round 1.)

- **Merge.** `449104d7` merges `origin/WIP/improvements-0-3-1`; it was clean, with no conflicts.
- **Fix.** `2e30bb59` changes `completed_leaves`:
  - A reachable completion commit is now the eligibility filter only.
  - Each eligible leaf sits where its newest gate commit sits in `git log --topo-order --full-history`, newest first. Ties, which cannot happen since a commit has one position, would break on codename.
  - A completion with no gate commit (landed without the review gate) sits where its completion commit does. This is deterministic, and it is the only position such a leaf has in history.
  - The tally comes from the same newest gate commit that gives the order.
- **Docs.** `docs/orchestration-quality.md` gains an "Order" row, and the `review_tally.py` module docstring says the same.

## Fix round: probes

- Class (which commit orders the window): `_window` is the only consumer of `completed_leaves` order. The digest and `quality_routing` both reach it through `area_quality`. Result: one ordering, tested once via the digest.
- Gate and completion order differ (the reviewer's sequence): `test_digest_quality.py::test_the_window_follows_gate_order_not_completion_order`. Result: fails at `9535b15a`, passes at `2e30bb59`.
- Legacy completion with no gate commit: `::test_a_completion_without_a_gate_commit_sits_where_it_completed` pins the fallback. Result: passes. It also passed before, because there completion and gate order coincide, so it pins the rule rather than reproducing a bug.
- Re-gated leaf (rework, two gate commits): the newest gate commit gives both the order and the tally. Result: consistent by construction, since one dict entry is kept per codename, first met in newest-first log order.
- An approved but unfinished leaf whose gate is newest: still excluded, because eligibility needs a completion. Result: `::test_a_gated_leaf_that_has_not_completed_is_not_counted_and_evicts_nothing` passes.
- Merge topology (TREESAME feature merge): the `--full-history` scan is unchanged. Result: `::test_a_leaf_whose_branch_nets_no_change_under_the_project_still_counts` passes.
- Archived leaf and overlay determinism (round 1 classes): their tests pass unchanged.
- Private cross-module test imports: `grep -E "from tests\.[a-z_]+ import .*\b_[a-z]"` over the new test files finds nothing.
- `specy-road file-limits`: OK.

## Changes

- `specy_road/review_tally.py` (new): `leaf_tally`, `format_tally`, `tally_trailers(repo_root, gate)`, `parse_tally`, `gate_history`, `leaf_areas`, `AreaQuality`, `area_quality`, `flagged_areas`, `quality_review`.
- `specy_road/bundled_scripts/mark_implementation_reviewed.py`: the leaf gate commit's trailers are `commit_trailers(gate) + tally_trailers(ROOT, gate)`; the module docstring says so.
- `specy_road/digest.py`: `_section_quality(root, nodes)`, rendered before the footer and capped at 30 areas (`_MAX_AREAS`).
- `specy_road/orchestrate_plan.py`: `assign_leaf(..., flagged=)` adds the quality-routing items and notes; `build_orchestration_plan` computes `flagged_areas` once.
- `specy_road/orchestration_config.py`: defaults `quality_window: 50`, `quality_area_depth: 1`, `quality_threshold: 0.5`, `quality_routing: false`.
- `specy_road/templates/project/schemas/orchestration.schema.json`: the four matching properties.
- `docs/orchestration-quality.md` (new): trailer, digest section and routing. `docs/orchestration-review.md`: a short "Quality by area" pointer.
- `specy_road/review_gate.py`: unchanged from the base (the first commit's edit is reverted).
- `tests/test_review_tally.py` (new), `tests/test_digest_quality.py` (new).

Final touch zones are the brief's list. `specy_road/review_rca.py`, `specy_road/bundled_scripts/digest_cli.py` and `specy_road/review_gate.py` are read but not changed (A1 says not to edit `review_gate.py`, and `digest_cli` gets no new flag per the planning sheet). No change was needed outside the zones.

## Verification

- Round 0: `pytest -n 4`: 4033 passed, and both `digest --check` runs passed.
- Fix round 2 (targeted only): 173 passed across the same twelve files.
- Fix round 1 (targeted only, per the coordinator): 171 passed across `test_digest.py`, `test_digest_quality.py`, `test_review_tally.py`, `test_mark_implementation_reviewed_gate.py`, `test_orchestrate_plan.py`, `test_finish_land_regenerates.py`, `test_generated_files.py`, `test_orchestration_config.py`, `test_strong_review.py`, `test_milestone_full_review.py`, `test_review_hardening.py` and `test_integrity_gate.py`. `digest --check` on this repo now reports the expected drift explained under Fix round 1.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK (pre-existing warnings only).
- `specy-road file-limits`: OK.
- Red-green: with the `tally_trailers` call removed from `mark_implementation_reviewed.py`, `tests/test_review_tally.py::test_mark_implementation_reviewed_writes_the_tally_after_the_reviewed_by_lines` fails; with it, the test passes.

## Walkthrough

1. `git diff ab4c6382~1 -- specy_road/review_gate.py` is empty.
2. Read `specy_road/review_tally.py` top to bottom: write side (`leaf_tally` → `tally_trailers`), then read side (`gate_history` → `_window` → `area_quality`).
3. `tests/test_digest_quality.py` pins:
   - the section's rows
   - flagged-first ordering
   - window and threshold policy
   - byte identity across runs, a monkeypatched clock, extra gitignored records, and a clone
   - no section on empty or tally-less history
4. `tests/test_review_tally.py` pins the trailer's counts, the end-to-end gate commit, and routing on and off.

## Added

Fix round 2 changes:

- `completed_leaves`: orders by the newest gate commit's log position, falling back to the completion commit's position (R1). It returns the same tuple shape as before.
- `tests/test_digest_quality.py`:
  - helper `_complete`, split out of `_land` so a test can separate gate and completion
  - `test_the_window_follows_gate_order_not_completion_order` (R1)
  - `test_a_completion_without_a_gate_commit_sits_where_it_completed` (the deterministic legacy rule)

Fix round 1 changes to the inventory below:

- `_counted_rounds`: merges the history with the gate's counted records, by (commit, model) (R1).
- `leaf_tally(repo_root, gate)`: now takes the gate, so its counts come from the gate's own evaluation. Adds `approvals` (R1).
- `quality_policy`: the policy at `HEAD` with defaults (R5).
- `completed_leaves`: replaces `gate_history`. It returns completion commits reachable from `HEAD` (with `--full-history`) plus each codename's newest tally (R2, R3).
- `_project_zones`: shared zone normalisation for `leaf_areas` and `quality_review`.
- `_window`: zones come from the live graph, with the graph at the completion commit for archived leaves (R4).
- `flagged_areas(root, policy)`: loads the full live graph itself, rather than the plan's possibly `under`-filtered nodes.
- `quality_review`: prefix match against flagged areas.
- `tests/test_digest_quality.py` (new, moved from `tests/test_digest.py`):
  - helpers `_land`, `_tally`, `_set_policy`, `SECTION`
  - `test_a_gated_leaf_that_has_not_completed_is_not_counted_and_evicts_nothing` (R2)
  - `test_an_archived_completed_leaf_keeps_its_place_in_the_window` (R4)
  - `test_a_local_overlay_cannot_change_the_committed_quality_policy` (R5)
  - `test_legacy_only_history_counts_its_leaves_with_no_rates` (R3)
  - `test_a_leaf_whose_branch_nets_no_change_under_the_project_still_counts` (merge topology)
  - the byte-identity test, extended with overlays
- `tests/test_review_tally.py`:
  - helpers `_gate_repo`, `_mark_reviewed` (public helpers, R6)
  - `test_a_human_approval_with_no_history_copy_is_one_round` (R1)
- Removed: `gate_history` and `AreaQuality`'s use of the policy argument (`area_quality(root, nodes)` reads `quality_policy`).

Inventory from the earlier rounds:

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
- Tests now in `tests/test_digest_quality.py`, with helpers `_gate_commit`, `_quality` and `_history` (A1/A2):
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
