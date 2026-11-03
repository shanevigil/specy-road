# Implementation summary: M11.38 — handoff status says who can still supply a missing approval

## What changed

When the review gate is not met, `specy-road handoff status <NODE_ID>` now prints, directly below the
`policy:` line, one line per roster entry (the `human` entry included) saying whether it can supply a
counting approval at the commit under review, and for each excluded one, why:

```
  policy: 1/2 distinct-family approvals, 0 block(s): not met
  who can still supply a counting approval at this commit:
    human (human): can approve, interactively with `specy-road mark-implementation-reviewed M1.1`
    opus (anthropic): its approval counts
    sonnet (anthropic): excluded — same family (anthropic) as opus's approval, which already counts
    sol (openai): can approve (file with `specy-road review record`)
    composer (cursor): excluded — not a reviewer role (roles: executor) and no active substitution
```

`--json` carries the same rows as `reviewer_eligibility` (`model`, `family`, `eligible`, `reason`) on each
claimed node; the list is empty once the gate is met, when the config fails to load, or when no commit resolves.

Reasons, checked in this order with the gate's own helpers (`is_rostered_reviewer`/`substitute_for`,
`may_handle`, the gate's `invalid`/`ineligible` lists and counted families):

- **A1** not a reviewer role (and no active substitution); sensitivity outside `may_process`; under
  `signed_reviews`, no `public_key` on the roster entry;
- **A1** executor of the leaf: the model filed a READY on the leaf before any valid review of its own on it;
- **A1** wrote a fix commit on this leaf: the model filed a READY after its first valid review on the leaf
  (current or under `history/`, compared by file mtime), so it reviewed and then fixed. These two come from
  the leaf's READY files, as `review_rca.rca_parties` already identifies the leaf's executors;
- **A1** rejected record: its record at this commit is invalid, or is listed by the gate as not counting;
  the gate's reason is quoted;
- **A1** same family as an approval already counted (only under `reviewers_distinct_families`).

Every exclusion is checked before a model is listed as counting, so a READY author is excluded even when the
gate counts its approval (the gate trusts the record's `authored_fix: false`), and under a distinct-family
policy only the first counted approval of a family reads as counting; a later one from the same family is
excluded as same-family. A model whose record blocks is listed as able to approve on re-review. The gate itself
is unchanged: this only explains roster entries.

### Review fix round (gpt-6.1-sol block)

`reviewer_eligibility` listed a model whose approval the gate counted as eligible before checking the READY-author
exclusion. All exclusions now run first. Checking every other exclusion against that shortcut found one more:
a second same-family approval read as counting, so `_same_family` now excludes a counted model when an earlier
counted approval has its family. `_writers` now tells executor from fix author by filing time rather than by
whether the model ever reviewed, so an executor that filed an approval is labelled the executor.

- **A2** `tests/test_review_eligible.py` covers the human listed as eligible, an executor and a fix
  author excluded (author-excluded), a same-family reviewer excluded, a rejected record, and the text
  placement below the policy line plus the empty list once the gate is met. Two regressions from the review:
  a READY author holding a counting approval is excluded with the author reason, and a second same-family
  counting approval is excluded as same-family.

## Touch zones

`review_cli.py` was at 399 lines and `review_gate.py` at 400 (the `file-limits` cap), so the new code lives in a
**new module, `specy_road/review_eligible.py`**; please add it to this leaf's touch zones. `review_cli.py`
gains one import line and changes two existing lines (now 400 lines); `review_gate.py` is unchanged.
Final list: `specy_road/review_eligible.py`, `specy_road/bundled_scripts/review_cli.py`, `tests/`.

Not changed (outside the touch zones): `docs/orchestration-review.md` describes `handoff status` output and
could mention the new lines.

## Verification

- `python -m pytest -n auto -q tests/test_review_eligible.py tests/test_review_cli.py tests/test_review_gate.py
  tests/test_integrity_gate.py tests/test_milestone_full_review.py tests/test_ready_command.py
  tests/test_review_delegate.py tests/test_review_evidence.py tests/test_review_hardening.py
  tests/test_review_file_case.py tests/test_review_files.py tests/test_review_rca.py tests/test_review_signing.py
  tests/test_review_round6_evidence.py tests/test_session_presence.py tests/test_worker_cli.py
  tests/test_worktree_paths_agree.py`: 229 passed (after the fix round)
- `specy-road file-limits`: OK
- `ruff check` on the changed Python files (C901): passed

## Added

- `specy_road/review_eligible.py` — new module (the CLI and gate files are at the line cap).
- `_writers` — maps READY authors to "executor of the leaf" or "wrote a fix commit on this leaf" (a READY written after the model's first valid review on the leaf, by mtime).
- `_rejected` — maps a model to the gate's reason its record at this commit is invalid or does not count, skipping models that already count.
- `_roster_reason` — role/substitution, `may_process` sensitivity and `signed_reviews`/`public_key` checks, reusing the gate's helpers.
- `_same_family` — exclusion when a distinct-family policy already counts that family from another model (for a counted model, only from an earlier counted approval).
- `_eligible_text` — wording for an eligible entry: re-review when its record blocks, the interactive command for `human`, `review record` otherwise.
- `reviewer_eligibility` — one row per roster entry; returns `[]` when the gate is met, the config errs or no commit resolves (guard: nothing to explain then).
- `eligibility_lines` — text rendering under the policy line.
- `review_cli._node_status` — new `reviewer_eligibility` key; `_render` — appends `eligibility_lines` after the policy line.
- Tests (`tests/test_review_eligible.py`, no mocks): `test_human_is_listed_as_able_to_supply_the_missing_approval`, `test_same_family_reviewer_is_excluded`, `test_executor_and_fix_author_are_excluded`, `test_rejected_record_is_excluded_with_the_gates_reason`, `test_ready_author_with_a_counting_approval_is_still_excluded`, `test_second_same_family_approval_is_excluded_not_counting`, `test_text_lists_reviewers_below_the_policy_line_until_the_gate_is_met`; local helpers `_run`, `_review`, `_ready`, `_rows`.
