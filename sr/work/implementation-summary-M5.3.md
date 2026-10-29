# Implementation summary for M5.3

## Summary

`specy-road validate` now meters the context every agent session pays before its first prompt. After the `OK` line it prints one `context:` line per harness on stdout, listing each instruction file that harness injects into a session started in the project root, with its lines and bytes and those of the specy-road managed section inside it, against the documented limit:

- **Codex** ([Custom instructions with AGENTS.md](https://developers.openai.com/codex/guides/agents-md)) walks from the git root down to the working directory. In each directory it takes the first non-empty file of `AGENTS.override.md`, then `AGENTS.md` (empty files are skipped; at most one file per directory), and truncates the combined result at `project_doc_max_bytes`, 32 KiB by default. The line shows the combined bytes out of 32,768. The same page's global layer (the Codex home) is outside this project walk.
- **Claude Code** ([How CLAUDE.md files load](https://code.claude.com/docs/en/memory), and the AGENTS.md section on the same page) loads `CLAUDE.md`, `.claude/CLAUDE.md` and `CLAUDE.local.md` from the working directory and every ancestor, filesystem root down. A project file suppresses the `AGENTS.md` fallback; `~/.claude/CLAUDE.md` does not. The fallback is every `AGENTS.md` and `.claude/AGENTS.md` on that walk. The documented target is under 200 lines per file, and it applies only to files inside the git root.
- **Outside the git root** is a note, labelled user-level / machine-local, with the file's lines and bytes, and it never warns and never fails `validate --strict`. That covers ancestor instruction files, `~/.claude/CLAUDE.md` (still its own `Path.home()` candidate, deduplicated against the walk), and Codex's global layer: the first non-empty of `AGENTS.override.md`, then `AGENTS.md`, in the Codex home. [The same AGENTS.md page](https://developers.openai.com/codex/guides/agents-md) (it now redirects to https://learn.chatgpt.com/docs/agent-configuration/agents-md) says that home "defaults to `~/.codex`, unless you set `CODEX_HOME`", so it is `$CODEX_HOME` when set, else `~/.codex` (review round 7).

When a limit is exceeded by a file inside the git root (the selected Codex files over 32,768 bytes; a Claude file at 200 lines or more), `validate` prints a `context: warning —` line on stderr naming that file. Notes are not part of that check. An ignored sibling, such as an `AGENTS.md` next to a non-empty `AGENTS.override.md`, is neither reported nor warned. The warning is like the others, so `validate --strict` fails on it (A1, amended A2: limits apply to files in the repository).

On this repository's nested `sr/` layout the Claude line now includes the checkout's ancestor `CLAUDE.md`, which sits above this worktree's git root:

```text
context: Codex reads AGENTS.md 57 lines, 6,056 bytes; sr/AGENTS.md 54 lines, 7,632 bytes (specy-road section 52 lines, 7,606 bytes) — 13,688 of its 32,768-byte project_doc_max_bytes budget
context: Claude Code reads CLAUDE.md 113 lines, 7,973 bytes — target under 200 lines per file
context: note — /Users/savigil/WORKSPACE/specy-road/CLAUDE.md 113 lines, 7,973 bytes, user-level / machine-local; not counted toward this repository's limit
```

I chose `validate` over a new `context show` command because `specy_road/cli.py` is outside the touch zones. The report is printed only by the `validate` command, not by the other `validate_at` callers (pickup, `add-node`, `upgrade`), so their output does not change. The warning sits in `validate_at` next to the other agent-guide warnings, so it reaches those callers the same way `warn_if_agents_md_block_stale` does.

## Changes

- `specy_road/agents_md_block.py`: limit constants with source URLs, `InjectedFile`, `injected_context`, `print_injected_context`, `warn_if_context_over_limits`.
- `specy_road/bundled_scripts/validate_roadmap.py`: calls the warning in `validate_at` and the report in `main`.
- `docs/install-and-usage.md`: one paragraph under "Everyday workflow (PM)". The file was already at its 400-line cap, so the new paragraph is a single line and the three-line paragraph above it is unwrapped (same words) to keep it at 400. Review round 1 names `.claude/CLAUDE.md` in that same line. Review round 7 names the Codex home there as `$CODEX_HOME`, else `~/.codex`.
- `tests/test_agents_md_block.py`, `tests/test_validate_strict.py`.

Final touch zones: as listed. `specy_road/agent_guide_block.py` was not edited; only its `AGENT_GUIDE` constant is imported. `validate_roadmap.py` is also in the `stale-command-check` (M5.2) session's paths in another worktree; my change there is an import plus two calls, so expect a small merge to reconcile.

## Verification

- `python -m pytest -q`: 2255 passed, 2 skipped
- `specy-road file-limits`: OK
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK
- Manual: `python -m specy_road.cli validate --repo-root sr` (output above)
- Review round 1: `python -m pytest -q tests/test_agents_md_block.py tests/test_validate_strict.py` — 15 passed; `specy-road file-limits` — OK
- Review round 2: the same pytest command — 19 passed; `specy-road file-limits` — OK
- Review round 3: the same pytest command — 20 passed; `specy-road file-limits` — OK
- Review round 5: the same pytest command — 21 passed; `specy-road file-limits` — OK
- Merge of `origin/WIP/improvements-0-3-1` (M5.1 rule provenance): import-only conflicts in `agents_md_block.py` and its test, both imports kept. `pytest -q tests/test_agents_md_block.py tests/test_validate_strict.py` plus the M5.1 guide-block, refresh-stubs and lean-rules tests — 52 passed; `python -m pytest -q` — 2301 passed, 2 skipped; `specy-road file-limits` — OK
- Review round 7: `python -m pytest -q tests/test_agents_md_block.py tests/test_validate_strict.py` — 24 passed; the same run with `CODEX_HOME` set to a missing directory — the Codex tests pass; the new test fails with the old `~/.codex` lookup; `specy-road file-limits` — OK

## Walkthrough

1. Run `specy-road validate` in any project and read the two `context:` lines after `OK`.
2. Write 200 lines to a `CLAUDE.md` inside the git root, or put a non-empty `AGENTS.override.md` past 32,768 bytes next to an `AGENTS.md`: a `context: warning —` line names that file and `validate --strict` exits 1. The same files above the git root, or in the Codex home (`$CODEX_HOME`, else `~/.codex`), are a `context: note` labelled user-level / machine-local and `--strict` still passes.

## Added

- `CODEX_PROJECT_DOC_MAX_BYTES`, `CLAUDE_MD_TARGET_LINES`: the documented limits, as constants with their source URLs (the planning sheet's Approach).
- `InjectedFile` + `describe()`: one measured file and its specy-road section, and the text the report prints for it.
- `_measure`: reads one file's lines and bytes and its managed section's lines and bytes (reuses `managed_block._split`).
- `injected_context`: dispatches to the two walks below (reuses `runtime_paths.git_root` as Codex's ceiling only).
- `_CODEX_CANDIDATES`, `_codex_paths`: per directory, first non-empty of `AGENTS.override.md` then `AGENTS.md`. The size check is the documented skip of empty files (review round 2).
- `_CLAUDE_CANDIDATES`, `_CLAUDE_AGENTS_FALLBACK`, `_claude_paths`: ancestor walk from the filesystem root, the three Claude filenames, and the `AGENTS.md` / `.claude/AGENTS.md` fallback (review round 2). Replaces `_CLAUDE_PROJECT_DOCS`, which stopped at the git root.
- `_inside`: a path is metered only when it is inside the git root (review round 5).
- `_codex_home_file`: the non-empty `AGENTS.override.md` or `AGENTS.md` in the Codex home, the global layer on the Codex page. The home is `CODEX_HOME` when set, else `~/.codex` (review round 7; it was always `~/.codex`).
- `_machine_local_paths`: everything discovered outside the git root, plus the home candidates when the walk did not already include them. Replaces `_without_user` and `_user_level_claude`. `warn_if_context_over_limits` never sees this list (review round 5).
- `_dirs_from_root`, `_present`, `_display`, `_measured`: the shared walk, the filename filter, absolute paths above the git root, and measurement.
- Branch `git_root(...) or project_root`: outside a git repository Codex measures only that directory. Claude still walks its ancestors.
- Branches `if codex:` / `if claude:` in the report: no line for a harness that reads no file.
- Branch `if self.block_size` in `describe`: no section clause for a file without a specy-road block (for example a git-root `AGENTS.md` in a nested layout).
- `print_injected_context`: the A1 report, called from `validate`'s `main`.
- `warn_if_context_over_limits`: the A2 warnings, called from `validate_at`. The Claude check is `lines >= 200`, matching the printed target of under 200 (review round 1; it was `>`).
- Test `test_context_meter_reports_what_each_harness_reads`: the exact report for a nested layout (both `AGENTS.md` files for Codex; Claude Code falling back to them, then switching to `CLAUDE.md`).
- Test `test_context_warnings_fire_only_past_a_documented_limit`: no warning at exactly 32,768 bytes and at 199 lines; one warning each at 32,769 bytes and at 200 lines (review round 1 moved the Claude boundary from 201).
- Test `test_dot_claude_claude_md_suppresses_the_agents_fallback`: with only `.claude/CLAUDE.md` as a Claude file (and an `AGENTS.md` present), Claude Code's line reports that file and its managed section, and Codex's line still reports `AGENTS.md`.
- Test `test_claude_walks_ancestors_and_falls_back_to_dot_claude_agents`: an ancestor `CLAUDE.md` and a `CLAUDE.local.md` are reported and suppress both `AGENTS.md` files; removing them makes the line report `AGENTS.md` and `.claude/AGENTS.md` (review round 2).
- Test `test_user_claude_md_under_home_is_listed_once`: with the repo under `HOME`, the user path appears once, on the note, labelled user-level / machine-local, and the repository line still reports `AGENTS.md` (review round 3; replaces the round-2 test of the same layout).
- Test `test_user_claude_outside_home_is_noted_and_does_not_fail_strict`: the repo is not under `HOME`, the user file is 201 lines, `validate --strict` exits 0 with an empty stderr, and stdout names the file once with the label (review round 3; the label is now user-level / machine-local).
- Test `test_ancestor_claude_above_the_git_root_does_not_fail_strict`: a 201-line `CLAUDE.md` above the git root is a note and `validate --strict` exits 0. Replaces `test_strict_warns_when_an_ancestor_claude_file_hits_200_lines`, which asserted the opposite under the earlier A2 (review round 5).
- Test `test_codex_user_layer_is_a_note`: `~/.codex/AGENTS.override.md` is the note and the oversized sibling `~/.codex/AGENTS.md` is neither reported nor warned (review round 5).
- `test_context_meter_reports_what_each_harness_reads` sets `HOME` to an empty directory so its exact stdout does not pick up a real `~/.claude/CLAUDE.md`. It and `test_codex_user_layer_is_a_note` also unset `CODEX_HOME`, so a developer's own Codex home cannot leak into them (review round 7).
- Test `test_codex_home_env_moves_the_user_layer`: with `CODEX_HOME` set to a temp directory, its `AGENTS.md` is the user-level / machine-local note and the `~/.codex/AGENTS.md` under `HOME` is not reported (review round 7). It fails with the old hardcoded `~/.codex`.
- Test `test_codex_meters_a_nonempty_override_instead_of_agents_md`: an empty override leaves the over-budget `AGENTS.md` as the measured and warned file; a non-empty override replaces it in both the report and the warning (review round 2).
- Test parametrization of `test_strict_fails_a_validation_that_warned` with `_overlong_claude_md`: `validate` itself emits the warning and `--strict` fails on it. The existing acceptance case is kept as the other parameter, so `_scaffold` lost its `acceptance` flag and that edit moved into `_clear_acceptance`.
- Assertions added to `test_strict_passes_a_fresh_scaffold`: the `validate` command prints both `context:` lines, and a fresh scaffold stays warning-free.
- Mocks: none. The user-file tests set `HOME` so `Path.home()` is the fixture; they do not patch a production name.
