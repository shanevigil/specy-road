# Harness landscape (standing research topic)

## Purpose

specy-road builds its own harness layer: it launches and resumes the vendor coding CLIs (Claude Code,
Codex CLI, Cursor `agent`) on the user's own subscription logins, parses their streams, normalises
usage, leases slots, guards tool calls and checks each run afterwards. Two reasons to keep watching
how others build agent harnesses and orchestration:

1. **Parity.** Keep specy-road's shapes close to how mature systems do the same job, so adopters meet
   familiar ideas and specy-road copies proven patterns instead of inventing them. The roster split
   into core fields and a typed `run:` block (M16.63) follows Kestra, GitHub Actions and Vibe Kanban.
2. **Buy vs build.** The 2026-11-05 decision was to keep building and adopt patterns only (Option A in
   the report below). Reopen it when a better fit appears; the triggers are listed below.

The full analysis is
[`slimming-2026-11-05/research-orchestration-patterns.md`](slimming-2026-11-05/research-orchestration-patterns.md)
(sections 2, 4.1 and 5).

## Watchlist

One line per entry, then what to watch for.

| Entry | What it is | Watch for |
|---|---|---|
| Kestra | JVM workflow server; task `type` plus a nested typed `taskRunner` | Changes to the task-runner split; how its 2.0 migration tool handled breaking config (a model for `upgrade`) |
| GitHub Actions runner model | `runs-on` / `uses` plus per-action validated `with:` | Changes to action input validation and runner labels; the pattern behind the typed `run:` block |
| Vibe Kanban | Local multi-CLI worktree runner; executor kind plus named variants | Its executor variants (the idea behind optional named run profiles); harnesses it adds; licence and maintenance |
| ACP and acpx | Agent Client Protocol (JSON-RPC over stdio) and a headless ACP client (alpha, Node) | Standard usage reporting in core ACP; `session/resume` and model selection; Cursor's native `agent acp` documenting usage; acpx leaving alpha or dropping runtime `npx` downloads |
| Claude Agent SDK | Anthropic's SDK that runs the Claude Code binary | Licence and dependency weight; the auth policy for subscription logins; typed messages and hooks that could replace the Claude parser |
| OpenAI Agents SDK | An agent loop over model APIs | Any mode that drives a CLI rather than calling APIs (today it is the wrong layer) |
| Codex app-server | `codex app-server --stdio`, JSON-RPC with resumable threads | A stable usage payload on `turn/completed`; the Python wrappers leaving "experimental" |
| Temporal | Durable execution server | A serverless or embedded mode light enough for a no-daemon, file-based design |
| Dagger | Container engine with function modules | Sandbox isolation that works with OAuth logins held in the keychain |
| OpenHands | Agent stack and agent server (REST/WebSocket, Docker) | Running external CLI agents over ACP; a lighter embedding |
| LiteLLM | Model API proxy with a price table | Supply chain: two PyPI compromises in 2026 (March; October per a single source). Do not depend on it or vendor its price data; watch only for its incident record |
| Claude Squad | Go TUI; tmux plus a worktree per agent (AGPL-3.0) | Worktree and session patterns; the licence rules out embedding |
| Conductor | macOS app for parallel coding agents | Whether it is maintained (reportedly not since Aug 2026, single source) |
| OpenTelemetry GenAI semantic conventions | Standard names such as `gen_ai.usage.input_tokens` (status: Development) | The spec reaching stable; the session-versus-turn usage question that `worker_usage_delta` handles |

## Triggers that reopen buy vs build

Any one of these reopens the decision; record the run in the log below.

- A maintained open-source package drives at least two of the CLIs specy-road uses, reports usage,
  and runs from Python or as a standalone binary, with no daemon.
- Core ACP gains standard usage reporting, or Cursor's `agent acp` documents usage, resume and model
  selection (then add an `acp` harness, Cursor first, stdlib JSON-RPC; Option B in the report).
- specy-road moves Claude workers to API billing (then the Claude Agent SDK becomes a candidate for
  the Claude slice; Option C in the report).
- A vendor CLI removes or changes its documented one-shot or resume mode, so keeping our adapter
  costs more than adopting a maintained one.

## Risks to keep in view

- **Claude Code `--bare` becoming the default for `-p`.** Bare mode does not read OAuth, so
  subscription-billed `claude -p` workers would break or switch to API billing when the default
  changes. Mitigation from the report: a preflight that detects bare-by-default (from `system/init`
  capabilities or the CLI version) and passes the opt-out explicitly, with a test fixture.
- **Subscription logins for SDK and `-p` agents.** The Agent SDK overview says third-party products
  must not offer claude.ai login unless approved, and the headless docs describe `claude -p` as the
  Agent SDK via the CLI. specy-road launches the user's own CLI under the user's own login, which is
  arguably different. This policy question is open; get a clear answer before orchestration is
  marketed as core.

## Cadence

Each minor release, or monthly while a minor release is open, whichever comes first. A run reads the
vendor docs and the watchlist entries' own pages, checks the triggers and risks, and adds one dated
entry below. Findings that need work become roadmap leaves or intake entries; this file records only
what changed and where it went.

## Log

- **2026-11-05.** First run:
  [`slimming-2026-11-05/research-orchestration-patterns.md`](slimming-2026-11-05/research-orchestration-patterns.md).
  Decision: keep building, adopt patterns only (Option A). The roster split into core fields and a
  typed `run:` block is planned in M16.63 and M16.64. No trigger fired: ACP has no standard usage,
  acpx is alpha and downloads adapters at run time, and the Claude Agent SDK steers to API keys.
