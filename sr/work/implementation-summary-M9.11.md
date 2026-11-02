# Implementation summary: M9.11 `nested-zone-paths`

## What changed

In a nested project (project root `sr/` under the git root), both the review
packet's changed-path list and the finish implementation check moved each
git-reported path into the project's frame (`sr/schemas/x.json` became
`schemas/x.json`) and then matched zones only against that form. A zone written
from the git root, like `sr/schemas/`, never matched, so the packet flagged the
file as outside the touch zones and finish refused the leaf.

- `specy_road/finish_implementation_check.py`: new `in_zones(zones, path, prefix)`
  takes a git-root-relative path and matches it in both forms: as git reported it,
  and moved into the project when it lies under the project. Code outside the
  project has only its git-root name, as before. `implementation_paths` now uses
  it and still returns matches project-relative, so its output is unchanged.
- `specy_road/bundled_scripts/review_packet.py`: `changed_paths_section` keeps the
  git-reported paths next to the project-relative ones it displays and marks
  outside-zone files with `in_zones`. Because the packet and finish now call one
  function, they agree (A1). The list shown and bookkeeping/policy detection
  behave as before.
- `specy_road/review_target.py`: no change needed. `touch_zones` returns the
  declared zones unchanged, and normalising happens at match time.

Why match both forms instead of turning zones into git-root form: in a nested
checkout, zones such as `specy_road/...` name code outside the project from the
git root. Adding the project prefix to every zone would break them, and there is
no reliable way to tell which form a zone uses. Trying both forms of the path
leaves existing zones working and accepts either spelling.

Touch zones confirmed: the change needed only `finish_implementation_check.py`,
`bundled_scripts/review_packet.py` and `tests/`. `review_target.py` stays in the
list but did not need an edit.

## Verification

- `python -m pytest tests/test_nested_zone_paths.py -q`: 12 passed
- `specy-road file-limits`: OK
- `python -m pytest -q -p no:cacheprovider` (full suite): 2868 passed, 2 skipped

## Added

- `finish_implementation_check.in_zones`: the one matcher shared by the packet and finish; it tries both forms of a path so either zone spelling matches (A1).
- `review_packet.changed_paths_section`: the `changed` list zipped with `paths`, so the zone test can see the git-root form while the packet still shows project-relative paths.
- `tests/test_nested_zone_paths.py::test_either_zone_form_is_in_zone_for_packet_and_finish`: nested layout. A file under `sr/schemas/` with a git-root-relative, project-relative, file or glob zone gets no outside-zone flag and no finish refusal (A1, A2).
- `tests/test_nested_zone_paths.py::test_an_unmatched_zone_is_still_flagged_and_refused`: the same file with no matching zone is still flagged in the packet and refused at finish (A2).
- `tests/test_nested_zone_paths.py::test_in_zones_reads_both_roots`: unit cases. Both forms work inside the project, code outside it has only its git-root name, and in an embedded layout (empty prefix) nothing is rewritten.
- Mocks: none (the tests use real temporary git repositories).
