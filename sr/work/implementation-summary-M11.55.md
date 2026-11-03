# Implementation summary: M11.55 (file-limit-split-not-delete)

## What changed

- `specy_road/bundled_scripts/role_prompt.py`: two new prompt blocks.
  - `FILE_LIMIT_LINES` (A1) is added to every executor prompt right after the role preamble. It says that a change which would push a file over a `specy-road file-limits` cap moves the new or related code into a new module, which is named in the implementation summary so the zones can be updated, and that unrelated docstrings, comments or user-facing text are never deleted or shortened to fit.
  - `REMOVED_TEXT_LINES` (A2) is added to every reviewer prompt right after the reviewer preamble, before the launch-mode lines. It asks the reviewer to check the diff for docstrings, comments or messages removed or shortened that the leaf did not need to touch, and to require their restoration.
- `tests/test_role_prompt_file_limits.py` (new): one test per rendered prompt (A2's "tests cover both prompt sentences").

## Touch zones (confirmed)

`specy_road/bundled_scripts/role_prompt.py`, `tests/`. `specy_road/templates/` needed no change.
The role preambles themselves live in `specy_road/bundled_scripts/role_prompt_rca.py`, which is outside the zones. The sentences are therefore appended in `build_prompt`, the same way `LAUNCH_MODE_LINES` and `SUBAGENT_LINE` already are. As a result, the executor sentence comes just after the preamble's boundary rules rather than inside the numbered steps. If the maintainer prefers it inside the preamble, a follow-up could move both into `role_prompt_rca.py`.

The new test file exists because `tests/test_models_and_prompt.py` is already at 400 lines (this leaf's own rule, applied).

## Verification

- `python -m pytest -q tests/test_role_prompt_file_limits.py tests/test_models_and_prompt.py`: 27 passed
- `specy-road file-limits`: exit 0
- `python -m pytest -q -x -n auto`: 3215 passed, 2 skipped
- Red/green: with `role_prompt.py` restored to the base, `tests/test_role_prompt_file_limits.py` fails (2 failed, exit 1).

## Added

- `FILE_LIMIT_LINES` (role_prompt.py): the A1 executor sentence.
- `REMOVED_TEXT_LINES` (role_prompt.py): the A2 reviewer sentence.
- `test_executor_prompt_says_split_into_a_new_module_never_delete_docs`: A1 is in the rendered executor prompt.
- `test_reviewer_prompt_asks_for_removed_docs_to_be_restored`: A2 is in the rendered reviewer prompt, and the executor sentence is not.
- Helpers, guards, mocks: none.
