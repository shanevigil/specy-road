# Implementation summary for M5.3

## Summary

`specy-road validate` now meters the context every agent session pays before its first prompt. After the `OK` line it prints one `context:` line per harness on stdout, listing each instruction file that harness injects into a session started in the project root, with its lines and bytes and those of the specy-road managed section inside it, against the documented limit:

- **Codex** reads every `AGENTS.md` from the git root down to the working directory and truncates them at `project_doc_max_bytes`, 32 KiB by default ([source](https://developers.openai.com/codex/guides/agents-md)). The line shows the combined bytes out of 32,768.
- **Claude Code** reads `CLAUDE.md` on that path, or the `AGENTS.md` files when there is no `CLAUDE.md`, and documents "target under 200 lines per CLAUDE.md file" ([source](https://code.claude.com/docs/en/memory)).

When a limit is exceeded (combined `AGENTS.md` over 32,768 bytes; any file Claude Code reads over 200 lines), `validate` prints a `context: warning —` line on stderr naming the file and what to do. It is a warning like the others, so `validate --strict` fails on it (A1, A2).

On this repository's nested `sr/` layout:

```text
context: Codex reads AGENTS.md 57 lines, 6,056 bytes; sr/AGENTS.md 54 lines, 7,632 bytes (specy-road section 52 lines, 7,606 bytes) — 13,688 of its 32,768-byte project_doc_max_bytes budget
context: Claude Code reads CLAUDE.md 113 lines, 7,973 bytes — target under 200 lines per file
```

I chose `validate` over a new `context show` command because `specy_road/cli.py` is outside the touch zones. The report is printed only by the `validate` command, not by the other `validate_at` callers (pickup, `add-node`, `upgrade`), so their output does not change. The warning sits in `validate_at` next to the other agent-guide warnings, so it reaches those callers the same way `warn_if_agents_md_block_stale` does.

## Changes

- `specy_road/agents_md_block.py`: limit constants with source URLs, `InjectedFile`, `injected_context`, `print_injected_context`, `warn_if_context_over_limits`.
- `specy_road/bundled_scripts/validate_roadmap.py`: calls the warning in `validate_at` and the report in `main`.
- `docs/install-and-usage.md`: one paragraph under "Everyday workflow (PM)". The file was already at its 400-line cap, so the new paragraph is a single line and the three-line paragraph above it is unwrapped (same words) to keep it at 400.
- `tests/test_agents_md_block.py`, `tests/test_validate_strict.py`.

Final touch zones: as listed. `specy_road/agent_guide_block.py` was not edited; only its `AGENT_GUIDE` constant is imported. `validate_roadmap.py` is also in the `stale-command-check` (M5.2) session's paths in another worktree; my change there is an import plus two calls, so expect a small merge to reconcile.

## Verification

- `python -m pytest -q`: 2255 passed, 2 skipped
- `specy-road file-limits`: OK
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK
- Manual: `python -m specy_road.cli validate --repo-root sr` (output above)

## Walkthrough

1. Run `specy-road validate` in any project and read the two `context:` lines after `OK`.
2. Append 201 lines to `CLAUDE.md`, or pad `AGENTS.md` past 32,768 bytes, and run it again: a `context: warning —` line appears and `validate --strict` exits 1.

## Added

- `CODEX_PROJECT_DOC_MAX_BYTES`, `CLAUDE_MD_TARGET_LINES`: the documented limits, as constants with their source URLs (the planning sheet's Approach).
- `InjectedFile` + `describe()`: one measured file and its specy-road section, and the text the report prints for it.
- `_measure`: reads one file's lines and bytes and its managed section's lines and bytes (reuses `managed_block._split`).
- `injected_context`: which files each harness reads, from the git root down to the project root (reuses `runtime_paths.git_root`).
- Branch `found(AGENT_GUIDE) or agents`: Claude Code reads `AGENTS.md` only when no `CLAUDE.md` is on the path (vendor docs).
- Branch `git_root(...) or project_root`: a project outside a git repository measures only its own directory.
- Branches `if codex:` / `if claude:` in the report: no line for a harness that reads no file.
- Branch `if self.block_size` in `describe`: no section clause for a file without a specy-road block (for example a git-root `AGENTS.md` in a nested layout).
- `print_injected_context`: the A1 report, called from `validate`'s `main`.
- `warn_if_context_over_limits`: the A2 warnings, called from `validate_at`.
- Test `test_context_meter_reports_what_each_harness_reads`: the exact report for a nested layout (both `AGENTS.md` files for Codex; Claude Code falling back to them, then switching to `CLAUDE.md`).
- Test `test_context_warnings_fire_only_past_a_documented_limit`: no warning at exactly 32,768 bytes and 200 lines; one warning each at 32,769 bytes and 201 lines.
- Test parametrization of `test_strict_fails_a_validation_that_warned` with `_overlong_claude_md`: `validate` itself emits the warning and `--strict` fails on it. The existing acceptance case is kept as the other parameter, so `_scaffold` lost its `acceptance` flag and that edit moved into `_clear_acceptance`.
- Assertions added to `test_strict_passes_a_fresh_scaffold`: the `validate` command prints both `context:` lines, and a fresh scaffold stays warning-free.
- Mocks: none.
