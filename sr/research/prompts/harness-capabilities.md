# Deep research: capabilities of the coding-agent CLIs that specy-road drives headlessly

## Who is asking and why

specy-road is an open-source toolkit that coordinates coding agents through a git-tracked roadmap. It never calls a model API itself. It launches each vendor's **own coding-agent CLI** as a headless worker in a git worktree: an *executor* implements one roadmap leaf, and *reviewers* from two different model families review it. specy-road keeps a per-harness facts record that drives its launch commands, model profiles and guardrails, so it needs **current, sourced facts** about each CLI, not impressions.

Treat the present date as the run date. Prefer facts that hold for the latest stable release, and give the version each fact was confirmed for.

## Harnesses in scope

1. **Claude Code** (Anthropic), headless as `claude -p`.
2. **OpenAI Codex CLI**, headless as `codex exec`.
3. **Cursor Agent CLI** (`agent` / `cursor-agent`), headless as `agent -p`.
4. **GitHub Copilot CLI** (documentation only; specy-road may add a reviewer profile).
5. **Google Antigravity CLI (`agy`)** and, if materially different, **Gemini CLI** (documentation only).

## Facts to establish, per harness

For each item give the answer, the exact flag or file name, the version it applies to, and a source.

1. **Version and release cadence.** Current stable version, release channel names, how often it changes, where the changelog lives.
2. **Headless invocation.** The non-interactive command; output formats (plain, JSON, streaming JSON); the shape of the final result record; exit codes for success, failure, refusal and interruption.
3. **Sessions.** Creating a session with a caller-chosen or returned id; resuming by id; whether resume works from a different directory or a sibling git worktree; where session state is stored.
4. **Permissions and sandboxing.** Permission modes and how to run fully non-interactively; how a denied action is reported in headless output and in the exit code; sandbox modes (read-only, workspace-write) and how to grant extra writable paths.
5. **Tool control.** Allow-lists and deny-lists of tools or shell commands; how to forbid `git push`, `gh pr`, and commits for a reviewer role.
6. **Instruction files.** Every file the harness injects automatically (for example AGENTS.md, CLAUDE.md, rules directories, override files, global or home-directory files), their precedence, whether nested directories are read, and any documented size limit or truncation.
7. **Skills, commands and subagents.** Directories read for skills or custom commands, file format, and whether symlinked skill folders are followed; native subagent or task-delegation features.
8. **Hooks.** Hook events, configuration location, whether a hook can block an action, and the exit-code or output contract for blocking.
9. **Autonomous git and workflow actions.** Whether the harness may create branches or worktrees, commit, push, open pull requests, or run in the cloud or background on its own, and the switch that turns each off.
10. **Memory, planning and todo features.** Persistent memory, plan mode, todo lists, background tasks, scheduled or cloud runs, "autopilot"-style modes: what each does and how to disable it in headless use.
11. **Models and effort.** Model families selectable, the model flag, and reasoning-effort or thinking controls with their accepted values and defaults.
12. **Quota and rate limits.** How a usage or rate limit surfaces in headless output (event, message, exit code), whether a reset time is given, and whether the CLI waits, retries or exits.
13. **Usage and cost reporting.** Token, turn and cost fields in headless output, and whether cost is an estimate.
14. **Known headless failure modes.** Documented or widely reported issues: a process that stays alive after the turn completes, interactive prompts that block headless runs, output that is buffered until exit, background jobs abandoned when the turn ends.

## Change watch

List every flag, subcommand, setting or feature added in roughly the last six months whose name or description involves any of: plan, memory, task, todo, worktree, branch, commit, push, pr, background, delegate, cloud, schedule, review, resume, fork, autopilot. For each, say what it does and whether it could act outside a single worker's assigned scope (for example committing, pushing, opening PRs, or spawning other agents), and how to disable it.

## Runtime verification guide

Write a short, concrete checklist a maintainer can run in a scratch repository to confirm the most important facts above on the installed versions: version and help output, a denied action's report and exit code, a commit requested from a nested subdirectory, creating a session and resuming it by id from a sibling worktree, which instruction files are actually read (sentinel lines), a usage-limit event, a hook that blocks a forbidden commit, and two sessions running concurrently in sibling worktrees.

## Sources and rigour

- Use primary sources first: vendor documentation, official changelogs and release notes, `--help` text quoted in official docs, and the vendors' own repositories. Mark anything from forums, blogs or issue threads as secondary, and say so.
- Quote the sentence that supports each fact, with the URL and the date read.
- Write "unknown" rather than guess. Flag contradictions between sources instead of resolving them silently.

## Output format

1. One section per harness, with a table: *item / answer / exact flag or file / version / source URL / quote / confidence (high, medium, low)*.
2. A cross-harness comparison table of items 2 to 6 and 9 to 12.
3. The change-watch list.
4. The runtime verification guide.
5. A short list of the facts most likely to break an automated headless worker, ranked by impact.
