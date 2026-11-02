# Implementation summary: M11.8 — delta review packet for small fix rounds

## What changed

- **Policy key** `policy.delta_review` (boolean, **default true**): added to
  `orchestration.schema.json` and to `DEFAULT_POLICY` in `orchestration_config.py`.
  Read from the integration branch like the rest of the policy.
- **The rule** (`review_gate.delta_problem`). A fix round from an approved commit
  `P` to the commit under review `C` may be delta-reviewed only when:
  - the policy is on;
  - `P` is an ancestor of `C` and is not `C` itself;
  - `git diff P..C` touches at most `DELTA_MAX_FILES = 3` paths (both sides of a
    rename count; there is no line limit);
  - every path is a doc or test file (`is_doc_or_test`: `.md/.rst/.txt/.adoc`, a
    path under `tests/`, `test/` or `__tests__/`, `test_*.py`, `*_test.*`,
    `*.test.*`, `*.spec.*`);
  - every path is inside the leaf's touch zones (registry entry first, then the
    node). The leaf's own `work/implementation-summary-<NODE_ID>.md` counts as
    inside, because a fix round nearly always updates it;
  - `compare_integrity(P, C)` has no findings.

  If any check fails, the round gets a full review (A1).
- **Which approval a delta starts from** (`review_gate.prior_approvals` and
  `delta_basis`): the model's latest approval of another commit of the node that
  counted at its own commit. These are read from `history/` plus the live
  `REVIEW-*.md`, oldest filing first. Each record is first checked against the
  brief's acceptance ids with `review_semantic_errors`, because history is loaded
  without them. So an approval missing an acceptance result is never a basis
  (round 3). A record that names `delta_from` is kept only
  when an approval already kept is of that commit and the delta from it qualifies
  (`_delta_why`). So a delta approval the gate rejected can never be the start of a
  later delta that would hide the rejected change. If the policy cannot be read,
  the result is a full review.
- **Packet** (`review_packet.build_packet(prior=…)`): the same sections, computed
  over `P..C` (via the existing `_with_base`). The packet adds a `## Delta review`
  section that tells the reviewer to add `delta_from: "<P>"` and includes that
  reviewer's notes on `P`. The whole diff is inlined (caps 0). A capped diff of a
  delta packet goes to `DIFF-<model>.patch`, so it never overwrites `DIFF.patch`.
- **`review-packet --full`**: stamps `review_gate.FULL_MARK` into `PACKET.md`.
  `delta_problem` returns "`review-packet --full` forces a full review" while
  `PACKET.md` is stamped and is the commit under review's packet. That makes the
  override part of gate eligibility as well as packet selection: no delta packet
  is built and no `delta_from` approval counts (A2, round 3). Rebuilding the
  packet without `--full`, or a new commit, lifts it.
- **Delivery, per reviewer** (`role_prompt.reviewer_packet`): `prompt --role
  reviewer --model M` builds M's delta packet at prompt time when `delta_basis`
  allows it. It writes `work/reviews/<NODE_ID>/PACKET-M.md` and inlines that file;
  otherwise it inlines `PACKET.md`, as before. A stale `PACKET-M.md` is removed
  first, so no reviewer is ever handed another reviewer's delta.
- **Review record**: optional `delta_from` field (quoted SHA) in
  `review-record.schema.json`. Validation comes from the schema, as instructed;
  `review_cli.py` is untouched.
- **Gate** (`evaluate_gate`): an *approval* that names `delta_from` counts only
  when the same model's counting approval of `delta_from` is on file (as kept by
  `prior_approvals`, the same `_delta_why` check), and the
  delta still meets `delta_problem` under the current integration-branch policy.
  When the policy is off, no delta approval counts. Blocks are unaffected.
  Distinct-family counting is unchanged, so both families are still needed (A2).
- **Docs**: a new "Delta review of small fix rounds" section in
  `docs/orchestration-review.md` covers the rule, the policy key, `--full`,
  `PACKET-<model>.md` and `delta_from` (A3).

## Design note on placement

The rule lives in `review_gate.py` rather than `review_packet.py`. The gate must
apply the same rule, and `review_packet` already imports `review_gate`, so placing
it in `review_packet` would create an import cycle.

The delta packet is built in `role_prompt.py` at prompt time rather than written
by `review-packet`, for two reasons:
- `review_packet.py` was at 398 of the 400-line cap;
- the prompt is the only place that knows which reviewer the packet is for.

To stay under the line caps without new modules, I made a few behaviour-neutral
compactions:
- in `review_packet.py`: `_tail`, `_header`, `test_integrity_section`;
- in `review_gate.py`: the `evaluate_gate`/`_eligibility` signatures, the
  `review_files` and `orchestration_config` imports, and the
  `gate_holds_at_head_or_exit` prints.

The output of all of these is unchanged.

## Touch zones (final)

`specy_road/bundled_scripts/review_packet.py`, `specy_road/review_gate.py`,
`specy_road/templates/project/schemas/orchestration.schema.json`,
`docs/orchestration-review.md`, `tests/`,
`specy_road/schemas/review-record.schema.json`,
`specy_road/bundled_scripts/role_prompt.py`, `specy_road/orchestration_config.py`.

## Verification

- `.conda/bin/pytest tests/test_delta_review.py -q`: 12 passed.
  - The round-2 test fails against `review_gate.py` at `c6bb2aea`.
  - The two round-3 tests fail against the three source files at `d1e585af`.
  - All of them pass now.
- `ruff check specy_road tests scripts`: all checks passed.
- `specy-road file-limits`: OK.
- `python scripts/check_test_private_imports.py`: 0 new.

Not run:
- The other related suites (`tests/test_review_packet.py`,
  `tests/test_review_gate.py`, `tests/test_models_and_prompt.py`), because the
  coordinator asked for only the touched test files. The round-1 reviewer re-ran
  them at `c6bb2aea`; this round changed only `review_gate.py`.
- `scripts/check_clones.py`, because pylint is not installed in this environment.

## Known limits and follow-ups (outside the touch zones)

- `delta_from` is self-attested, like `fresh_session`. A reviewer handed a delta
  packet that omits it is counted as a full review. Signed records cover the field.
- The following were not updated because they are outside the zones:
  - `review-record.template.md` (both the scaffold template and `sr/work/`) does
    not mention `delta_from`; the delta packet tells the reviewer instead.
  - `suggested_prompts/*.md` (per CLAUDE.md maintainer hygiene) may want a line
    about `delta_from`.
  - The toolkit roadmap's copy `sr/schemas/orchestration.schema.json` is not
    refreshed. The code validates against the packaged schema.
  - `role_prompt_rca.reviewer_precondition` still names `PACKET.md`, which
    `review-packet` always writes, so the precondition still holds.

## Added

### Helpers
- `review_gate.DELTA_MAX_FILES`, `_DOC_SUFFIXES`, `_TEST_DIRS`: the constants of the A1 rule.
- `review_gate.is_doc_or_test`: classifies a path as documentation or test (A1).
- `review_gate.delta_problem`: the eligibility rule, shared by the packet and the gate (A1, A2).
- `review_gate.prior_approvals`: a model's counting approvals of other commits, so a delta starts only from a real approval (A2).
- `review_gate.delta_basis`: picks the reviewer's latest such approval and applies the rule; an unreadable policy means a full review.
- `review_gate._delta_why`: why a `delta_from` approval does not count, given the model's counting priors. The gate and `prior_approvals` share it, so a rejected delta approval is never a basis (A2, round 2).
- `review_packet._delta_section`: the `## Delta review` header, the `delta_from` instruction and the reviewer's notes (A1).
- `review_gate.FULL_MARK`: the `--full` stamp. It moved from `review_packet` so `delta_problem` can read it; `review_packet` imports it (A2, round 3).
- `delta_problem`: a commit-bound `--full` guard (`PACKET.md` stamped and naming the commit under review), so the gate, `delta_basis` and the prompt all honour it (A2, round 3).
- `prior_approvals`: a `review_semantic_errors(…, acceptance_ids(node))` guard, so an earlier approval missing an acceptance result is no basis (A2, round 3).
- `role_prompt.reviewer_packet`: builds the reviewer's own delta packet and hands it to that reviewer only. It now relies on `delta_basis` for `--full` (round 3).

### Branches and guards
- `evaluate_gate`: an approval with `delta_from` goes through `_delta_why` against `prior_approvals` (A2).
- `prior_approvals`: walks records oldest first and skips a `delta_from` approval that `_delta_why` rejects against the approvals kept so far (A2, round 2).
- `build_packet`: a `prior` parameter for the delta range, and a `full` parameter for the stamp.
- `_diff` / `_capped_diff`: a `patch_name` parameter, so a delta packet never overwrites `DIFF.patch`.
- `review-packet --full` flag (A2).
- `reviewer_packet` removes a stale `PACKET-<model>.md` before choosing which packet to hand over.
- Schemas: `policy.delta_review` (default true in `DEFAULT_POLICY`) and the record's `delta_from` (A1, A2).

### Mocks
- none

### Tests (`tests/test_delta_review.py`)
- `test_doc_and_test_paths`: the doc/test classification.
- `test_an_eligible_delta_counts_for_the_approving_reviewer_and_both_families_are_still_needed`: an eligible delta, and both families still required (A2, A3).
- `test_a_delta_with_a_source_file_needs_a_full_review`: a delta with a source file (A3).
- `test_a_delta_over_three_files_needs_a_full_review`: a delta over three files (A3).
- `test_a_delta_with_an_integrity_finding_needs_a_full_review`: a lost assert (A3).
- `test_a_reviewer_that_did_not_approve_the_earlier_commit_gets_no_delta`: no delta packet and no delta approval for that reviewer; its full review still counts (A2, A3).
- `test_an_ineligible_delta_approval_is_no_basis_for_a_later_delta`: a full approval at P, a rejected delta approval at C1 (a source file), then docs-only C2. The delta basis is not C1, and a `delta_from: C1` approval of C2 does not count (A2, round 2).
- `test_an_earlier_approval_missing_an_acceptance_result_is_no_delta_basis`: an incomplete historical approval yields no delta basis and no delta packet, and a delta approval built on it does not count (A2, round 3).
- `test_the_gate_refuses_a_delta_approval_while_review_packet_full_is_current`: at gate level, a delta approval counts, stops counting after `review-packet --full`, and counts again once the packet is rebuilt without it (A2, round 3).
- `test_policy_off_forces_full_review`: with `delta_review: false`, no delta packet and no delta approval (A2, A3).
- `test_the_prompt_hands_each_reviewer_its_own_packet`: per-reviewer delivery and the delta packet's contents (A1).
- `test_review_packet_full_stops_delta_packets`: `--full` forces the full packet and removes a stale delta packet (A2).
