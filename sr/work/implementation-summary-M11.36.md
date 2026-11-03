# Implementation summary: M11.36 — A resumed reviewer session may approve a delta it was shown

Base `ea837ec1` was a coordinator checkpoint of the first Composer worker's uncommitted edits (not
reviewed). I kept its policy key, default and module, rewrote the gate and status logic for A2, and
dropped its prompt-side duplicate of the packet text. `origin/WIP/improvements-0-3-1` is merged in
(`b13fa665`, no conflicts).

The second worker's patch (`m1136-main2.patch`, read for reference only) turned up one real gap:
the reviewer preamble always said "This is a fresh session". That is now fixed (see below). I did not
take its other changes:
- a second key name, `reviewer_resumed_delta_approval`;
- a `GateResult.summary()` suffix;
- moving `human_approval_completes` and `commit_trailers` into `review_gate_ready.py`, which is out of
  scope.

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
- **Resumed blocks.** With the key on, a resumed block naming `delta_from` counts as a block. The
  delta rules gate approvals only, so this can only make the gate stricter. When a block is refused
  only for `fresh_session`, the status note says "block", not "approval".
- **Reviewer prompt.** `reviewer_preamble` takes `resumed_delta`. When the reviewer reads its own
  delta packet and the key is on, the line "This is a fresh session" becomes: if you are the resumed
  session that approved the delta's base, set `fresh_session: false`; otherwise this is a fresh
  session. The new `role_prompt.reviewer_lines` builds the packet before the preamble, which keeps
  `build_prompt` under the 80-line function cap.
- **Schemas.** The checkpoint's description of the key was circular ("resumed the session that read
  its delta packet"). It now says which session is resumed and what stays refused.
- **Delta packet.** The **Delta review** section in `review_packet._delta_section` says whether a resumed
  session may approve (key on) or a fresh one is needed (key off).
- **Docs.** `docs/orchestration-review.md` has a new paragraph after the delta-review section: the key,
  its default, what it waives and what it does not, and the four status messages.
- **Reverted from the checkpoint.** In `role_prompt.py`, `delta_session_lines` recomputed `delta_basis`
  and repeated text the appended packet already carries, so I removed it. The checkpoint's `delta_section_lines` move out of `review_packet.py` is also undone:
  `_delta_section` stays in place.

## Touch zones (final list)

These are the brief's zones plus the ones added with `specy-road edit-node M11.36 --add touch_zones=…`
(committed on this branch, along with the registry claim):

- `specy_road/review_gate.py`
- `specy_road/bundled_scripts/review_packet.py`
- `specy_road/bundled_scripts/role_prompt.py`
- `docs/orchestration-review.md`
- `tests/`
- `specy_road/review_resumed_delta.py`: a new module, because `review_gate.py` is at its 400-line cap
- `specy_road/orchestration_config.py`: the key's default in `DEFAULT_POLICY`
- `specy_road/templates/project/schemas/orchestration.schema.json` and
  `sr/schemas/orchestration.schema.json`: `policy` has `additionalProperties: false`
- `specy_road/bundled_scripts/role_prompt_rca.py`: holds `reviewer_preamble`

`specy_road/templates/project/roadmap/orchestration.yaml` lists neither `delta_review` nor this key,
so I left it alone.

## Verification

- `pytest tests/test_resumed_delta_review.py`: 14 passed.
- Red-green, first round: with `review_gate.py` and `review_packet.py` restored to `fa53b678`, all 11
  of that round's tests fail.
- Red-green, this round: with the prompt and resumed-delta modules restored to `63839627`, the
  key-on preamble test and `test_resumed_block_reasons` fail.
- Every test file that references `role_prompt`, `review_packet`, `orchestration_config`, the
  orchestration schema, `review_cli`, `review_gate`, `review_resumed_delta` or `handoff` (66 files):
  857 passed. The full suite before the merge: 3362 passed, 2 skipped.
- `specy-road file-limits`: OK.
- `python scripts/check_test_private_imports.py`: 0 new.
- `specy-road validate`: OK.
- `ruff check` on the changed files: clean. `ruff check specy_road tests scripts` still reports a C901
  in `review_packet_uncommitted_refs.py`, which this leaf does not touch; the error is pre-existing.
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
- Branch in `fresh_only_note` for a block: a block is never held to the delta rules, so the note
  says whether it would count.
- `role_prompt_rca.reviewer_preamble(..., resumed_delta=False)`: the session sentence for a resumed
  delta reviewer.
- `role_prompt.reviewer_lines(...)`: builds the reviewer's preamble and packet. It detects a delta
  round by the `PACKET-<model>.md` that `reviewer_packet` writes only for one, and is split out of
  `build_prompt` to keep that function under its cap.
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
  - `test_delta_packet_says_whether_a_resumed_session_may_approve` (2 params): the packet text and the
    preamble with the key on and off.
  - `test_full_packet_prompt_still_says_fresh_session_when_policy_on`: a full packet keeps the fresh
    preamble.
  - `test_resumed_delta_block_counts_when_policy_allows`: a resumed delta block counts.
  - `test_resumed_block_reasons`: the A2 block wording, with and without `delta_from`.
