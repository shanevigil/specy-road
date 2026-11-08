# Implementation summary: M16.1.5

AGENTS.md is the one agent entry with a task-conditional load order; CLAUDE.md is a pointer.

Base `5dce867e`; implementation commit `c83385c5`; fix round 1 after merging `origin/WIP/improvements-0-3-1` (`b781d827`); fix round 2 after merging it again (`9c39ce3e`); fix round 3 after merging it again (`ef13dd25`); fix round 4 after the coordinator's zone change (`d36e40ef`), merged at `439228ac`.

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

## Fix round 1 (review by gpt-6.1-sol at `1cb6cefc`)

- **A3 (fixed, in zone).** Class: a file in the unconditional part of a load order that the test leaves out of its count. `load_order_paths` deliberately leaves out the digest, so `roadmap-context.md` (item 0 of the consumer order, before "By task") went uncounted. `_always_load_order` now adds the digest when the unconditional part names it. The consumer closure is now 161 lines, and a missing digest fails the existing missing-file check. The toolkit's `AGENTS.md` names `sr/roadmap-context.md` only under "By task", so it is not counted.
- **A1 (not fixed: needs paths outside the touch zones).** Class: policy restated outside its one canonical place. These copies remain, and each needs a zone added before it can become a link:
  - `docs/contributor-guide.md` § Default branch is `dev` (lines 98-105): says all feature work targets `dev` and contradicts the WIP-base rule.
  - `.cursor/rules/026-release-version-tag-sync.mdc:8`: the "Human owns the number" bullet.
  - `docs/release-runbook.md:9`: restates the version rule.
  - `docs/release-runbook.md:150`: the WIP topic-branch base.
  - `docs/git-workflow.md:6`: still points at `CLAUDE.md` for the branch policy.
- **A4 (not fixed: needs paths outside the touch zones).** Class: provenance comments kept in shipped block templates. Removing the 27 comments from `specy_road/templates/specyrd/agents-rules.md` breaks the parametrized `tests/test_agents_md_block.py::test_every_rule_in_a_block_template_is_followed_by_its_provenance`. It also empties `chore_garden`'s advisory-rule scan (`specy_road/bundled_scripts/chore_garden.py`, which reads `_RULE_TEMPLATES`). The same class reaches `agents-md-block.md` (8 comments) and `claude-md-block.md` (2). A design that removes the class for all three is to move the comments into a maintainer-only provenance file and point `chore_garden`, `agent_guide_block.strip_provenance`'s callers and that test at it. The coordinator needs to add these zones: `specy_road/bundled_scripts/chore_garden.py`, `specy_road/agent_guide_block.py`, `specy_road/agents_md_block.py`, `tests/test_agents_md_block.py`, `tests/test_chore_mode.py`, the two other block templates, and a new provenance file (e.g. `docs/design-notes/agent-rules-provenance.md`, which does not ship).

## Fix round 2 (review by gpt-6.1-sol at `b1a38442`)

- **A3 (fixed, in zone).** Class: a file every agent is told to read, but counted only when a harness happens to import it.
  - **The gap:** `.specyrd/AGENTS.team.md` was counted only through `CLAUDE.md`'s `@` import. A consumer initialised without Claude Code (Codex or Cursor only) left it, and `.specyrd/AGENTS.md` itself, out of the total. The same held for `.specyrd/AGENTS.local.md`.
  - **The rule now (stated in the test docstring):** the managed files the `AGENTS.md` stub tells every agent to read (`RULES_MD`, `TEAM_MD`, `LOCAL_MD`, the public constants in `harness_instruction_files`) are counted when present, whatever the harness imports.
  - **Test change:** the existing test is parametrized with a third case, `consumer-no-claude` (`init project` only). It counts 150 lines; the claude-code consumer counts 161.
  - **Limit:** a project's own files that its addenda point to are not followed. The budget covers what specy-road tells every agent to read, not what a project adds.
- **A1 and A4 (still not fixed: the touch zones are unchanged).** The registry row on `origin/WIP/improvements-0-3-1` still lists the same eight zones. Every path both findings need is outside them, so this leaf stops there again; the full lists are under Fix round 1.
  - **A1 needs:** `docs/contributor-guide.md`, `docs/release-runbook.md`, `docs/git-workflow.md`, `.cursor/rules/026-release-version-tag-sync.mdc`.
  - **A4 needs:** `specy_road/bundled_scripts/chore_garden.py`, `specy_road/agent_guide_block.py`, `specy_road/agents_md_block.py`, `tests/test_agents_md_block.py`, `tests/test_chore_mode.py`, `specy_road/templates/specyrd/agents-md-block.md`, `specy_road/templates/specyrd/claude-md-block.md`, plus a new provenance file that does not ship.
  - **Coordinator's choice:** add these zones (or split them into a follow-up leaf), or narrow A1 and A4. Editing them from here would break the executor rule against changes outside the zones.

## Fix round 3 (review by gpt-6.1-sol at `33cc8191`): blocked on touch zones

The review repeats the round 1 and round 2 findings A1 and A4 unchanged. No new input shape was named and A3 is no longer listed. After merging `origin/WIP/improvements-0-3-1` at `ef13dd25`, this leaf's registry row still lists the same eight touch zones, and both findings need only paths outside them. This round therefore changes no product file. The executor rules forbid edits outside the zones, and editing the registry or the acceptance is the coordinator's job.

- **A1 needs:** `docs/contributor-guide.md` (lines 98-105), `docs/release-runbook.md` (lines 9 and 150), `docs/git-workflow.md` (line 6), `.cursor/rules/026-release-version-tag-sync.mdc` (line 8).
- **A4 needs:**
  - **Code:** `specy_road/bundled_scripts/chore_garden.py` and `specy_road/agent_guide_block.py` (which read the provenance from the templates), and `specy_road/agents_md_block.py`.
  - **Tests:** `tests/test_agents_md_block.py`, which requires the comments to stay in the template, and `tests/test_chore_mode.py`.
  - **Templates:** `specy_road/templates/specyrd/agents-md-block.md` and `claude-md-block.md`, which carry the same class of comment (8 and 2).
  - **New file:** a maintainer-only provenance resource outside `specy_road/templates/`, so it is not in the wheel's `templates/**/*` package data.
- **Coordinator options:** add these zones to M16.1.5; split A1's other copies and A4 into a follow-up leaf, with this leaf's acceptance narrowed to match; or rule on the interpretation. Another automatic fix round under the current zones cannot clear either finding.

## Fix round 4 (coordinator resolution at `d36e40ef`)

- **A1 (fixed).** Class: the branch policy or the version-numbers rule restated outside its canonical place. The canonical places are `docs/toolkit-development.md` § Maintainer workflow vs consumer workflow for the branch policy, and `AGENTS.md` § Version numbers (human-owned) for the version rule. Each copy now links there:
  - `docs/contributor-guide.md` § Default branch is `dev` → § Branch policy, a link. The old text said "all feature work targets `dev`", which contradicted the WIP-base rule, and "`main` is intentionally minimal until v0.1", which is stale. No file linked the old anchor.
  - `docs/release-runbook.md:9`: the "Must know" version line now links to `AGENTS.md`.
  - `docs/release-runbook.md:150`: the WIP-base sentence in the pre-release steps now links to the branch policy.
  - `docs/git-workflow.md:6`: "Not for" now points to `toolkit-development.md` instead of `CLAUDE.md`.
  - `.cursor/rules/026-release-version-tag-sync.mdc:8`: the "Human owns the number" bullet is now a link to `AGENTS.md`, which removes the 026 → 027 → AGENTS.md hop.
  - `AGENTS.md` § Coordination: the "Branches" line's parenthetical summary of the policy was dropped, leaving only the link.
- **A4 (narrowed by the coordinator; met).** Acceptance now asks only that the shipped `agents-rules.md` cite files an adopter has. `tests/test_agent_start_up_reading.py::test_shipped_rules_cite_only_files_an_adopter_has` checks it, and the load order names only files a fresh consumer repo has (checked by the start-up test's missing-file assertion). Provenance comments are unchanged; moving them is M16.1.12.

## Fix round 5 (review at `14b8efb8`)

- **A1 (fixed).** Class: a branch-target statement that contradicts the canonical branch policy. Round 4 caught the section copy but missed the guide's "Must know" summary line.
  - **The fix:** `docs/contributor-guide.md:9` said "Feature work targets `dev`; `main` takes release-marker PRs only". It now links to the branch policy in `docs/toolkit-development.md`. `AGENTS.md` § Coordination points there as the policy's one statement, so the link skips the extra hop.
  - **Kept:** the guide's own branch-name regex and issue-link rule stay; they are CI conventions enforced by `pr-conventions.yml`, not the branch policy.

## Probes

- Digest in the consumer closure: now counted at 23 lines; total 161, under 400.
- Digest in the toolkit closure: `AGENTS.md` names `sr/roadmap-context.md` only under "By task", so it is not counted.
- Other unconditional items that `load_order_paths` skips: only placeholders containing `<`, i.e. `planning/<id>…`, which is under "By task" in both orders. Nothing else is skipped.
- Branch-policy copies (grep for `WIP/improvements-x-y-z`, "topic branch" and "default branch" in tracked docs and rules, excluding `sr/` and fixtures):
  - In zone: `AGENTS.md`, `docs/toolkit-development.md`.
  - Outside zones: `docs/release-runbook.md:150`, `docs/contributor-guide.md:98`.
- Version-rule copies (grep for "human-owned", "Human owns" and "VERSION DECISION"):
  - In zone: `AGENTS.md` (canonical), 027 (link).
  - Outside zones: 026:8, `docs/release-runbook.md:9`.
  - `constitution/principles.md:7` and `docs/release-runbook.md:109` name the principle or link to it rather than restating the rule; I left them as they are.
- Round 2, managed files: closure membership checked with and without `CLAUDE.md`. Both consumer cases now count `.specyrd/AGENTS.md` and `.specyrd/AGENTS.team.md`; `.specyrd/AGENTS.local.md` is counted when present (a fresh init creates none).
- Round 2, toolkit root: there is no root `.specyrd/AGENTS.md` (only `sr/.specyrd/`), so no managed file is added; the total stays at 238.
- Round 2, other files the rules tell agents to read: only the load order (already counted up to "By task") and the three managed files above. The rest are task-conditional (`docs/orchestration*.md`, brief) or generated per task (`work/brief-*`).
- Round 2, zones: the registry row on `origin/WIP/improvements-0-3-1` is unchanged, so A1 and A4 are still outside this leaf.
- Round 3, zones: the registry row on `origin/WIP/improvements-0-3-1` at `ef13dd25` is unchanged (the same eight paths), so A1 and A4 are still outside this leaf.
- Round 3, package data: `templates/**/*` ships the template file itself, which confirms A4 needs the comments moved out of `specy_road/templates/`. That needs the out-of-zone paths listed above.
- Round 4, branch-policy copies: grep across tracked `*.md`/`*.mdc` (excluding `sr/`, fixtures, CHANGELOG, design-notes) for "targets `dev`", `WIP/improvements-x-y-z`, "topic branch … from" and "branch from `dev`". After the edits, only `docs/toolkit-development.md` (canonical) and `AGENTS.md:23` match; the latter names the line `sr/` lives on and states no policy.
- Round 4, version-rule copies: grep for "never bump", "do not bump", "without the exact number" and "unless the user stated" finds only `AGENTS.md` (canonical). 026, 027 and `release-runbook.md:9` now link; `release-runbook.md:109` already linked.
- Round 4, broken anchors: nothing links `#default-branch-is-dev`; the new links target `#maintainer-workflow-vs-consumer-workflow` and `#version-numbers-human-owned`, which exist.
- Round 4, tests that read the edited docs: `tests/test_release_harness.py` (030 and runbook strings still present), `tests/test_refusals_name_their_fix.py` and `tests/test_sibling_repo_approvals.py` pass.
- Round 5, wider grep: tracked `*.md`/`*.mdc` (excluding `sr/`, fixtures, CHANGELOG, design-notes) for "targets `dev`", "work targets", "PR to/into `dev`" and "merge … into `dev`".
  - `contributor-guide.md:9`: fixed.
  - `toolkit-development.md:55`: the canonical text.
  - `contributor-guide.md:364`: states where Dependabot's PRs target (a repository configuration fact tied to the release gate), so it stays.
  - `release-runbook.md:843`: a runbook step's post-release docs PR target; the runbook owns release steps, so it stays.
- Provenance comments by template: `agents-rules.md` 27, `agents-md-block.md` 8, `claude-md-block.md` 2, `agents-team.md` 0.
- Readers of provenance comments: `agent_guide_block.py` (`PROVENANCE`, `strip_provenance`), `agents_md_block.py` (render), `chore_garden.py` (advisory-rule), and `tests/test_agents_md_block.py`, `tests/test_chore_mode.py`.

## Added

- **Test** `tests/test_agent_start_up_reading.py::test_start_up_reading_exists_and_stays_within_the_limit` (parametrized toolkit/consumer): A3, covering the start-up closure, the missing-file and supply-chain checks, and the 400-line gate.
- **Test** `tests/test_agent_start_up_reading.py::test_shipped_rules_cite_only_files_an_adopter_has`: A4, checking that every `docs/*.md` the rendered rules cite exists in a fresh consumer repo.
- **Helper** `_consumer` (test module): builds the fresh consumer repo both tests need.
- **Helper** `_always_load_order` (test module): the load order up to the "By task" line, read from the rules file in a consumer repo or from `AGENTS.md` in this one. Since fix round 1 it also includes the digest when that part names it, because `load_order_paths` leaves it out.
- **Helper** `_lines` (test module): line count of one file.
- **Guards:** none.
- **Mocks:** none.
