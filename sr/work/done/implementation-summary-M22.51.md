# Implementation summary: M22.51 `operator-decision-record`

Built on w-0221's commits `1f66a31e` (command, ledger, schemas, gate, parity rows, help goldens, tests) and the
coordinator's `6a73dbd2` (docs section, rc3 dry-run golden, review-gate decision-table rows). This round added
`d729e99f`: the principles amendment in both copies and the CHANGELOG `[Unreleased]` entry.

## What changed

- **A1 / A2 — command:** `specy-road review operator-decision` in the new module `specy_road/review_override.py`,
  registered in `review_cli.py`. Operator form (`--quote`, `--session`) and coordinator form (`--rule`, two `--rca`,
  two `--alignment`, `--limit`, `accept-with-limits` only). Its own role check runs before any write; refusals for
  children, unresolved commit, empty quote/session, unset git identity, rule (missing, expired, not a
  `standing-rule`), integration-branch sheet tier (none or trust boundary), evidence families/parties, no counted
  block and limits (each counted findings string named by exactly one `--limit`).
- **Ledger:** `decisions add --kind standing-rule` (`R#` ids, `--why` required, `--expires` honoured); never an open
  question, never a routing preference; closes with `--answer` alone. Both `decisions.schema.json` copies gain
  optional `decided_by` (operator|coordinator) and the `standing-rule` kind.
- **A3 — gate:** `GateResult.accepted` and `shortfall_settled`; `apply_operator_decisions` runs after deferrals and
  honours only a closed `decided_by` decision of the node whose answer names the marker's commit, under the existing
  bookkeeping carry. It settles only named blocks and the named shortfall (never under `signed_reviews: true`); a
  marker without its entry settles nothing. Status and list print the accepted line through `gate.summary()`.
- **Principles 6 and 7** (both copies) name the operator decision record beside the interactive approval. The
  wording of §7 keeps the phrase `tests/test_review_round6_docs.py` asserts.
- **Docs / CHANGELOG:** `docs/orchestration-review.md` "Operator decision"; one `[Unreleased]` Added entry.
- **Parity:** `command_map.yaml` rows; goldens for `review`, `review operator-decision`, `decisions add`; the rc3
  dry-run golden now lists `would write schemas/decisions.schema.json`; `gate_rows.yaml` tables the new
  `shortfall_settled` branch with an approve row and a `signed_reviews` refusal row (new `operator` step).

## Design choice for the reviewers

The gate reads the decision from the working-tree ledger and, failing that, from the ledger committed on the
integration branch: `mark-implementation-reviewed` runs on the leaf branch and refuses an uncommitted ledger, and a
ledger commit on the leaf branch would end the bookkeeping carry. The stamp test covers this.

## Touch zones

The listed zones are accurate; no file outside them changed.

## Verification

`pytest -n 4` full suite: 7107 passed, 17 skipped, 1 failed before the §7 rewording (the round-6 docs assertion),
all pass after it. `ruff`, `file-limits`, `validate` / `export --check` / `digest --check` on the dogfood fixture pass.

## Fix round 1 (gpt-6.1-sol, R1)

Merged `origin/WIP/improvements-0-3-1` first (no conflicts). Class: a launch-role value that is set but is not
exactly `coordinator` (empty, whitespace, other case, padding) was normalised to "unset" or "coordinator" and
accepted. Fix at the cause: `role_refusal` now has one rule, stated in its docstring, the module docstring and
`docs/orchestration-review.md`: unset is the manual coordinator, and the only accepted set value is exactly
`coordinator`. No normalisation remains, and no branch was added (the condition replaced the old one).

## Probes

- Every reader of `SPECY_ROAD_ORCHESTRATION_ROLE` in this change (`grep ROLE_ENV specy_road/review_override.py`):
  only `role_refusal`, called once by `cmd_operator_decision` before any write for both forms. Fixed there.
- Both forms (operator and `--rule`) share that one call: confirmed, so the coordinator form is covered too.
- Other `.lower()` / `.strip()` normalisation in the module: only `sheet_tier`, which parses the sheet's tier; its
  leniency makes more sheets read as trust boundary (more refusals), so it widens no authority. Left as is.
- The help golden for `review operator-decision` does not describe the role; no change needed.
- Red-green: with the old `role_refusal`, the four new cases `role_empty`, `role_whitespace`, `role_uppercase`,
  `role_padded` fail (4 failed); with the fix all pass.

## Added

- `specy_road/review_override.py` (module): the command, its refusals, and the gate hook; kept apart so
  `review_gate.py` and `review_cli.py` stay under the file limits.
- `apply_operator_decisions`, `honoured`, `_markers`, `_ledgers`: the gate reads a decision only through its marker
  and its closed entry, at its commit or across bookkeeping-only commits (A3).
- `role_refusal`, `_form_problem`, `_recorder`, `_rule_problem`, `_tier_problem`, `_cited`, `evidence_problem`,
  `_limit_problem`, `_coordinator_problem`, `_blocks_to_settle`: one guard per A1/A2 refusal, each reached by a
  row of `test_refusals_write_nothing` / `test_the_coordinator_form_refuses` / `test_cited_evidence_must_be_a_project_file`.
- `finding_texts`, `block_item`, `shortfall_text`, `accepted_line`, `marker_path`, `sheet_tier`, `_answer`, `_entry`,
  `_fail`: wording and paths shared by the writer and the gate reader.
- `GateResult.accepted`, `GateResult.shortfall_settled` and the branches in `passed` / `summary` / `problems`: the
  settled shortfall and the accepted lines (A3).
- `decisions.STANDING_RULE`, `standing_rule_active`, `_open_unexpired` (split out of `preference_active`), `kind`
  parameter of `add_preference`, standing-rule branches in `open_questions` and `close_entry`, and the
  `decisions_cli` standing-rule form check: `decisions add --kind standing-rule` (A2).
- Test step `Leaf.operator` in `tests/parity/review_gate/test_review_gate_decision_table.py` and two rows in
  `gate_rows.yaml`: the decision-table check requires every new gate branch to be tabled.
- `tests/test_review_override.py`: one test (parametrized where the sheet's table has variants) per test-table row:
  block/shortfall, bookkeeping, code commit, later block, marker only / other decision, role, identity, trust rule,
  rule, evidence, limits, no block, other gate failures, stamp. No mocks; role env cleared with `monkeypatch`.
- Constitution and CHANGELOG text: required by A3.
- Fix round 1: four `test_refusals_write_nothing` cases (`role_empty`, `role_whitespace`, `role_uppercase`,
  `role_padded`) for R1; no helper, branch or guard added.
