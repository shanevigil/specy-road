# Implementation summary: M11.49 — packet-zones-at-commit

## What changed

- **A1 (zones at the reviewed commit).** `resolve_target` now reads the node from its chunk **at the reviewed
  commit** (`node_at`, git objects only) and stores its `touch_zones` on `ReviewTarget.committed_zones`
  (milestone and leaf paths alike). The new `ReviewTarget.review_zones` property is the ordered union of the
  claim row's `touch_zones` and those committed zones. When the node cannot be read at that commit
  (`committed_zones is None`) it returns `touch_zones` unchanged (the claim row's zones, else the node's in the
  working tree). `review_packet` uses `review_zones` for the header's **Touch zones** line and for the
  **Changed paths** "outside touch zones" marks. `ReviewTarget.touch_zones` is unchanged, so `prompt`,
  `impact --zones` and `worker reconcile` keep their current behaviour.
- `unfinished_leaves_at` now uses the shared `node_at` reader. It behaves as before: a leaf that cannot be read
  at the commit counts as unfinished.
- **A2 (lockfiles generated).** `review_packet.LOCKFILES` lists `package-lock.json`, `yarn.lock`,
  `pnpm-lock.yaml`, `poetry.lock`, `uv.lock`, `Cargo.lock` and `go.sum`. They are matched by file name in any
  directory. `_generated` treats such a file as generated when `git check-attr linguist-generated` at the
  reviewed commit reports `unspecified`, which means no `.gitattributes` entry. Any entry decides instead:
  `linguist-generated=false` (or `-linguist-generated`) inlines the file, and `set`/`true` keeps it generated.
  `_capped_diff` already kept generated files out of the over-budget flag and the line and byte counts. The new
  test checks that a large lockfile sorting first does not stop later files from being inlined.
- Docs: `docs/orchestration-review.md` has a new **Changed paths in the review packet** section (how the zones
  are formed), plus the lockfile rule and the "uses up neither budget" note in **The diff in the review packet**.
  The module docstring of `review_packet.py` notes both.

## Touch zones (confirmed)

`specy_road/review_target.py`, `specy_road/bundled_scripts/review_packet.py`, `tests/`,
`docs/orchestration-review.md`. These were enough; no new module was needed and file-limits passes.

## Verification

- `python -m pytest tests/test_review_packet.py -q`: 31 passed
- `python -m pytest -n auto -q`: 3265 passed, 2 skipped
- `specy-road file-limits`: OK
- `ruff check` on the three changed Python files: clean
- Red-green: with the two source files reverted to the base, the A1 test and both A2 tests fail. The fallback
  test passes either way, because it checks that existing behaviour is kept.

## Added

- `ReviewTarget.committed_zones` field: the node's `touch_zones` at the reviewed commit, `None` when unreadable (A1).
- `ReviewTarget.review_zones` property: union of claim-row zones and committed node zones, falling back to `touch_zones` (A1).
- `review_target.node_at()`: reads a node from its chunk at a commit; shared by the zones read and `unfinished_leaves_at` (A1, no duplicate reader).
- `review_target._zones_at()`: `touch_zones` of `node_at`, or `None` (A1).
- `review_packet.LOCKFILES` constant: the default lockfile names (A2).
- `_generated` branch: a LOCKFILES name with `linguist-generated` unspecified at the commit is generated (A2).
- Test `test_zones_added_to_the_node_on_the_branch_count_from_a_checkout_on_dev`: the A1 scenario (zone committed on the feature branch, packet built on dev, file no longer flagged, header shows the union).
- Test `test_zones_fall_back_to_the_claim_when_the_node_is_unreadable_at_the_commit`: guards the fallback when the chunk at the commit does not parse.
- Test `test_a_large_lockfile_sorting_first_is_listed_and_later_files_are_inlined`: A2, a 3000-line `package-lock.json` before `src/` plus a nested `gui/yarn.lock`; both listed as generated, the later source files inlined.
- Test `test_linguist_generated_false_inlines_a_lockfile`: A2, `uv.lock linguist-generated=false` is inlined while `Cargo.lock` without an entry stays generated.
- Mocks: none.
