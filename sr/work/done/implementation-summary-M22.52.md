# Implementation summary: M22.52 (`review-fix-check`)

After a block, the executor names the one block a fix commit answers with `specy-road ready --fix-of <model>@<sha>`;
the other family's approval of `<sha>` then counts at the fix commit under the A1 conditions, and the blocker's
reviewer prompt gets a fix-check section (A2).

## What changed

- `specy_road/schemas/handoff.schema.json`: optional `fix_of`, pattern `^[A-Za-z0-9._-]+@[0-9a-f]{7,40}$`;
  `additionalProperties` stays false.
- `specy_road/review_gate_ready.py`: `ready --fix-of MODEL@SHA` writes `fix_of` into READY; the existing
  pre-write schema check refuses a malformed value.
- `specy_road/review_gate.py` (beside `count_at_later_commit`, which with `review_bookkeeping.py`,
  `delta_problem`, `DELTA_MAX_FILES` and `delta_from` is unchanged):
  - `FixOf`, `round_records`, `fix_of_for`: the block a current, valid READY's `fix_of` names (READY at the commit
    under review; each model's latest record at `<sha>`).
  - `fix_carry_problem` (+ `_fix_range_problem`, `_tier_problem`, `zones_at`): the conditions — the named record
    is a block and the round's only block; `<sha>` is the fix's sole parent; every path of `<sha>..<fix>` (both
    rename sides, prefix-rebased) is in the zones committed at `<sha>` (registry claim, else node) or the leaf's
    summary/review files; the integration ref's sheet (`git show <ref>:./<planning_dir>`) has `## Tier`
    plain or behavioural; `delta_review` not false, no current `--full` stamp, no integrity finding.
  - `_carried_by_fix`: lets a stale other-family approval at `<sha>` count; a refusal goes to the new declared
    `GateResult.carry_refused` field (already used dynamically by `review_bookkeeping`), so the `policy:` line of
    `handoff status` names why.
  - `_blocker_must_approve`: once an approval is carried, a gate problem until the blocker approves the fix
    commit; a new block keeps the gate unmet as before.
  - `latest_ready` is read once, before the loop (it was read after it).
- `specy_road/bundled_scripts/role_prompt.py` (`fix_check_section`) and `role_prompt_rca.py`
  (`fix_check_lines`): the named blocker's reviewer prompt lists each findings string of its block and the exact
  `git diff <sha>..<fix>`, asks for a verdict on each and new findings only where the fix broke something.
- Parity: `tests/parity/command_map.yaml` row for `ready --fix-of`; `specy-road__ready.txt` golden regenerated.
- `docs/orchestration-review.md` (new section "Fix check after a block"), `CHANGELOG.md` [Unreleased].

Touch zones: confirmed; no file outside them changed. No file-limits cap is approached (review_gate.py 564 lines).

## Fix round 1 (gpt-6.1-sol block at c9ca18ed)

Both findings had one cause, class **"a carried approval's carry is not a recorded fact"**: later steps inferred
it (the delta rule re-judged the record at the fix commit; the blocker rule fired on any older approval, including
a bookkeeping carry). Design change: `_carried_by_fix` records each carry in `GateResult.fix_carried`, and the new
`_judged_at` returns the commit a record is judged at (the commit under review, or the blocked commit for a fix
carry). `evaluate_gate` uses that commit for `prior_approvals`, `_delta_why` and `fresh_only_note`, and
`_blocker_must_approve` fires only when a counted approval is in `fix_carried`. `evaluate_gate` has the same
branch count as at the merge base (`if not count_at_later_commit: continue` became `if _judged_at(...) is None:
continue`). Docs say a carried approval is judged as at the blocked commit.

## Probes

- Carried `delta_from` approval (Q full, P delta from Q, sol blocks P, code fix F): failed at c9ca18ed, now carries (carry test `delta=True`, 6 cases).
- Bookkeeping carry + `fix_of` naming a non-blocker (summary-only fix, `fix_of sonnet@P`, sol approves F): failed at c9ca18ed (`sonnet must approve`), now identical to the gate without `fix_of` and met.
- Every bad-`fix_of` row (absent, malformed, stale READY, approver, bookkeeping) now compares the whole gate outcome (passed, approvals, blocks, stale, problems) with the same state after deleting `fix_of` from READY: equal.
- `fresh_only_note` (same class: judged at `result.commit`): now given the judged commit; for every non-carried record that commit is `result.commit`, so unchanged.
- `_eligibility` checks (reruns, notes, signature, routing, model mismatch, guidance, family): do not read the commit; unaffected.
- `review_semantic_errors` / acceptance ids: from the current node, the same for both commits; unaffected.
- `unmet_strong`, `verifier_gate_problems`, `executor_blocked_gate_problems`, `integrity_gate_problems`, `pin_problem`: judge the commit under review, which is what the gate opens; correct to leave.
- `policy_line` "carried from an older commit": keyed on the record's commit, true for both carries; correct.
- `apply_deferrals` / `apply_operator_decisions`: act on blocks only; a fix carry adds only approvals; unaffected.
- Prompt `fix_check_section`: reads the block, not carries; unaffected.

## Notes for reviewers

- `ready --help` does not cite the doc path: `tests/test_cli_help_text.py` refuses unshipped doc paths in help.
- The gate applies no path floor (`sr/tools/tier.py`'s), per the sheet's accepted limits.

## Gates run

- `pytest -n 4` (full suite): 7100 passed, 18 skipped, 1 failed before the help-text fix
  (`test_cli_help_text.py[ready -h]`), then the affected files re-run green.
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood`,
  `specy-road file-limits`, `ruff check`, `scripts/check_public_hygiene.py`: pass.
- Mutation checks: carry disabled -> the carry rows fail; `_blocker_must_approve` removed -> the
  `reviewers_required: 1` carry rows fail.

## Added

- `review_gate.FixOf` (dataclass): one value for the named block, read by the gate and the prompt.
- `review_gate.round_records`: each model's latest record at a commit (block and only-block checks).
- `review_gate.fix_of_for`: READY `fix_of` -> `FixOf`, shared by gate and prompt.
- `review_gate.zones_at`: the zones committed at `<sha>`, so zones widened later do not count.
- `review_gate._fix_range_problem`: sole-parent and in-zone path checks.
- `review_gate._tier_problem`: integration-branch sheet tier; ref unresolved / sheet missing / no tier / other tier branches, each reached by a tier-unknown or trust row.
- `review_gate.fix_carry_problem`: the A1 condition list (block, only block, range, tier, delta_review, `--full`, integrity).
- `review_gate._carried_by_fix`: the carry beside `count_at_later_commit`; sibling-repository guard reached by the `sibling repositories` policy row.
- `review_gate._blocker_must_approve`: the carried approval alone never opens the gate; keyed on `fix_carried` (round 1).
- `GateResult.fix_carried` field (round 1): records each fix carry, so later steps do not infer it.
- `review_gate._judged_at` (round 1): the commit a record is judged at; replaces the inline count/carry branch.
- `GateResult.carry_refused` field: declared what `review_bookkeeping` already set dynamically.
- `review_gate._TIER`, `FIX_CARRY_TIERS`: the tier pattern (as `sr/tools/tier.py`) and the tiers that carry.
- `ready --fix-of` option and the `fix_of` schema property: A1.
- `role_prompt.fix_check_section`, `role_prompt_rca.fix_check_lines`: A2 prompt section.
- Mocks: none.
- Tests, `tests/test_delta_review.py`: `fix_round` fixture (public, reused by the prompt test), `_ready`, `_carried`, `_refused`, `_status`, `_mv`, `_malformed`, `_two_commits`, `_sibling`, `_no_sheet_on_dev` helpers; `_file` gains `findings`; rows: carry/blocker approves/new block (x required 2-distinct and 1), trust, tier unknown (4), out of zone (3), widened zones, bad fix_of (4), `ready` refuses malformed `--fix-of`, two blocks / two fix commits, policy (delta_review off, `--full`, integrity, sibling).
- Tests, round 1: `fix_round(delta=...)` and the carry test's `delta` parameter (carried delta approval); `_outcome` and `_summary_only` helpers; the bad-`fix_of` test now compares against the gate with `fix_of` removed and gains the bookkeeping-carry row.
- Tests, `tests/test_role_prompt_reviewer.py`: prompt row for the blocker and for the approver.
