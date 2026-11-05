# Implementation summary: M15.35 — packet never lists `.git` as uncommitted

Base `045de174`; code commit `40bea4d8`.

## What changed, per acceptance item

- **A1:** `_named_repo_path` in `review_packet_uncommitted_refs.py` returns `None` when the first path segment is `.git`, so `.git` and paths under it are never collected as uncommitted references. A new integration test builds a review packet whose brief (via an updated planning sheet) names `` `.git` ``, `` `.git/hooks/pre-commit` ``, and a missing `` `docs/x.md` ``; the Uncommitted references section lists only `docs/x.md`, stderr has exactly one warning, and neither section mentions `.git`.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/review_packet_uncommitted_refs.py`
- `tests/` (added `tests/test_review_packet_dot_git_m15_35.py` because `tests/test_review_packet.py` was already at the 400-line cap)

Out of scope unchanged: M15.17 git-ignore skipping and path-extraction rules.

## Verification

- `pytest tests/test_review_packet_dot_git_m15_35.py -q`
- `specy-road file-limits`

## Added

- Guard in `_named_repo_path` rejecting first segment `.git` — A1; stops the metadata directory from being treated as a named repo path.
- `tests/test_review_packet_dot_git_m15_35.py` with `test_packet_skips_dot_git_paths_named_in_the_brief` — A1 acceptance scenario through `build_packet`.
- Local `_uncommitted_block` helper in that test module — parses the packet section without growing `test_review_packet.py` past file limits.
