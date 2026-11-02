# Implementation summary: M8.4 — Ship skills once and meter every file each harness injects

Branch `feature/rm-ship-skills-once-and-meter-every-file-each-harness-injects`, base `a82ae3b`.

## A1 — skills written once; prune and validate warning for `.cursor`/`.codex` copies

- **Already true, now tested:** `specyrd init` (cursor, claude-code, codex) writes each skill once to
  `.agents/skills/<name>/SKILL.md`, plus the `.claude/skills/<name>` link for Claude Code. It writes
  nothing under `.cursor/` or `.codex/`. Git history shows specy-road never wrote `.cursor/skills` or
  `.codex/skills`, so a copy there was made by hand or by another tool.
- **Detection** (`specyrd_skills.mirrored_copies`): it looks for a `specyrd-*` copy of an *installed*
  skill (the canonical `SKILL.md` exists) under `.cursor/skills/`, `.codex/skills/` or
  `.cursor/commands/`. Each copy is sorted into one of two lists:
  - **disposable:** a symlink to the canonical skill, a one-file copy byte-equal to the canonical
    `SKILL.md`, or a verbatim specyrd stub (`generated_match`, the same test `--force` uses).
  - **kept:** anything else, such as a copy someone edited.

  It skips three cases:
  - paths the manifest records, so a `generic` pack pointed at `.cursor/commands` is that pack's and
    not a copy;
  - a mirror directory that resolves to `.agents/skills`, because deleting through it would delete
    the canonical skill;
  - a mirror directory that resolves outside the repository.
- **Prune:** `refresh_stubs` adds the disposable copies to its orphan list, so
  `refresh-stubs --prune` and `upgrade --prune` delete them with the existing `_prune`. Without
  `--prune` they are listed, not deleted. The kept copies are never deleted.
  `refresh_stubs.py` stays at its 400-line cap: the change is one line, and two comment lines were
  folded together.
- **Validate:** `specyrd_init.warn_if_skills_mirrored` (called from `validate_at`) prints one non-fatal
  `skills: warning — …` line on stderr naming every copy. It suggests `upgrade --prune` for the
  disposable ones and says to delete the kept ones by hand. It resolves the git root, because the
  copies sit there in a nested layout. `--strict` counts it like any other warning.

## A2 — per-harness injected-file meter (`agents_md_block.py`)

- `injected_context` now returns a dict keyed `Codex`, `Claude Code`, `Cursor` and `Copilot`. The one
  caller that unpacked the old tuple, `tests/test_enforced_rules_pointers.py`, was updated to match.
- **Cursor:** `AGENTS.md` and `CLAUDE.md` in each directory from the git root down to the project
  root, plus the rules under `.cursor/rules/` (`.mdc`/`.md`, nested folders included) whose
  YAML frontmatter sets `alwaysApply` to a YAML true (`true # comment`, `True`, `yes`). Rules scoped
  by glob or description load only when they match, so they are not counted against "every
  session"; this choice is documented. A rule whose frontmatter does not parse is not counted.
- **Copilot:** `AGENTS.md` and `.claude/CLAUDE.md` in the git root and the working directory, plus
  `.github/copilot-instructions.md` at the git root.
- **Output:** neither Cursor nor Copilot documents a size limit, so each prints a `context:` line
  with its total and never warns.
- **Codex:** the 32 KiB chain is unchanged. When the Codex-home file is a global
  `AGENTS.override.md`, its machine-local note now adds that every Codex session on the machine
  reads it in place of the `AGENTS.md` beside it.
- **Docs:** `docs/install-and-usage.md` documents the per-harness list, the override note and the
  skill-copy prune/warning. The file stays at its 400-line cap: existing lines were extended, none
  added.

## Touch zones (confirmed)

All edits are inside the listed zones:
- `specy_road/specyrd_skills.py`
- `specy_road/specyrd_init.py`
- `specy_road/bundled_scripts/refresh_stubs.py`
- `specy_road/bundled_scripts/upgrade.py` (docstring and `--prune` help only)
- `specy_road/bundled_scripts/validate_roadmap.py`
- `specy_road/agents_md_block.py`
- `docs/install-and-usage.md`
- `tests/`

`specy_road/templates/specyrd/` needed no change.

## Verification

- New and affected tests: `tests/test_skill_mirrors.py`, `tests/test_context_meter_harnesses.py`,
  `tests/test_agents_md_block.py`, `tests/test_enforced_rules_pointers.py`: 56 passed.
- `specy-road file-limits`: OK. `ruff check specy_road tests scripts`: OK.
  `scripts/check_test_private_imports.py`: 0 new.
- Dogfood fixture: `validate`, `export --check` and `digest --check` all OK. The `.specyrd/cache`
  those manual runs leave in the fixture was removed before the full suite ran.
- `scripts/check_clones.py` was **not run**: `pylint` is not installed in this environment.
- Full `pytest` (with `-p no:cacheprovider`): 2955 passed, 2 skipped (before the review fix below).

### Review fix (gpt-6.1-sol, A2 block)

- Finding: a Cursor rule with `alwaysApply: true # always` was not counted, because a regex matched
  the raw line.
- Fix: `_always_applied` now parses the frontmatter with the existing
  `planning_artifacts.split_frontmatter` (`yaml.safe_load`; it returns `{}` for frontmatter that is
  unparsable or not a mapping). A rule counts only when `alwaysApply` is the YAML boolean true. The
  `_ALWAYS_APPLY` regex is gone.
- The existing public meter test now covers: an inline comment and `True` (counted); a quoted
  `"true"` and unparsable frontmatter (not counted).
- Reran, touched files only: `tests/test_context_meter_harnesses.py`, `tests/test_agents_md_block.py`,
  `tests/test_enforced_rules_pointers.py`: 47 passed. `specy-road file-limits` and `ruff` are OK.

## Added

- `specyrd_skills.MIRROR_DIRS`: the three directories (`.cursor/skills`, `.codex/skills`,
  `.cursor/commands`) where a copy duplicates an `.agents/skills` skill.
- `specyrd_skills._mirror_rel`: maps a command to its copy's path: a flat `.md` file under
  `commands/`, a skill folder elsewhere.
- `specyrd_skills._is_disposable_copy`: the guard that only a link to the skill, a byte-equal copy or
  a verbatim stub is pruned, so nothing anyone wrote is lost.
- `specyrd_skills.mirrored_copies`: detection shared by prune and validate. Its guards: skip
  manifest-recorded paths (`generic` pack), skip names with no canonical skill, skip a mirror
  directory that resolves to `.agents/skills` or outside the repository.
- `refresh_stubs.refresh_stubs`: one line that adds the disposable copies to the orphans `--prune`
  deletes.
- `specyrd_init.warn_if_skills_mirrored` and its call in `validate_at`: the A1 validate warning.
- `agents_md_block._CURSOR_CANDIDATES`, `_CURSOR_RULES`, `_COPILOT_CANDIDATES`,
  `_COPILOT_REPO_FILE`: the per-harness file lists (A2).
- `agents_md_block._always_applied`: a Cursor rule is counted only when its YAML frontmatter
  (parsed with the existing `split_frontmatter`) sets `alwaysApply` true; unparsable frontmatter is
  not counted.
- `agents_md_block._cursor_paths`, `_copilot_paths`: the files each harness injects (A2).
- `agents_md_block._note_suffix`: the global `AGENTS.override.md` note for Codex (A2).
- `tests/test_skill_mirrors.py`: init writes nothing under `.cursor`/`.codex` (all three skill
  packs); the disposable vs kept split; `upgrade --prune` removes the copies and keeps edited and
  unrelated skills, with the warning before and after; without `--prune` copies are listed and not
  deleted; a `generic` pack in `.cursor/commands` is not a copy; a `.cursor/skills` link to
  `.agents/skills` is never pruned; a copy with no installed skill is ignored. The helper
  `_flat_stub` builds a verbatim flat stub via a `generic` init in a sibling directory, to avoid a
  new private import.
- `tests/test_context_meter_harnesses.py`: Cursor files and the `alwaysApply` filter (including an
  inline comment, `True`, a quoted string and unparsable frontmatter); Cursor's walk
  into a nested project; Copilot's files in the root and the working directory; one line per
  harness and no warning past 32 KiB for Copilot.
- Changes to existing tests:
  - `test_agents_md_block.py`: the exact-output test now expects the Cursor and Copilot lines; the
    Codex-home tests assert the override note appears only for an override.
  - `test_enforced_rules_pointers.py`: uses the dict API.
- Mocks: none.
