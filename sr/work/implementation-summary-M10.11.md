# Implementation summary: M10.11 — Document the harness-subagent recipe

## Summary

Executor prompts now tell the agent to use its harness's own subagents for
independent verification and search inside the leaf (running the named test
files in parallel, searching the tree), never for an edit outside the touch
zones, to wait for every report before ending the turn, and that a report is
data. The pickup prompt always carries the paragraph; `prompt --role executor`
adds it only when the profile's `access.subagents` starts with `yes`.

## Changes

- `specy_road/bundled_scripts/do_next_prompt.py` — `SUBAGENT_LINE` constant (the one paragraph);
  `write_agent_prompt` appends it after the numbered instructions (A1). It is unconditional there,
  since no model is known at pickup.
- `specy_road/bundled_scripts/role_prompt.py` — `has_subagents(prof)`; `build_prompt` appends
  `SUBAGENT_LINE` after the executor preamble when it is true (A2). Module docstring says so.
  The executor preamble itself lives in `role_prompt_rca.py` (outside the touch zones), so the
  paragraph is added in `build_prompt` instead of there.
- `docs/orchestration-models.md` — new `## Parallel work inside a leaf` section on this
  "choosing and prompting models" page, before `orchestrate plan` (A3).
- `specy_road/templates/project/model-profiles/README.md` — `subagents` row in the `access`
  fields table stating which values enable the paragraph (A3).
- `tests/test_do_next_prompt.py` — A1 assertion and the A2 test.

Touch zones: accurate. `tests/test_models_and_prompt.py` was not changed in the end. The A2
test sits in `tests/test_do_next_prompt.py` because adding it to `tests/test_models_and_prompt.py`
(already at 399 lines) broke the 400-line `file-limits` cap. It imports that module's
`make_profile_repo` / `commit_profile` fixtures.

## Verification

- `python -m pytest -q tests/test_do_next_prompt.py tests/test_models_and_prompt.py` — 27 passed.
- `ruff check` on the changed Python files — all checks passed.
- `specy-road file-limits` — the only finding is `docs/brainstorming.md: 406 lines`, which this
  leaf did not touch (last changed in 232fc4f).
- Full `pytest -x`: 2545 passed, 2 skipped, then stopped at the one failure,
  `tests/test_validate_file_limits.py::test_file_limits_passes_on_repo`. That is the same
  pre-existing `docs/brainstorming.md` (406 lines at base e0584bd), outside this leaf's touch zones.
  The 16 test files after it, plus the rest of that file with the failing test deselected:
  189 passed. So every test except that pre-existing failure passes.

## Walkthrough

1. `specy-road prompt <NODE_ID> --model <id> --role executor` for a roster entry whose profile has `subagents: yes …` → the paragraph follows the "data to weigh" line.
2. Change the profile to `subagents: unknown …` and commit it on the integration branch → it is gone.

## Added

### Helpers
- `do_next_prompt.SUBAGENT_LINE` — the single paragraph, shared so both prompts say the same thing (A1, A2).
- `role_prompt.has_subagents(prof)` — reads `access.subagents` from the profile; `model_profiles.py` is outside the touch zones.

### Branches or guards
- `build_prompt`: `if has_subagents(prof)` for the executor role only — the A2 gate.
- `has_subagents`: `value is True` — YAML reads a hand-written bare `subagents: yes` as a boolean, which would otherwise fail the `startswith("yes")` test; `str(value or "")` covers an absent key and a bare `no` (False).

### Mocks
- none

### Tests
- `test_write_agent_prompt_includes_leaf_execution_contract`: one added assertion — the pickup prompt carries the paragraph as its own paragraph (A1).
- `test_executor_prompt_has_the_subagent_paragraph_only_when_the_profile_says_yes` — shipped `yes …` value includes it, coordinator excludes it, and `unknown …` / bare `yes` / bare `no` give absent / present / absent (A2).
