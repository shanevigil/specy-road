# Implementation summary for M3.16

## Summary

`specy_road/bundled_scripts/worker_cli.py` (408 lines) and `specy_road/worker_adapters.py`
(430 lines) were split by moving whole functions, unchanged, into two new modules. They are
now 346 and 342 lines and `specy-road file-limits` passes. Nothing else changed: function
names, bodies, comments and docstrings are byte-identical, and the old modules import the
moved names back, so every caller (`worker_runner`, `worker_ops`, `worker_lease`,
`role_prompt`, the tests) still resolves the same objects.

## Changes

- `specy_road/worker_adapter_parsers.py` (new, 110 lines): the command-template placeholder
  grammar from `worker_adapters.py` (`PLACEHOLDERS`, `_SESSION`, `_WORD`, `_ANY_PROMPT`,
  `_placeholder_of`, `_tokens`, `substitute_prompt`, `placeholder_problem`,
  `has_prompt_placeholder`) and the text helpers the adapters use (`_text`, `_snip`, `_json`).
- `specy_road/worker_adapters.py`: those definitions removed; imports `_SESSION`, `_json`,
  `_snip`, `_text`, `_tokens`, `placeholder_problem`, `substitute_prompt` from the new module.
  `import re` and `import shlex` went with the code that used them. `PLACEHOLDERS` and
  `has_prompt_placeholder` are not re-exported: nothing outside the moved block uses them.
- `specy_road/bundled_scripts/worker_cli_render.py` (new, 71 lines): the record and event
  rendering helpers from `worker_cli.py` (`_row`, `_line`, `_ends_turn`,
  `_harness_message_before`, `_terminal_message`, `_sync_event_lines`).
- `specy_road/bundled_scripts/worker_cli.py`: those definitions removed; imports `_line`,
  `_row`, `_sync_event_lines`. Its `wrapper_alive` import moved with the only code that used it.

Final touch zones: `specy_road/bundled_scripts/worker_cli.py`, `specy_road/worker_adapters.py`,
`specy_road/worker_adapter_parsers.py`, `specy_road/bundled_scripts/worker_cli_render.py`.
`tests/` was not changed. Nothing in the tests patches either module, and they reference only
public names (`wa.adapter_for`, `wa.Launch`, `wa.placeholder_problem`, `wa.substitute_prompt`,
`wa.STDIN_INSTRUCTION`, `wa.ADAPTERS`, `wa.Unsupported`), all still reachable from
`worker_adapters`.

To confirm the move is verbatim, I checked every removed line of the diff against the two new
files: all are present, and the only added lines in the old modules are the two imports.

## Verification

- `specy-road file-limits`: `OK: file limits satisfied.` (exit 0)
- `ruff check specy_road tests scripts`: `All checks passed!` (exit 0)
- `python scripts/check_test_private_imports.py`: `117 current, 118 baselined, 0 new` (exit 0).
  The one stale baseline entry (`test_review_round6_evidence.py: review_packet._changed`) was
  already there before this change.
- `python scripts/check_clones.py --pylint <uvx pylint wrapper>`: `11 current, 12 baselined, 0 new`
  (exit 0). pylint is not installed in the repo env, so I ran pylint 4.1.3 through `uvx`.
- `python -m pytest -q`: 2402 passed, 2 skipped, 2 failed. Both failures are
  `tests/test_unauthored_leaf_guard.py::test_validate_notes_complete_leaves_still_on_the_scaffold[False|True]`
  and fail the same way at base `065e4cc` (checked in a throwaway detached worktree). They count
  `notice:` lines from `validate`, which has nothing to do with worker code.

## Notes

- `specy-road session start` warned of an overlap with session `savigil-s79894` (M3.10,
  `feature/rm-worker-reconcile-and-status`) on `worker_cli.py` / `worker_adapters.py`. Its
  worktree no longer appears in `git worktree list`, and this work ran in its own worktree, so
  it could not collide. If M3.10 still has unmerged edits to either file, they would need a
  rebase onto this split.

## Added

- Module `specy_road/worker_adapter_parsers.py`: receives the moved placeholder-grammar and text helpers (A1).
- Module `specy_road/bundled_scripts/worker_cli_render.py`: receives the moved rendering helpers (A1).
- Import of the moved names back into `worker_adapters.py` and `worker_cli.py`: keeps existing callers and tests unchanged (A2).
- Helpers: none (every function was moved, not written).
- Branches or guards: none.
- Mocks: none.
- Tests: none. The existing worker tests cover the moved code unchanged (A2).
