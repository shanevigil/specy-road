# Implementation summary: M21.18 — deferral bound to its decision

Branch `feature/rm-deferral-bound-to-its-decision`, base `79f2029e`, code commit `5f92a1c5`.

## What changed

- **A1 — one predicate** (`specy_road/review_deferral.py`): `deferral_in_effect(repo_root, node_id, marker) -> list[str]`
  (problems; empty means in effect). It requires, in order: the RCA the marker names is among
  `loop_state`'s valid records, recommends `defer_findings` and has `trigger.round == marker.round`;
  the marker's items match the RCA's `deferred_findings` one to one (equal reviewer, finding, category,
  acceptance_id, input_class; commits compared with `review_target.same_commit`, so the RCA's 12-character
  prefix matches the marker's full sha); the decision is closed, on this node, of kind `decision`, its
  `why_now` starts `<RCA> recommends defer_findings`, its answer starts `Deferred by `, contains
  `from <RCA>:` and, for each marker item, `answer_item(item)`; finally `qualify_deferral` accepts the
  items. Shape-validity stays with `load_markers` (only valid markers reach the predicate).
- **A2** — `review defer`'s `_record` writes each item through the shared `answer_item` (finding, reviewer,
  full commit, category on acceptance id, input class) — answer text only, no schema change.
  `apply_deferrals` uses only the predicate (`_closed_decisions` removed; the ledger is still read only
  when a marker names the block). `review_next_step.facts` and `rework_rca.governing_rca` go through
  `rca_deferral(repo_root, node_id, rca_name)`, a thin lookup of the marker beside an RCA that returns
  `None` (no marker), `[]` (in effect, via the predicate) or problem lines. A marker that exists but is not
  in effect gives `DEFER_UNAPPLIED`, its problem lines are joined into `refused` after `review defer`'s own
  refusal ("already applied"), and it is never the governing rework design. `applicable_record`'s
  "already applied" check is unchanged.
- **A3 — tests**: `_forge_closed_deferral` now writes `RCA-<round>.md` (default round 2, a valid forced
  RCA) with the items, a ledger entry in `_record`'s shape (`bound_ledger`) and the marker; the agreement
  test's forged repo writes the same bound entry (`LEDGER` is now `bound_ledger(...)` for the malformed-marker
  test). The rounds test's two forges keep their outcomes (A2 one keeps opus blocked, A1 one clears it).
  New parametrized `test_a_marker_not_bound_to_its_decision_and_rca_resolves_nothing` (9 cases) first runs a
  genuine `review defer` (RCA commit as a 12-char prefix) and checks the block is removed, the step is
  `spent_defer_applied_no_executor` and `governing_rca` is RCA-2; then each tamper leaves the reviewer in
  `GateResult.blocks`, the budget state not `spent_defer_applied*` and `governing_rca` `None`. Red check:
  with the predicate reverted to "any closed decision on the node" and `rca_deferral` to "marker exists",
  all 9 cases fail.
- **A4 — docs**: `docs/orchestration-review.md` deferral paragraph and `docs/design-notes/review-loop-rca.md`
  "Audit trail and gate" state the binding; CHANGELOG `[Unreleased]` Fixed, entry prefixed "Security:".
  `review defer` remains human-only; no new defer path.

Note: the commit-replay case cannot be observed as a block at the older commit (the gate counts each
reviewer's latest review only), so that case checks the block at HEAD plus the next-step facts and the
governing design, which the answer's commit check alone refuses.

Deferrals recorded in the old answer format stop counting (fail safe; the block stays).

## Touch zones (final)

Unchanged from the brief: all ten zones; `tests/test_review_defer_rounds.py` needed no edit (its forges
go through `_forge_closed_deferral`). No callers outside the zones needed changes (`review_gate`,
`review_rca`, `review_trend`, `review_cli`, `role_prompt_rework` use unchanged names).

## Verification

- `python -m pytest -n 4 -q tests/test_review_defer.py tests/test_review_deferral_agreement.py tests/test_review_defer_rounds.py tests/test_review_next_step.py` — 65 passed
- `python -m pytest -n 4 -q` (full suite) — 5428 passed
- `ruff check specy_road tests scripts`, `specy-road file-limits`, `scripts/check_clones.py`,
  `scripts/check_test_private_imports.py`, `scripts/check_machine_paths.py` — clean

## Added

- `review_deferral.answer_item` — the one wording of a deferred item in the decision answer, shared by `_record` and the predicate so they cannot drift.
- `review_deferral._ITEM_KEYS` / `_items_match` — one-to-one marker ↔ RCA item comparison (equality plus `same_commit`).
- `review_deferral._decision_problems` — the ledger checks (closed, node, kind, `why_now`/answer shape, each item named); an unreadable ledger is a problem (fails safe).
- `review_deferral.deferral_in_effect` — the single predicate (A1).
- `review_deferral.rca_deferral` — marker-beside-an-RCA lookup for `facts`/`governing_rca` (none / in effect / why not), including a guard that the marker names that RCA.
- `review_next_step.facts` branch — `DEFER_APPLIED` only when in effect; otherwise the marker's problem lines join `refused`.
- `tests/test_review_defer.py::bound_ledger` — a ledger entry in `_record`'s shape, used by the forge helpers and the agreement test.
- `tests/test_review_defer.py::_crlf_review`, `_edit_yaml`, `_unrelated`, `_rewrite`, `UNBOUND` — setup and tampers for the new negative cases (sonnet blocking with identical finding text is needed for the reviewer replay).
- `tests/test_review_defer.py::test_a_marker_not_bound_to_its_decision_and_rca_resolves_nothing` — 9 negative cases plus the genuine path (A3).
- `os.utime` in that test — guarantees the RCA is filed after every review so `governing_rca`'s mtime comparison is deterministic.
- Mocks: none.
