# Implementation summary: M11.61 `meter-claude-rules-and-nested`

Branch `feature/rm-meter-claude-rules-and-nested`, base `de7cfc6c`, code commit `a68df116`.

## What changed

- **A1 — Claude rules and auto memory.** The Claude Code line now counts every `.md` under
  `.claude/rules/` (recursive), in each directory from the git root down to the project root,
  after the CLAUDE.md family. A rule whose frontmatter sets `paths` is left out: Claude Code
  loads it only when it works on a matching file (same treatment as Cursor's non-`alwaysApply`
  rules). Rules do not suppress the `AGENTS.md` fallback. The auto-memory file
  `~/.claude/projects/<repo>/memory/MEMORY.md` is a machine-local note giving the file's size
  and the part Claude Code loads (first 200 lines or 25 KB, whichever comes first). `<repo>` is
  the main checkout's absolute path with non-alphanumerics replaced by `-`, found through
  `git rev-parse --git-common-dir`, so every worktree resolves the same file (checked against
  this machine: the worktree run found the session's real memory file).
- **A2 — Cursor nested and Copilot path instructions.** Cursor gets a note line after its
  counted line listing every `AGENTS.md` below the git root that is not on the path to the
  project root ("applies … when the agent edits a file below it; not counted per session"),
  found with `git ls-files --cached --others --exclude-standard` so ignored trees are not
  walked. Copilot now counts `.github/instructions/**/*.instructions.md` in the git root.
- **A3 — 4 MiB cap.** A Claude instruction file (CLAUDE.md family, AGENTS fallback, rules,
  `~/.claude/CLAUDE.md`) over 4 MiB is dropped from the Claude count and the user-level notes.
  Inside the git root it is a `context: warning` on stderr (like the 200-line warning, so
  `--strict` fails on it); outside it is a note. A file of exactly 4 MiB still counts.
- **Docs.** `docs/install-and-usage.md` context-meter paragraph covers the new files.

## Touch zones

Final list: `specy_road/agents_md_block.py`, `docs/install-and-usage.md`, `tests/`, plus the
**new module `specy_road/harness_instruction_files.py`**. The new candidates would have taken
`agents_md_block.py` (372 lines) past the 400-line cap, so, as the planning sheet suggested,
the per-harness path discovery (constants and the `_codex/_claude/_cursor/_copilot_paths`,
`_machine_local_paths`, `_always_applied` family) moved there unchanged apart from dropping the
leading underscore on names now imported across modules. `agents_md_block.py` keeps the
measuring and reporting and re-exports `AGENTS_MD`; it is now 297 lines, the new module 222.

## Verification

- `ruff check specy_road/agents_md_block.py specy_road/harness_instruction_files.py tests/test_context_meter_rules_memory_nested.py` = 0
- `specy-road file-limits` = 0
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` = 0
- `pytest -n auto` = 0 (3254 passed, 2 skipped)

## Open points for review

- The 4 MiB, 200-line / 25 KB and nested-AGENTS.md behaviours come from the sourced Claude
  research report; the memory-directory name encoding (non-alphanumeric → `-`) matches the
  directory on this machine but is not quoted in that report. A path long enough for Claude Code
  to hash would simply find no file and print no note.
- `25 KB` is taken as 25,000 bytes (`CLAUDE_MEMORY_BYTES`).
- Whether an over-4 MiB `CLAUDE.md` still suppresses the `AGENTS.md` fallback is undocumented;
  the meter keeps the present-file rule it already used.

## Added

### Helpers (`specy_road/harness_instruction_files.py`)
- `claude_rules` — the unconditional `.claude/rules/**/*.md` from the git root down (A1).
- `_frontmatter` — shared frontmatter read for Claude `paths` and Cursor `alwaysApply`; replaces the inline read in `_always_applied`.
- `claude_loads` — the 4 MiB size check (A3).
- `claude_skipped` — every present Claude file over the cap, deduplicated by resolved path (A3).
- `_main_worktree` — main checkout from `--git-common-dir`, so worktrees share one memory dir (A1).
- `claude_memory_file` — locates `MEMORY.md` under `~/.claude/projects/<repo>/memory/` (A1).
- `claude_memory_loaded` — lines/bytes of the first 200 lines capped at 25 KB (A1).
- `cursor_nested_agents` — nested `AGENTS.md` off the project path, via `git ls-files` (A2).
- Constants `CLAUDE_MAX_FILE_BYTES`, `CLAUDE_MEMORY_LINES`, `CLAUDE_MEMORY_BYTES`, `_CLAUDE_RULES`, `_COPILOT_INSTRUCTIONS` — the documented limits and paths.

### Helpers (`specy_road/agents_md_block.py`)
- `_roots` — resolved project root and git root, shared by the three entry points.
- `_not_loaded` — the one "over 4 MiB, loads none of it" phrase used by the warning and the note (A3).
- `_print_machine_local` — machine-local notes (existing loop, plus memory and over-cap notes), split out to keep `print_injected_context` short.

### Branches / guards
- `copilot_paths` appends `.github/instructions/**/*.instructions.md` (A2).
- `injected_context` adds rules to Claude's list and filters it by `claude_loads` (A1, A3).
- `machine_local_paths` drops over-cap Claude files so they are not described as read (A3).
- `print_injected_context` prints the Cursor nested note after the Cursor line (A2).
- `warn_if_context_over_limits` warns for an over-cap Claude file inside the git root (A3).

### Mocks
- none (tests use real temp git repos and a `HOME` override).

### Tests (`tests/test_context_meter_rules_memory_nested.py`)
- `test_claude_counts_rules_recursively_beside_the_claude_md_family` — recursive rules, `paths`-scoped and non-`.md` left out, nested project rules (A1).
- `test_auto_memory_is_a_machine_local_note_shared_by_worktrees` — memory note text and loaded part, not in the counted line, same file from a worktree (A1).
- `test_auto_memory_load_stops_at_25_kb_before_200_lines` — the byte cap wins over the line cap (A1).
- `test_cursor_notes_nested_agents_md_below_the_root` — nested note, on-path and ignored files excluded (A2).
- `test_copilot_counts_its_path_specific_instructions` — recursive `*.instructions.md`, other files excluded (A2).
- `test_claude_file_over_4_mib_is_reported_not_loaded_never_counted` — in-repo warning, machine-local note, exact-cap file still counted (A3).
