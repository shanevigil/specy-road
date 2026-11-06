# Implementation summary: M21.33 (brainstorm start is the first call, alone)

## What changed

- **A1** `specy_road/templates/specyrd/commands/specyrd-brainstorm.md`:
  - **Description:** "(not even in the same step as this skill)" is replaced by the sentence from the brief: "After reading this skill, make `specy-road brainstorm start` your next tool call, alone in its tool-call batch, with no parallel read or search (not roadmap-context.md, roadmap/, planning/ or anything else); after it returns, read the prompt file it names and continue." The description is 570 characters, under the 1024 limit.
  - **First body paragraph:** the same sentence comes after the existing opening line and before "What you read before round 1 anchors every idea in it."
  - **Kept wording:** the existing "Run `specy-road brainstorm start` first, before reading roadmap-context.md…" and "Run `start` **before reading anything else**: not `roadmap-context.md`…" phrases stay. `tests/test_brainstorm_prompt_fixes.py`, which is outside the touch zones, asserts both, and neither contradicts the new rule.
- **A2** `suggested_prompts/brainstorm-roadmap.md` Phase 1 states the same rule: the next tool call, alone in its batch, with no parallel read or search; after it returns, read the prompt file it names.
- **A3** `tests/test_brainstorm_skill_first_call.py` is a new test, parametrized over claude-code, codex and cursor:
  - It renders each harness's skills with `run_init`, the function behind `specyrd init`.
  - In each `.agents/skills/specyrd-brainstorm/SKILL.md` it asserts that the sentence is in the description and in the first body paragraph, that "same step" is gone, and that the description is at most 1024 characters.
  - For claude-code it also asserts that `.claude/skills/specyrd-brainstorm/SKILL.md` resolves to that file.
  - There is no CLI enforcement.
- **CHANGELOG:** an entry under the existing `[Unreleased]` → `### Changed` heading.

## Touch zones

These were confirmed accurate and need no additions: the template, `suggested_prompts/brainstorm-roadmap.md`, `tests/test_brainstorm_skill_first_call.py` and `CHANGELOG.md`. `specy-road file-limits` passes.

## Verification

- **Red-green:** with the template restored to HEAD, `pytest -q tests/test_brainstorm_skill_first_call.py` gives 3 failed, exit 1. With the change it passes.
- **Full suite:** `pytest -q -n 4` gives 5530 passed.

## Added

- **Helpers:** none.
- **Branches or guards:** none.
- **Mocks:** none.
- **Tests:** `test_shipped_skill_makes_start_the_next_tool_call_alone[claude-code|codex|cursor]` is the A3 regression for CR5. It checks the rendered copy each harness actually loads, including the claude-code `.claude/skills` link.
