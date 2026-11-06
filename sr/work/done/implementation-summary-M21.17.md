# Implementation summary: M21.17 (writers-refuse-links-out)

Commit: `4ce3fa24` on `feature/rm-writers-refuse-links-out` (base `43c375da`).

## What changed

- `specy_road/managed_block.py`: `refused_link(root, path, *, any_link=False) -> str | None` beside
  `resolves_outside`; returns `"<REFUSED>: <path>"` when the path resolves out of `root` (dangling included) or,
  with `any_link`, when it is a symlink at all.
- `specy_road/generated_files.py`: `refused_generated_files(root)` checks both `GENERATED_COMMITTED` names with the
  guard; `regenerate_generated_files` checks both before writing either, writes only the unrefused ones, prints one
  stderr line per refused name and returns the refused names (was `None`; callers ignore it).
- `specy_road/init_project.py`: `_write_generated` counts a path as present by `os.path.lexists` (a dangling link
  is skipped without `--force`); with `--force` a refused name is listed as
  `skipped (exists): <name> (refused: … : <path>)` and not listed as written.
- `specy_road/finish_land_deterministic.py`: `_regenerate_generated_files` checks both names before either write and
  raises `DeterministicResolveError` naming the path(s), so land aborts as for an unloadable graph.
- `specy_road/review_rejected.py`: `write_rejected` guards with root = reviews dir, `any_link=True`; when refused it
  prints `error: <reason>` to stderr and writes nothing. `ReviewRecordTrace.refuse` still returns the record
  command's own error and exit code.
- `specy_road/review_delegate_packet.py`: `ensure_packet` guards first (root = reviews dir, `any_link=True`) and
  raises `ReviewTargetError` (already caught by `cmd_review_delegate` → `error: …`, exit 1) before any harness
  starts or `RUN-<model>.json` is saved. `DelegateError` was not used: importing it from `review_delegate` would be
  circular.
- `CHANGELOG.md`: `[Unreleased]` → Fixed (security) entry.

Touch zones: the listed zones were accurate; no other file changed. No file-limit cap was hit
(`specy-road file-limits`: OK).

## Verification

- `pytest -q -n 4 tests/test_writers_refuse_links_out.py` — 27 passed; with the package changes reverted, 15 failed
  (red/green).
- Full suite `pytest -q -n 4` — 5446 passed (existing init, finish, review-rejected, review-packet tests unchanged).
- `specy-road file-limits` — OK.

## Added

- `managed_block.refused_link`: the one guard A1 names, reusing `resolves_outside`.
- `generated_files.refused_generated_files`: shared by `regenerate_generated_files`, init and finish so all three
  check both names before either write with one call.
- Branch in `regenerate_generated_files`: skip each refused name, stderr line, return refused names (A1).
- Branch in `init_project._write_generated`: `lexists` presence; refused names reported as skipped with reason (A1/A2).
- Guard in `finish_land_deterministic._regenerate_generated_files`: raises `DeterministicResolveError` (A1).
- Guard in `review_rejected.write_rejected`: refuses any link, stderr line, writes nothing (A1/A3).
- Guard in `review_delegate_packet.ensure_packet`: refuses any link via `ReviewTargetError` before launching (A1/A3).
- `tests/test_writers_refuse_links_out.py::test_writer_refuses_a_link_out_of_its_root`: the A2 writer × layout table
  (6 writers × 4 layouts, bytes compared).
- `tests/test_writers_refuse_links_out.py::test_review_delegate_refuses_a_linked_packet_before_launching`: A3,
  non-zero exit naming the path, no harness call, no `RUN-opus.json`.
- `tests/test_writers_refuse_links_out.py::test_a_refused_marker_leaves_the_record_refusal_unchanged`: A3, the
  `review record` error and exit code are the same with and without a linked marker.
- Mocks: none.
