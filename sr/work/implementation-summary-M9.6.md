# Implementation summary for M9.6

## Summary

With `policy.integrity_gate: true` in `roadmap/orchestration.yaml` (default false), the review gate now
turns every `specy-road integrity` finding for the commit under review into a gate problem unless the
node's new optional `planned_test_changes` lists that exact finding line. Both the switch and the
declarations are read from the integration branch (`policy_source`'s ref): the switch through the
existing `effective_config(repo_root, ref)` read, the declarations through
`load_roadmap_nodes_at_ref(repo_root, ref)`. A declaration committed only on the leaf branch (or present
in the working-tree node) does not clear its finding; the same declaration committed on the integration
branch does. The merge base for the findings is `git merge-base <integration ref> <commit under review>`.

The problems are appended to `GateResult.verifier_problems`, the same list M9.4's `blocked_on` problems
use, so `passed`, `problems()`, `human_approval_completes`, `handoff status`,
`mark-implementation-reviewed --yes` and `finish-this-task` (`gate_holds_at_head_or_exit`) all act on
them without further wiring. Each prints as
`integrity (undeclared): <finding line> — not in <ID>'s planned_test_changes on <ref>`.

With the policy off or absent, `integrity_gate_problems` returns `[]` before running anything, so the
gate result is unchanged (A4). With it on and no integration ref or merge base, the gate fails closed
with one problem.

The pickup prompt (`do-next-available-task`, `work/prompt-<ID>.md`) gains a `## Planned test changes`
section listing the leaf's declarations (or `_none_`) and stating that any other test removal or
weakening is a `blocked_on` stop until the coordinator amends `planned_test_changes` on the integration
branch. The section is emitted whether or not the review gate is on, since A5 does not condition it.

## Changes

- `specy_road/integrity_gate.py` (new): `planned_test_changes(repo_root, ref, node_id)` and
  `integrity_gate_problems(repo_root, policy, node_id, commit, ref)`.
- `specy_road/review_gate.py`: `evaluate_gate` appends `integrity_gate_problems(...)`; module docstring
  mentions it. 342 lines (cap 400).
- `specy_road/bundled_scripts/do_next_prompt.py`: `_planned_test_changes_lines(node)`, included before
  `## Instructions`.
- `specy_road/templates/project/schemas/roadmap.schema.json`: optional node `planned_test_changes`
  (array of non-empty strings).
- `specy_road/templates/project/schemas/orchestration.schema.json`: `policy.integrity_gate` (boolean).
- `sr/schemas/`: `specy-road refresh-schemas --repo-root sr`. Besides the two fields above this also
  brought in schema text that earlier leaves had added to the templates without refreshing `sr/`
  (`land_check_cmd` in `git-workflow.schema.json`, the two `escalate_*` policy keys in
  `orchestration.schema.json`); refresh copies the templates whole.
- `tests/fixtures/specy_road_dogfood/schemas/roadmap.schema.json`: copied from the template (was
  byte-identical before), because gate test repos copy their schemas from the fixture.
- `docs/roadmap-authoring.md`: `planned_test_changes` row in the optional-fields table. The file was at
  its 400-line cap, so one hard-wrapped paragraph under "Five questions the planning sheet must answer"
  was joined onto one line (renders identically) to make room.
- `docs/orchestration-review.md`: new `## The integrity gate` section; the M9.6 forward reference in the
  test-integrity section now points at it.
- `suggested_prompts/bootstrap-roadmap.md`: the only prompt that enumerates node fields and policy keys;
  names `planned_test_changes` and `policy.integrity_gate`.
- `CHANGELOG.md`: one `[Unreleased] / Added` entry.
- `tests/test_integrity_gate.py` (new).

Touch zones: accurate as listed. Not touched (outside the zones, noted for the coordinator):
`orchestration_config.DEFAULT_POLICY` does not gain an `integrity_gate: False` key (the gate reads it
with `.get`), and `specy-road prompt --role executor` (`role_prompt*.py`) does not carry the new lines;
A5 names the prompt written at pickup, which is `do_next_prompt.py`.

## Verification

- `pytest tests/test_integrity_gate.py` — 14 passed.
- `pytest` (full suite) — 2666 passed, 2 skipped (16m18s).
- `ruff check specy_road tests scripts` — all checks passed.
- `specy-road file-limits` — OK.
- `python scripts/check_clones.py --pylint <pylint 4.1.3 in a scratch venv>` — 0 new.
- `python scripts/check_test_private_imports.py` — 0 new.
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood` — OK;
  `specy-road validate --repo-root sr` — OK. The fixture's ignored `.specyrd/` cache those runs wrote
  was removed with `git clean -fdX tests/fixtures` before `pytest`.

## Walkthrough

1. `specy_road/integrity_gate.py` — the whole mechanism (one read of policy, one of the node at the ref).
2. `specy_road/review_gate.py`, end of `evaluate_gate` — the single call site.
3. `tests/test_integrity_gate.py` — A3 is `test_declaration_on_the_leaf_branch_does_not_clear_the_finding`
   (passes the leaf's own declared node, as `resolve_target` would load it) and
   `test_declaration_on_the_integration_branch_clears_the_finding`.

## Added

### Helpers
- `integrity_gate.planned_test_changes` — reads the node's declarations from the integration ref only, so a leaf-branch declaration cannot waive a finding (A2, A3).
- `integrity_gate.integrity_gate_problems` — one problem per undeclared finding when the policy is on; `[]` when off, so A4 holds.
- `do_next_prompt._planned_test_changes_lines` — the pickup prompt's declaration list and `blocked_on` stop rule (A5).

### Branches or guards
- `integrity_gate_problems`: early `[]` when `policy.integrity_gate` is falsy or there is no commit — keeps the gate unchanged with the policy off (A4) and matches the gate's existing "no commit" problem.
- `integrity_gate_problems`: a problem when there is no integration ref or merge base — fails closed rather than passing a commit it cannot compare.
- `planned_test_changes`: non-string entries ignored, unreadable roadmap at the ref means no declarations — fails closed.

### Mocks
- none

### Tests (`tests/test_integrity_gate.py`)
- `test_undeclared_finding_blocks_an_approved_gate` — A2: an approved gate fails on an undeclared removal.
- `test_declaration_on_the_leaf_branch_does_not_clear_the_finding` — A3, leaf-branch case.
- `test_declaration_on_the_integration_branch_clears_the_finding` — A3, integration-branch case.
- `test_gate_off_or_absent_ignores_findings` (3 params: no file, no key, `false`) — A4.
- `test_gate_switched_on_only_on_the_leaf_branch_is_not_read` — A2 "read from the integration branch like the rest of the policy".
- `test_no_integration_ref_fails_closed` — the fail-closed guard above.
- `test_handoff_status_prints_undeclared_findings` — A2 handoff status output.
- `test_mark_reviewed_yes_refuses` — A2 `mark-implementation-reviewed --yes`.
- `test_finish_refuses_once_the_integration_branch_turns_the_gate_on` — A2 `finish-this-task`, through its public `main`.
- `test_schemas_accept_the_new_fields` — A1, both schemas (and a non-boolean `integrity_gate` is rejected).
- `test_pickup_prompt_lists_planned_test_changes` (2 params: none / one) — A5.
