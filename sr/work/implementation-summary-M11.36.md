# Implementation summary: M11.36 — A resumed reviewer session may approve a delta it was shown

Base `ea837ec1` was a coordinator checkpoint of a terminated worker's uncommitted edits (not reviewed).
This round keeps its policy key, schemas and module, rewrites the gate and status logic for A2, and
drops its prompt-side duplicate. The leaf's diff is `fa53b678..HEAD`.

## What changed

- **A1, policy key.** `policy.reviewer_resumed_delta` (default `false`, in `DEFAULT_POLICY` and both
  orchestration schemas). With the key on, `reviewer_fresh_session` is waived only for a record naming
  `delta_from`. Such an approval then goes through the existing M11.8 path unchanged: `evaluate_gate`
  applies `_delta_why`, and `prior_approvals` applies `delta_problem`. So it counts only under the delta
  rules, and it can serve as the basis of the next delta. Any other record with `fresh_session: false`
  is still refused. The record's `delta_from` plus its `commit` name the delta it read
  (`delta_from..commit`); no new record field was added.
- **A2, handoff status.** `_eligibility` now runs the other checks before the session check (rerun,
  notes, signature, family). When `fresh_session` is the **only** failure, `evaluate_gate` replaces the
  reason with `fresh_only_note`. That note says it is the only reason, then gives one of four outcomes:
  - the resumed delta would count with the key on;
  - it would still not count, and why;
  - a resumed delta naming `delta_from: <sha>` would count (adding "with the key" while it is off);
  - no resumed delta would count, and why.

  When another check fails too, the reason lists `fresh_session` first, then that check. `handoff status`
  shows these reasons through the existing `gate.problems()`; `review_cli.py` is unchanged.
- **Delta packet.** The **Delta review** section in `review_packet._delta_section` says whether a resumed
  session may approve (key on) or a fresh one is needed (key off).
- **Docs.** `docs/orchestration-review.md` has a new paragraph after the delta-review section: the key,
  its default, what it waives and what it does not, and the four status messages.
- **Reverted from the checkpoint.** In `role_prompt.py`, `delta_session_lines` recomputed `delta_basis`
  and repeated text the appended packet already carries, so `role_prompt.py` is back to base (no net
  change). The checkpoint's `delta_section_lines` move out of `review_packet.py` is also undone:
  `_delta_section` stays in place.

## Touch zones (final list)

Zones named in the brief that this leaf changed: `specy_road/review_gate.py`,
`specy_road/bundled_scripts/review_packet.py`, `docs/orchestration-review.md`, `tests/`.
`specy_road/bundled_scripts/role_prompt.py` has no net change.

The leaf's diff also contains these paths outside the brief's zones. All of them come from the
checkpoint commit `ea837ec1`. Please add them to the touch zones:

- `specy_road/review_resumed_delta.py`: a new module. `review_gate.py` is at the 400-line cap. I rewrote
  this file this round.
- `specy_road/orchestration_config.py`: one line, `reviewer_resumed_delta: False` in `DEFAULT_POLICY`.
  Unchanged this round.
- `specy_road/templates/project/schemas/orchestration.schema.json` and `sr/schemas/orchestration.schema.json`:
  the `policy` object has `additionalProperties: false`, so the key cannot be set without them.
  Unchanged this round.

`specy_road/templates/project/roadmap/orchestration.yaml` lists policy keys but does not list this new
key. It is outside the zones, so I left it alone.

## Verification

- `pytest tests/test_resumed_delta_review.py`: 11 passed. With `review_gate.py` and `review_packet.py`
  restored to `fa53b678`, all 11 fail (red-green).
- `pytest -n auto` (full suite): 3362 passed, 2 skipped.
- `specy-road file-limits`: OK. `review_gate.py` and `review_packet.py` are each at 400 lines.
- `python scripts/check_test_private_imports.py`: 0 new.
- `ruff check specy_road tests scripts`: one C901 in `review_packet_uncommitted_refs.py`, a file this
  leaf does not touch. The error is pre-existing. The files this leaf changed pass `ruff check`.
- `scripts/check_clones.py` was not run: `pylint` is not installed in this environment.

## Added

- `review_resumed_delta.FRESH_SESSION` / `RESUMED_KEY`: the session refusal text and key name. The gate
  compares against `FRESH_SESSION` to spot a fresh-only refusal.
- `review_resumed_delta.fresh_session_problem(policy, data, other)`: the session check plus the waiver
  for an approval naming `delta_from`. It combines with the other checks' reason, so a fresh-only
  refusal can be told apart (A1, A2).
- `review_resumed_delta.fresh_only_note(...)`: the A2 status text for a fresh-only refusal, saying
  whether a resumed delta would count and under which policy.
- `review_resumed_delta.resumed_delta_on(root)`: reads the key from the effective policy, as the gate
  does, and fails closed. The packet section uses it.
- Guard in `review_gate._eligibility`: the session check now runs last, and the family check folds
  into `why`, so "only reason" is true when it is reported.
- Branch in `review_gate.evaluate_gate`: on a fresh-only refusal, report `fresh_only_note` in place of
  the bare reason.
- Branch in `review_packet._delta_section`: a resumed-session sentence when the key is on, a
  fresh-session sentence when it is off.
- Mocks: none.
- Tests in `tests/test_resumed_delta_review.py`:
  - `test_resumed_delta_approval_counts_when_policy_allows`: A1, allowed.
  - `test_resumed_delta_approval_still_meets_the_delta_rules`: A1, counts only under M11.8's rules.
  - `test_resumed_delta_refused_when_policy_off`: A2, refused with the policy off; checks the gate
    reason and `handoff status --json` problems.
  - `test_policy_off_says_when_the_delta_would_not_qualify_anyway`: A2, "would still not count".
  - `test_resumed_full_review_still_needs_fresh_session`: A1/A2, resumed full review with the key on;
    checks the gate and `handoff status`.
  - `test_resumed_full_review_names_the_key_when_policy_off`: A2, the key is named when it would help.
  - `test_resumed_review_without_an_earlier_approval_needs_a_fresh_full_review`: A2, no basis.
  - `test_another_failing_check_is_not_reported_as_fresh_session_only`: A2, "only" is not claimed
    falsely.
  - `test_resumed_delta_approval_is_a_basis_for_the_next_delta`: A1, `prior_approvals` honours the
    waiver.
  - `test_delta_packet_says_whether_a_resumed_session_may_approve` (2 params): the packet text with the
    key on and off.
