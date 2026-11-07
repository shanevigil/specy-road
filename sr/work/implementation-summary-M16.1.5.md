# Implementation summary: M16.1.5

AGENTS.md is the one agent entry with a task-conditional load order; CLAUDE.md is a pointer.

Base `5dce867e`; implementation commit `c83385c5`.

## Acceptance

- **A1.** `CLAUDE.md` is 9 lines: an `@AGENTS.md` import (Claude Code skips `AGENTS.md` while `CLAUDE.md` exists, so the import is what loads it) and three Claude-specific notes. Its maintainer-hygiene notes moved, nothing dropped: adoption prompts, reuse, the PM Gantt sequence, the gates and release/tag parity went to `AGENTS.md` (Maintainer hygiene, Version numbers); the git workflow policy went to `docs/toolkit-development.md`.
  - **Version-numbers rule:** stated once, in `AGENTS.md` § Version numbers (human-owned). That section now also holds 027's "VERSION DECISION NEEDED" block. `.cursor/rules/027-…mdc` keeps its `alwaysApply` frontmatter and one sentence that links to that section.
  - **Branch policy:** stated once, in `docs/toolkit-development.md` § Maintainer workflow vs consumer workflow. That section absorbed `CLAUDE.md`'s branching, promotion, PR and release-marker text, and corrects the stale `release: x.x.x` form to `release: vX.Y.Z`. `AGENTS.md` § Coordination and `.cursor/rules/030-…mdc` link to it. 030 keeps only its sync-first hygiene section, which is stated nowhere else, plus links to toolkit-development.md and the release runbook. `tests/test_release_harness.py` pins 030's links to `release-runbook.md` and `release: vX.Y.Z`; both stay.
- **A2.** `AGENTS.md` `### Load order` always reads purpose, principles and constraints. Its "By task" list covers orchestration or review, roadmap data, dependencies or release, the dogfood fixture, and `sr/` roadmap work. `specy_road/templates/specyrd/agents-rules.md` always reads the digest, purpose, principles and constraints, then "By task:" items 4-6. `docs/supply-chain-security.md` is no longer in either default order.
- **A3.** `tests/test_agent_start_up_reading.py` covers this repo and a freshly initialised consumer repo (`init project` plus `specyrd init --ai claude-code`).
  - **What it counts:** the unique files in the closure, using the existing public helpers. These are the entry files plus the always-applied Cursor rules (`cursor_paths`), the files `CLAUDE.md` imports (`claude_imports`), and the load order up to its "By task" line (`load_order_paths`). The generated digest is not counted, since it grows with the roadmap.
  - **Output:** with `-s` it prints each counted path, the total, and `CLAUDE.md`'s size against its estimate of about 20 lines (printed, not enforced).
  - **Failures:** it fails when a default-order file is missing, when supply-chain is in the default order, or when the total is over 400.
  - **Current totals:** toolkit 238 lines; consumer 145 lines.
- **A4.** Two parts:
  - **Interpretation, for reviewers to check:** "shipped" is read as the rendered `.specyrd/AGENTS.md` that adopters get. `render_rules()` already strips every provenance comment, and `tests/test_agents_md_block.py::test_rules_file_is_the_full_rule_set_and_the_stub_points_at_it` asserts that no `<!--` remains. The comments stay in the template because `tests/test_agents_md_block.py::test_every_rule_in_a_block_template_is_followed_by_its_provenance` and `chore_garden`'s advisory-rule scan read them there. Removing them would need changes outside the touch zones.
  - **Cites only adopter files:** the new test asserts that every `docs/*.md` the rendered rules cite exists in a fresh consumer repo. Non-shipped docs are already rewritten to versioned toolkit URLs. The load order's former `docs/orchestration.md` pointer is replaced by "the Task loop below".
- **A5 (informational).** Docs: 59 insertions and 226 deletions, net -167. The new test adds 73 lines.

## Constraints met

- **Rules-file budget:** `tests/test_enforced_rules_pointers.py::test_the_rules_file_stays_within_its_budget` pins the rendered rules file at 68 lines and 9,496 bytes, and HEAD sat exactly at both. The task-conditional order therefore had to fit in the same space; it renders to 68 lines and 9,494 bytes. Only the load-order lines being rewritten were made more concise (e.g. "then only cited contracts"); no other text was shortened.
- **Load-order order:** in the template, supply-chain stays before `shared/README.md`, inside `### Load order`, so `validate`'s missing-file warning keeps naming both in that order (`tests/test_agents_md_block.py::test_validate_names_load_order_files_the_project_lacks`).
- **Lean section:** the `## Lean changes and tests` section in `AGENTS.md` is kept verbatim (`tests/test_lean_rules.py` mirrors it).

## Touch zones (final)

- **Changed:** `AGENTS.md`, `CLAUDE.md`, `docs/toolkit-development.md`, `specy_road/templates/specyrd/agents-rules.md`, `tests/test_agent_start_up_reading.py`, `.cursor/rules/027-version-numbers-require-human.mdc`, `.cursor/rules/030-git-workflow-management.mdc`.
- **Unchanged:** `docs/context-regressions.yaml`. No case cites the files changed here, and no acceptance item asks for a new case.
- **Outside the zones, left alone (follow-up for the planner):**
  - `docs/git-workflow.md:6` still points to `../CLAUDE.md` for the toolkit branch policy. It should point to `docs/toolkit-development.md#maintainer-workflow-vs-consumer-workflow`. Today it reaches the policy in two hops: CLAUDE.md, then AGENTS.md.
  - `docs/contributor-guide.md` § Default branch is `dev` restates part of the branch policy.
  - `.cursor/rules/026-release-version-tag-sync.mdc` restates the version rule in one bullet, which links to 027.

## Checks run

- `pytest -n 4`: 6803 passed, 8 skipped.
- `specy-road validate`, `export --check` and `digest --check` on the dogfood fixture: exit 0.
- `specy-road file-limits`: OK.
- `ruff check` on the new test: clean.
- `scripts/check_machine_paths.py` and `scripts/check_test_private_imports.py`: exit 0.

## Added

- **Test** `tests/test_agent_start_up_reading.py::test_start_up_reading_exists_and_stays_within_the_limit` (parametrized toolkit/consumer): A3, covering the start-up closure, the missing-file and supply-chain checks, and the 400-line gate.
- **Test** `tests/test_agent_start_up_reading.py::test_shipped_rules_cite_only_files_an_adopter_has`: A4, checking that every `docs/*.md` the rendered rules cite exists in a fresh consumer repo.
- **Helper** `_consumer` (test module): builds the fresh consumer repo both tests need.
- **Helper** `_always_load_order` (test module): the load order up to the "By task" line, read from the rules file in a consumer repo or from `AGENTS.md` in this one.
- **Helper** `_lines` (test module): line count of one file.
- **Guards:** none.
- **Mocks:** none.
