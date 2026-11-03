# Implementation summary: `M11.80` — test-worker-cap

## What changed

- **A1:** `roadmap/git-workflow.yaml` accepts an optional string `verify_cmd`
  (`specy_road/templates/project/schemas/git-workflow.schema.json`), separate from
  `land_check_cmd`. `specy_road/verify_cmd_config.py` reads it
  (`resolve_verify_cmd`; unset, blank or an unreadable config means `None`) and
  renders one `**Running tests:**` sentence (`verify_cmd_lines`):
  - set: "run this leaf's tests with `<verify_cmd>` followed by the test paths
    (`verify_cmd` in `roadmap/git-workflow.yaml`); other workers may share this
    machine, and the full suite runs at landing."
  - unset: "when other workers share this machine, cap parallel test workers (for
    example `pytest -n 4`, not `-n auto`) …; a project can name the command as
    `verify_cmd` …".

  The executor brief carries it at the end of section 7 (touch-zone instruction,
  `generate_brief._section_touch_zone_instruction`), so every executor prompt
  (which embeds the brief) has it. The reviewer prompt carries it in
  `role_prompt.reviewer_lines`, after the launch-mode lines, since a reviewer's
  prompt embeds the packet, not the brief.
- **A2:** `docs/orchestration-workers.md` gains a **Parallel tests** paragraph
  (after "Killing by pattern"): concurrent workers each running a full parallel
  suite oversubscribe the CPU; recommends `verify_cmd` with a small worker count
  and `land_check_cmd` for the full suite at landing. `docs/git-workflow.md`
  documents the `verify_cmd` field next to `land_check_cmd`, with an example.
  `tests/test_verify_cmd.py` covers the executor and reviewer prompt text with
  and without `verify_cmd`.

## Touch zones (final)

Declared zones, plus **`specy_road/verify_cmd_config.py`** (new module), added
with `specy-road edit-node M11.80 --add touch_zones=specy_road/verify_cmd_config.py`
as the planning sheet's Approach allows; the roadmap chunk and registry row are
committed on this branch. Why: `specy_road/git_workflow_config.py` is at 395 of
its 400-line cap, so the reader could not go there as the Approach suggested,
and `role_prompt.py` is at exactly 400 lines.
`git_workflow_config.py` is therefore unchanged.

`role_prompt.py` stays at 400 lines: it imports `verify_cmd_lines` on its
existing `generate_brief` import line (generate_brief imports it from
`verify_cmd_config`), and the extra term joins the existing `reviewer_lines`
return expression. No docstring, comment or user-facing text was shortened.

Not changed (outside zones, not needed): `specy_road/templates/project/roadmap/git-workflow.yaml`
(the template could show a commented `verify_cmd` example) and `sr/schemas/git-workflow.schema.json`
(the toolkit project's own schema copy).

## Verification

- `python -m pytest -n 4 -p no:cacheprovider -q tests/test_verify_cmd.py tests/test_models_and_prompt.py tests/test_generate_brief.py tests/test_baseline_gate.py tests/test_schema_revision.py` — 71 passed
- Every test file mentioning `role_prompt`, `generate_brief`, `render_brief`,
  `build_prompt`, `git_workflow_config` or `git-workflow` (69 files), in six
  batches with `-n 4` — 772 passed. One combined run of all 69 was stopped by the
  harness's 10-minute timeout while machine load was ~28 from other workers;
  the batches then ran clean.
- `specy-road file-limits` — OK
- `ruff check` on the touched Python files — OK
- `specy-road validate`, `specy-road export --check` — OK

## Added

### Helpers
- `specy_road/verify_cmd_config.py` — new module: the `verify_cmd` reader and the prompt sentence, kept out of `git_workflow_config.py`, which is at its line cap.
- `resolve_verify_cmd(repo_root)` — reads `verify_cmd`, treating unset, blank or an invalid config as `None`, the same way `resolve_baseline_cmd` does.
- `verify_cmd_lines(repo_root)` — the one sentence (set or unset form) shared by the brief and the reviewer prompt, so the two cannot drift apart.

### Branches or guards
- The `if cmd:` branch in `verify_cmd_lines` — A1 asks for different text with and without `verify_cmd`.

### Schema
- `verify_cmd` property in `git-workflow.schema.json` — without it, `additionalProperties: false` rejects the key.

### Mocks
- none

### Tests (`tests/test_verify_cmd.py`)
- `test_schema_accepts_verify_cmd` — A1: the config accepts the key.
- `test_unset_or_blank_verify_cmd_resolves_to_none` — a blank value falls back to the cap advice, not an empty command in backticks.
- `test_prompts_without_verify_cmd_say_to_cap_test_workers` — A1/A2: executor and reviewer prompt text without `verify_cmd`.
- `test_prompts_with_verify_cmd_give_it_as_the_leaf_test_command` — A1/A2: both prompts give the command with test paths appended, and the executor's copy is inside the brief.
