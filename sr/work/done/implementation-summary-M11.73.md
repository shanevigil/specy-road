# Implementation summary: M11.73 — specy-road ready warns when the leaf no longer merges cleanly

## What changed

- **A1:** `specy-road ready` now runs the trial merge that `handoff status` runs, `trial_merge(root, t.ref, t.base_ref)`
  with `t = resolve_target(root, node_id, "HEAD")`, after it writes the READY file.
  - On a **code** conflict it prints `warning: <integration ref> is N commit(s) ahead and a trial merge conflicts on
    <paths>: …`, then a line telling the executor to `git merge <integration ref>`, resolve, commit, run the verifiers
    again and rerun `specy-road ready` before handing off.
  - On a **bookkeeping-only** conflict it prints a one-line note that this does not block review, the same distinction
    `handoff status` makes.
  - On a **clean** merge it prints nothing extra.
  - The command still exits 0 and the READY file is still written. A1 asks for a warning, not a refusal, and
    `mark-implementation-reviewed` and `finish` already refuse.
  - Nothing is printed when `ready` refuses for another reason, or when git cannot answer the trial merge.

## Touch zones (final)

- `specy_road/bundled_scripts/review_cli.py`: one import line changed. `build_parser` now registers `ready` through the
  new module.
- `tests/`: `tests/test_ready_command.py`.
- **New module, outside the listed zones:** `specy_road/review_ready_merge.py`. `cmd_ready` lives in
  `specy_road/review_gate_ready.py`, which is not a touch zone, and both `review_cli.py` and `review_gate.py` are at the
  400-line `file-limits` cap. Following the executor prompt's file-limits rule, the new code went into a new module that
  wraps `cmd_ready`. Please add `specy_road/review_ready_merge.py` to the leaf's touch zones.
- `specy_road/review_gate.py`: unchanged. `trial_merge` is re-exported there from `review_gate_ready.py`, and the new
  module imports it from that same source.

## Verification

- `python -m pytest -q tests/test_ready_command.py tests/test_review_cli.py tests/test_review_gate.py`: 42 passed (exit 0)
- `specy-road file-limits`: OK (exit 0)
- `python -m pytest -n auto -q`: 3379 passed, 2 skipped (exit 0)
- Red-green: with `review_cli.py` pointed back at `review_gate_ready.add_ready_parser`,
  `python -m pytest -q tests/test_ready_command.py -k trial_merge` failed on the bookkeeping and code cases (exit 1).
- Merge round: merged `origin/WIP/improvements-0-3-1` (Codex reviewer roster entries) cleanly at `b5409504`; it changes nothing this leaf depends on (only an unrelated helper in `tests/review_repo_helpers.py`), and after it the leaf's tests (42 passed) and `specy-road file-limits` (OK) pass again.

## Added

- `specy_road/review_ready_merge.py`: new module, because the touch-zone files are at the line cap and `cmd_ready` is
  outside the zones.
- `trial_merge_warning(root, node_id)`: builds the warning or note lines from the same trial merge `handoff status`
  makes.
- Guard in `trial_merge_warning` for `ReviewTargetError`: returns no lines. `cmd_ready` has already resolved the same
  target, so this is defensive only.
- Guard in `trial_merge_warning` for `tm is None or not tm.conflicts`: prints nothing when the merge is clean or git
  cannot answer, as `handoff status` does.
- Branch in `trial_merge_warning` for a bookkeeping-only conflict: prints a note, not a warning, matching the
  non-blocking label in `handoff status`.
- `cmd_ready` wrapper: runs the original `cmd_ready`, and only when it exits 0 prints the warning lines to stderr.
- `add_ready_parser` wrapper: registers the original parser, then points `ready` at the wrapper, so `review_cli.py`
  changes by one import line.
- Test `test_ready_warns_when_the_trial_merge_handoff_status_makes_conflicts[clean|bookkeeping|code]` in
  `tests/test_ready_command.py`: covers a clean leaf, a bookkeeping-only conflict and a code conflict. It checks that
  `handoff status` reports the same conflict and that the READY file is still written.
- Mocks: none.
