# Implementation summary: M22.26 — post-run zone check git-root zones

## Touch zones (confirmed)

Scanned call sites from the brief: `worker_turn_check.py` is imported by `worker_ops_message.py`, `worker_runner.py`, and tests only; no extra zones required.

Final touch zones: `specy_road/worker_turn_check.py`, `tests/test_worker_turn_check.py`, `CHANGELOG.md`.

## Change

`_outside_zones` now delegates path-in-zone checks to `finish_implementation_check.in_zones` with `project_prefix`, matching finish and review-packet behaviour in nested layouts (`sr/...` zones vs project-relative zones).

## Added

- `_nested_touch_zones` — sets graph/registry touch zones in the nested-layout fixture for the git-root zone form case.
- `_close_turn_findings` — runs `close_turn` and returns the post-run findings list for assertions.
- `test_nested_close_turn_accepts_a_commit_inside_either_zone_form` — parametrized `sr/src` and `src` zone lists; no `committed_outside_zones`.
- `test_nested_close_turn_flags_a_commit_outside_git_root_and_project_zones` — commit at git root outside `sr/` still flagged.

## Added inventory

### Helpers

- `_nested_touch_zones` — write git-root-form touch zones into the nested test graph without duplicating `nested_project`.
- `_close_turn_findings` — thin wrapper so zone tests assert through `close_turn` per acceptance.

### Branches or guards

- none

### Mocks

- none

### Tests

- `test_nested_close_turn_accepts_a_commit_inside_either_zone_form` — regression for A1 in-zone cases via `close_turn`.
- `test_nested_close_turn_flags_a_commit_outside_git_root_and_project_zones` — regression for A1 outside case via `close_turn`.
