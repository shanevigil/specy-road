# Harness compatibility triage (research of 2026-10-28)

Two deep-research reports (one Claude, one OpenAI) answered the prompt
"coding-agent harness capabilities as they relate to specy-road". This note
records what specy-road takes from them. The reports themselves are not
tracked; every claim below is vendor-documented unless marked **unverified**.

**Caveat that governs everything here:** neither report ran a harness binary or
read harness source. Version numbers disagree between them (for example Claude
Code 2.1.310 vs 2.1.312, Gemini CLI 0.44 vs 0.65), and both say so. Nothing
below is "verified at runtime" until the verification leaf (M8.7) runs it.

## Where the reports agree

1. **Keep every specy-road command a deterministic tool.** Both reports map
   each of specy-road's commands to *duplicate* (keep ours) or *gap* (no
   harness equivalent with the same state contract). Neither recommends
   re-implementing any of them on a harness feature. The shipped
   `specyrd-*` skills and the managed `AGENTS.md` block are the only
   *complements*: the adapter layer from model intent to the CLI.
2. **Harness-owned orchestration conflicts with specy-road-owned
   orchestration.** Worktree creation (`claude --worktree`, `/batch`,
   `codex --worktree`, `agent -w`), session forking, cloud agents (Cursor
   Cloud Agents, Copilot `/delegate` and the cloud coding agent, Claude
   routines), PR automation (`/split-to-prs`, `/autopilot`) and autonomous
   loops (`/loop`, `/goal`, `--autopilot`, `--fleet`) each create a second
   owner for branches, workers or landing. All are **avoid**.
3. **Hidden memory and harness planning must not become project state.**
   Claude auto memory (repository-scoped, shared across worktrees), Codex
   memories (`memories.use_memories` and `memories.generate_memories` both
   default on), Copilot Memory, Gemini/Antigravity `/learn`, and plan modes
   everywhere. **Avoid**, with the documented switch where one exists.
4. **Native review is advisory only.** `/code-review`, `codex review`,
   Cursor `/review*`, Copilot `/review` produce comments or chat, not
   `work/reviews/<ID>/REVIEW-<model>.md`, and none enforces distinct
   families or reruns per commit. Useful as an executor self-check; never
   gate evidence.
5. **Exit code 0 is not success.** Claude prints in-run failures as the
   stdout result; Codex documents one failure exit; Copilot documents none
   for `-p`; Gemini treats a would-ask policy as deny when headless. A
   deterministic post-run check must look at the event stream
   (`permission_denials`, `is_error`, `turn.failed`, `api_retry`) and at
   `git status`, not at the exit code.
6. **Instruction files and skills are loaded more than once.** Cursor reads
   `AGENTS.md` *and* `CLAUDE.md` and scans `.agents/skills`, `.cursor/skills`,
   `.claude/skills` and `.codex/skills`; Copilot reads `AGENTS.md`,
   `.claude/CLAUDE.md` and `.github/copilot-instructions.md` and scans three
   skill directories. specy-road's mirrored stub packs are therefore loaded
   three to four times by those harnesses, and the context meter undercounts.
   Almost every harness reads `.agents/skills`; only Claude Code needs
   `.claude/skills`.
7. **Structured final output is the right verdict channel.** Claude
   `--json-schema` (`structured_output`), Codex `-o` / `--output-schema`,
   Antigravity `--json-schema`. specy-road should write the review record
   from that JSON instead of asking the model to emit valid frontmatter.
8. **Gemini CLI is a dead end for new work.** Google moved unpaid and Google
   One users to Antigravity CLI (`agy`) on 2026-06-18; `agy -p` documents
   output formats, conversation ids, `--mode accept-edits` and a JSON schema
   flag. Treat `agy` as a `generic` harness candidate; do not invest in a
   Gemini CLI adapter.
9. **Cursor and Copilot are the multi-family reviewers.** Both select the
   model by name across vendors from one harness; Claude Code and Codex
   reach one family each. Copilot `-p` with `--resume` is undocumented, so
   it is a one-shot reviewer, not an executor, until verified.
10. **Nested project roots are undocumented everywhere.** No vendor states
    whether model-created relative paths resolve against the cwd or the
    repository root. specy-road already launches workers at the git root and
    names git-root-relative paths in prompts and briefs (M3.9); keep that.

## Per-harness facts specy-road will act on (documented, not runtime-verified)

| Harness | Unattended invocation | Session | Permissions | Git | Avoid |
|---|---|---|---|---|---|
| Claude Code | `claude -p … --output-format stream-json`; since 2.1.302 `-p` starts in a mode that silently denies unapproved tools, so pass `--permission-mode` and `--allowedTools` (or `--bare` plus `--append-system-prompt-file` for the brief); `--permission-prompts none` | `--session-id <uuid>` / `--resume <id>`; never `--continue` across worktrees | `acceptEdits` or `dontAsk` + allow rules; `bypassPermissions` only inside an external sandbox | commits when asked; attribution trailer on by default | auto memory, `/batch`, `--worktree`, `/fork`, `/background`, routines, `/loop` wakeups (`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`) |
| Codex CLI | `codex exec --json -o <file> …`; `--full-auto` no longer supported | thread id in `thread.started`; `codex exec resume <id>`; `--last` is cwd-scoped | `--sandbox workspace-write` (exec default is read-only); `approval_policy` never prompts | **`.git` and the linked gitdir are read-only inside `workspace-write`: the executor cannot commit** | memories (both switches false; per-profile `CODEX_HOME`), `--worktree`, `exec fork`, cloud tasks; `~/.codex/AGENTS.override.md` silently replaces the global file |
| Cursor CLI | `agent -p --force --trust --model <m> --output-format stream-json` | `agent create-chat` returns the id; `--resume <id>`; `agent ls` is not headless | `--force` is broad; pair with hooks or an external sandbox | `-w` makes its own worktrees under `~/.cursor/worktrees` | `-w`, `/split-to-prs`, `/autopilot`, Cloud Agents, `/create-rule` and `generate-rule`, plan mode |
| Copilot CLI | `copilot -p … -s --output-format json --allow-tool … --deny-tool …` | `--resume <id>` (with `-p`: unverified) | deny rules win over `--allow-all` | cloud agent creates branches and PRs | `/delegate`, cloud agent, `--plan`, `--autopilot`, `--fleet`, Copilot Memory (switch unknown); deny `shell(git push)` and `shell(gh pr:*)` |
| Antigravity `agy` | `agy -p … --mode accept-edits --new-project --print-timeout <n> --output-format stream-json` | `--conversation <id>` | `--mode` | unknown | `/learn`, `/goal`, `/schedule`; shared `default-cli-project` |

## What specy-road changes (roadmap phase M8)

- **M8.1 Harness facts drive profiles.** A tracked facts fixture (one record
  per harness: version, headless command, session flags, permission example,
  instruction files and size guidance, skill directories, hooks, autonomous
  git actions and their switches, model families, quota behaviour,
  evidence) from which `refresh-profiles` renders `model-profiles/` and the
  executor command templates. On a version bump the diff of `--version`,
  `--help` and inventories is classified before the refresh is accepted; any
  new identifier containing plan, memory, task, todo, worktree, branch,
  commit, push, PR, background, delegate, cloud, schedule, review, resume,
  fork or autopilot fails the diff until it is assigned a relationship.
- **M8.2 Adapters harden the launch.** Claude: permission flags, no
  prompts, retry watchdog with a capped usage-limit wait, a *paused by
  limit* worker state that `worker resume` picks up after the reset. Codex:
  `exec --json`, `workspace-write`, memories off, per-profile `CODEX_HOME`.
  Cursor: `create-chat`, `--force --trust`, no `-w`. Every adapter runs a
  deterministic post-run check: permission denials, failed turn, api retry,
  empty diff, and git state (HEAD, branch, stash, porcelain) unchanged
  except for the expected files.
- **M8.3 Verdict capture.** Reviewer runs are read-only; the adapter asks
  for structured output matching the review-record schema and specy-road
  writes `REVIEW-<model>.md` itself. Removes the invalid-frontmatter rerun
  class seen in this run.
- **M8.4 Ship skills once.** `specyrd init` writes `.agents/skills` plus
  `.claude/skills` and stops mirroring into `.cursor/` and `.codex/`;
  `upgrade --prune` removes the copies. The context meter counts, per
  harness, every file it actually injects (Cursor: `AGENTS.md`, `CLAUDE.md`,
  `.cursor/rules`; Copilot: `AGENTS.md`, `.claude/CLAUDE.md`,
  `.github/copilot-instructions.md`; Codex: the 32 KiB chain and a note when
  `AGENTS.override.md` exists).
- **M8.5 Guard hooks and avoid lists.** Checked-in, per-harness hook files
  that deny `git commit`/`push`/`gh pr` for reviewer roles and `push`,
  `gh pr`, worktree and cloud commands for executors (Claude and Codex have
  documented blocking hooks; Cursor's are reported). Each model profile
  carries its avoid list with the exact switch.
- **M8.6 Candidate harnesses.** A Copilot CLI reviewer profile and an
  Antigravity `agy` generic profile, each gated on the runtime checks.
- **M8.7 Runtime verification (Human-led).** Run the reports' verification
  guide against installed binaries in a scratch repository with a linked
  worktree and a nested project root: versions and help, denial behaviour
  and exit codes, commit-when-asked from a subdirectory, create/resume by id
  from a sibling worktree, instruction-sentinel loading versus the meter,
  Cursor `-p` with and without `--force`, Claude usage-limit events with the
  watchdog, forbidden-commit hook test, sibling-worktree concurrency. Its
  results replace the **unverified** labels in the facts fixture.

## Decision for the maintainer

**Codex cannot commit inside its documented sandbox.** specy-road's executor
contract asks the worker to commit its own work. Options: (a) run Codex
workers with a broader sandbox and rely on the guard hook instead; (b) let
the adapter make the checkpoint commit on the worker's behalf after each
turn (author = the model profile, trailer recorded); (c) keep Codex as a
reviewer only. Both reports lean to (b) by implication (the harness should
never own commits). Decided (2026-10-29): (b), the adapter commits on the worker's behalf; M8.2 implements it.

## Relation to the research register

M7.2 ("run the harness-capabilities research and fold its findings") is
done in substance by this note; its register entry is written when M7.1
exists. Cadence recorded for the register: refresh on every supported
harness version bump, and in full each minor release.
