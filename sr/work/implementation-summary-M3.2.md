# Implementation summary for M3.2

## Summary

`specy-road handoff status` no longer calls a claimless leaf's records "leftover"
or points at the pushing pickup. A leaf with READY/REVIEW files under
`work/reviews/<ID>/` but no registry claim is reported as `unclaimed — no commit
under review`, with each READY file (ok/INVALID) and each valid review record's
verdict, model and family; invalid records are listed as problems. The hint
names `--ref <branch>` and `do-next-available-task --under <ID> --local`. The
command gains `--ref`, which evaluates the node against that branch or commit
through the existing `_node_status` path (works with or without a claim). A
claimless directory with no records keeps the old "caller error" exit 1, with a
message that it can be deleted and no pickup advice. Naming the node with
records present exits 0.

`docs/orchestration.md` (Hand-off files) gains a paragraph: records are read
from the working tree, are untracked by design, policy comes from
`roadmap/orchestration.yaml` on the integration branch, approvals persist as
`Reviewed-by:` trailers; plus the claimless `handoff status`, `--ref` and
`--local` behaviour.

## Changes

- `specy_road/bundled_scripts/review_cli.py` — `_unclaimed()` splits the two
  claimless shapes; `_node_status` / `_status_or_error` take an optional ref;
  `_render` keys off the `error` field and prints "no commit under review" when
  there is no ref; `handoff status --ref`; exit code keyed off `error`.
- `docs/orchestration.md` — the paragraph above. The file was at its 400-line
  cap (`specy-road file-limits`), so the section's intro paragraph was reflowed
  into long lines (no wording change) to make room; the file is 400 lines.
- `tests/test_review_cli.py` — tests for both claimless shapes.

Final touch zones: `review_cli.py`, `docs/orchestration.md`, `tests/`.
`specy_road/review_target.py` needed no change (its `resolve_target` already
takes `ref`, and `handoff status` no longer embeds its pickup message).

## Verification

- `python -m pytest -q` — 2221 passed, 2 skipped.
- `specy-road file-limits` — OK.
- `ruff check specy_road/bundled_scripts/review_cli.py tests/test_review_cli.py` — passed.

## Walkthrough

1. In a repo with a READY and a REVIEW under `work/reviews/M1.1/` and an empty
   registry, run `specy-road handoff status M1.1`: records and verdicts listed,
   hint names `--ref <branch>` and `--local`, exit 0.
2. Add `--ref <branch>`: the normal state/policy evaluation at that commit.
3. With an empty `work/reviews/M1.1/` and no claim: exit 1, "the directory can be deleted".

## Added

- `_unclaimed()` in review_cli.py — distinguishes "no records" (caller error, deletable dir) from "records, no claim" (listed with verdicts and the `--ref`/`--local` hint) (A1, A2).
- `ref` parameter on `_node_status` / `_status_or_error` — lets `--ref` reuse the existing status evaluation instead of a second path (A2).
- `handoff status --ref` argument — the evaluation the hint points to (A2).
- Guard: `--ref` without a node id fails — one branch must not be applied to every node in the sweep.
- `_render` "no commit under review" header branch — the claimless listing has no ref/commit to print.
- Mocks: none.
- Test `test_records_without_a_claim_are_listed_with_their_verdicts` — A1/A2 text output, `--ref` evaluation reaching `approved`, and the `--ref`-without-node guard.
- Test `test_no_claim_and_no_records_is_an_empty_directory` — the other claimless shape: exit 1, no pickup advice.
- Helper `_drop_claim` in tests — empties the registry for both tests.
