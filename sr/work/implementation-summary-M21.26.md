# Implementation summary: M21.26 — gate excludes READY authors

## What changed

- `specy_road/review_eligible.py`: `_writers` is now the public `writers(repo_root, node_id, branch)`, returning
  model -> (READY file name, reason). `handoff status` keeps its wording ("executor of the leaf (READY-x.md)" /
  "wrote a fix commit on this leaf (READY-x.md)"). New `reviews_to_judge(repo_root, node, branch, ineligible)`: the
  node's review records the gate judges; a record whose model id is a writer goes to `ineligible` with
  `<model> wrote <READY file> on this leaf; the executor never reviews its own leaf`, before validity, `authored_fix`,
  verdict or signature are looked at (A1). Exact model id only, so another model of the executor's family is judged
  as before (A2).
- `specy_road/review_gate.py`: `evaluate_gate` iterates `reviews_to_judge(...)` (with its `branch`) instead of
  `list_reviews(...)`; module docstring rule list names the new condition. No READY → identical list, so the gate is
  unchanged (A2).
- `specy_road/review_delegate.py`: `delegate` refuses a writer (`DelegateError`, CLI exit 1) right after the target
  resolves, naming the READY file — before the roster/harness setup, packet, lock, RUN file or launch (A3).
- `tests/test_review_gate_ready_author.py` (new, A4).
- `docs/orchestration.md` (## The review gate), `docs/grind-session.md` (the "trusts self-attested authored_fix"
  sentence), `CHANGELOG.md` [Unreleased] Fixed, marked Security (A5).

## Touch zones

Final list unchanged from the brief: `specy_road/review_gate.py`, `specy_road/review_eligible.py`,
`specy_road/review_delegate.py`, `tests/test_review_gate_ready_author.py`, `docs/orchestration.md`,
`docs/grind-session.md`, `CHANGELOG.md`. No call site outside the zones needed changing (callers already pass
`branch` to `evaluate_gate` where they know it; `mark-implementation-reviewed` does).

## File limits

`review_gate.py` (400/400), `docs/orchestration.md` (400/400) and `docs/grind-session.md` (500/500) were already at
their caps at the base commit. To stay net zero: the per-record exclusion lives in `review_eligible.py`
(`reviews_to_judge`), the review_gate docstring's "Policy is read from…" paragraph was rewrapped to the file's
~115-column width (text unchanged, one line fewer), the orchestration.md addition joins the existing paragraph under
"## The review gate", and the grind-session bullet was rewrapped. No text was removed or shortened.

## Verification

- `python -m pytest -q tests/test_review_gate_ready_author.py` — 8 passed.
- Red-green: with the `specy_road/` changes reverted, 5 of the 8 fail (rc4 shape, executor block, signed approval,
  fix author, delegate refusal); the 3 "unchanged behaviour" tests (same family ×2, no READY) pass both ways.
- Related suites (`tests/test_review*`, `test_mark_impl*`, `test_handoff*`, `test_finish*`,
  `test_dynamic_routing_reviewers`, `test_roster_availability`, `test_prompt_channel_cli_run`,
  `test_milestone_full*`; 70 files) with `-n 4` — 1287 passed.
- `ruff check specy_road tests scripts` — clean; `specy-road file-limits` — OK.

## Notes for reviewers

- A writer's record is excluded even when it is invalid (e.g. `authored_fix: true`) or stale: it lands in
  `ineligible` rather than `invalid`/`stale`. Consumers of `ineligible` only read `path.name` and `data["model"]`.
- READY authorship stays cooperative attestation (an unsigned file); the docs say so. Out of scope per the sheet.

## Added

- `review_eligible.writers` (renamed from `_writers`, value now `(READY name, reason)`): the one helper A1 asks for;
  the file name is needed for the gate's and delegate's sentence.
- `review_eligible.reviews_to_judge`: the gate's record list minus writers' records (which it routes to
  `ineligible`); keeps `review_gate.py` within its 400-line cap.
- Guard in `review_delegate.delegate` (non-chore branch): refuses a writer before any write (A3).
- `tests/test_review_gate_ready_author.py`:
  - `test_rc4_shape_executor_approval_does_not_count_and_gets_no_trailer` — the D3 regression; also checks
    `mark-implementation-reviewed --yes` refuses and writes no `Reviewed-by: opus` trailer.
  - `test_executor_block_is_ineligible_and_does_not_hold_the_gate` — plan-review row G-R5 (block).
  - `test_executor_signed_approval_is_ineligible` — plan-review row G-R5 (signed approval; first shows it counts
    without a READY, so the signature verifies). Skipped without `ssh-keygen`, as `test_review_signing.py` is.
  - `test_another_model_of_the_executors_family_counts` (parametrized distinct families off/on) — A2.
  - `test_a_fix_author_is_excluded` — A4 fix author.
  - `test_no_ready_leaves_the_gate_unchanged` — A2/A4 no READY.
  - `test_delegate_refuses_a_ready_author_and_writes_nothing` — A3 (no file under the leaf's reviews dir changes,
    the fake harness is never called).
- Mocks: none (the delegate test uses the existing fake harness from `tests/review_delegate_helpers.py`).
