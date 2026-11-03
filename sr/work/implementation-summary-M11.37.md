# Implementation summary: M11.37 — packet-uncommitted-refs

## What changed

`review-packet` now renders a `## Uncommitted references` section immediately after the implementation summary. It scans the rendered brief, each planning sheet on the node chain (committed at the reviewed commit, else the working tree), and the implementation summary (same rule). Inline-code and markdown-link tokens that look like repository file paths are checked with `git cat-file -e` at the reviewed commit; misses are listed in the packet and printed on stderr so a coordinator can commit them before reviewers start.

Path extraction ignores branch-shaped tokens (`feature/...`) and path-like prose that does not start under a known project top-level directory or root file name, and requires a file extension on multi-segment paths so bare directory placeholders such as `` `shared/` `` do not warn.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/review_packet.py`
- `specy_road/bundled_scripts/review_packet_uncommitted_refs.py` (new; keeps `review_packet.py` under the 400-line cap)
- `tests/`

The registry claim still lists only `review_packet.py`; the coordinator should add `review_packet_uncommitted_refs.py` to the claim row before `finish-this-task`.

## Acceptance

- **A1:** `## Uncommitted references` plus stderr warnings for each path named in the brief, planning sheet or summary that is absent at the reviewed commit.
- **A2:** `tests/test_review_packet.py` covers an uncommitted named file, a committed named file, and non-repository path-like tokens.

## Verification

- `pytest tests/test_review_packet.py -q`
- `specy-road file-limits`

## Added

- `specy_road/bundled_scripts/review_packet_uncommitted_refs.py` — path token extraction, source text collection, and the uncommitted-references section (keeps the main packet module under file limits).
- `_named_repo_path` / `_named_paths` — normalize backtick and link tokens into project-relative repository paths.
- `_show` — read a project-relative blob at the reviewed commit for source scanning.
- `uncommitted_refs_section` — build the packet section and emit stderr warnings.
- `tests/test_review_packet.py::_uncommitted_block` — slice the packet for assertions.
- `test_packet_warns_when_a_planning_sheet_names_an_uncommitted_file` — A1 untracked case.
- `test_packet_is_silent_when_a_named_file_is_at_the_reviewed_commit` — committed case.
- `test_packet_ignores_path_like_tokens_that_are_not_repository_paths` — A2 false-positive guard.
