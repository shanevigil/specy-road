# 0.3.1: workers behind the coordinator (research reconciled)

**Status:** built 2026-10-27 (7a–7d merged to `WIP/improvements-0-3-1`;
reference `../orchestration-workers.md`; real-harness checks in
`../agentic-sandbox-runbook.md` §5). Reconciles the external research on
IDE-native, cross-harness orchestration against what slices 1–6 built. All
decisions below are taken; "7c as built" records what changed in the
building.

## Inputs

- The research prompt ("IDE-Native, Cross-Harness Multi-Agent Orchestration for
  Specy-Road"), run by the maintainer in two assistants on 2026-10-27: a ChatGPT
  deep-research report (728 lines) and a Claude research report (653 lines, 74
  sources). Both were temporary files in the repo root and are **not
  committed**; this note keeps what matters from them. Neither run executed
  anything: every rating is from documentation and public issue trackers.
- The 0.3 slices already built: `docs/design-notes/v0-3-0-orchestration-slices.md`
  and `docs/design-notes/agent-guidance-and-shared-checkouts.md`.

## What the report recommends

The ChatGPT report rates every orchestrator host and worker interface it could
verify from public documentation (no live IDE was available to it, so nothing
in it is a tested proof of concept) and settles on its **Architecture B**:

1. One portable control surface the orchestrating model calls from whatever IDE
   chat it already sits in: an Agent Skill plus an MCP server owned by
   specy-road. Never drive a vendor's chat UI, never make a PTY the control plane.
2. A deterministic local **worker supervisor** that makes no decisions: it
   launches workers, persists their identity, and keeps a durable event log.
   Lazily started; no UI of its own.
3. **Vendor adapters** below it, using each harness's documented programmatic
   interface: Codex app-server first, Claude Agent SDK/CLI, Cursor ACP/SDK.
   Adapters declare capabilities (`steer`, `interrupt`, `resume`,
   `live_attach`, …) and return `unsupported` rather than emulate.
4. **Harness and model are distinct identities.** An execution target is at
   least `(harness, model, environment, billing_route)`; a Claude model in the
   Cursor harness is a Cursor session.
5. **Single-writer lease** per worker session (`orchestrator | human |
   handoff_pending | none`): no local harness documents safe concurrent writers,
   and Anthropic's extension warns that opening one session twice mixes
   messages. Human intervention is an **event** with an `instruction_epoch`,
   captured by a prompt-submit hook where the harness has one; otherwise the
   worker is marked `possibly_modified_externally` at the next sync.
6. Precedence when a human redirects a worker: hard task constraints → explicit
   contract amendment → the human's direction → orchestrator strategy → the
   worker's own idea. A conflict with touch zones, dependencies or a gate puts
   the worker in `needs_reconcile`.
7. **No portable wake-up** of the orchestrator exists. `delegate` must return
   immediately; completion reaches the coordinator through a durable queue, an
   explicit `sync`/`worker_events` call, and host notifications where available.
8. The specy-road **event log is authoritative** for orchestration state; vendor
   transcripts are evidence.
9. Skills: one canonical source plus thin per-harness adapters (done, slice D).
10. cmux is optional presentation for humans to see and enter a worker terminal,
    never the message API. VS Code's native sessions are an accelerator, not the
    portability boundary (`chatSessionsProvider` is still a proposed API).
    JetBrains (ACP host) is the natural second-wave target; Windsurf is not.
11. Idempotent delegation keyed to task/attempt, per-task ownership, bounded
    concurrency, worktree ownership stored apart from process identity,
    credentials by reference only, redacted event payloads.

Its MVP estimate is four to six developer-weeks for three adapters, durable
state, the MCP tool surface and basic IDE registration.

## Where the Claude run agrees, and what it adds

The Claude report reaches the same Architecture B independently and shares
every point above. It adds, and this note takes:

- **Licensing posture.** Anthropic does not allow third parties to offer
  claude.ai login; OpenAI publicly endorses Codex subscriptions in third-party
  harnesses; Cursor's SDK needs `CURSOR_API_KEY`. Launching the user's own
  installed CLI under the user's own auth is the defensible route for every
  vendor, and the Agent SDK path for Claude may bill differently from the
  plan (unverified, in flux). This settles D2 in favour of the CLIs.
- **Codex app-server is marked Experimental** by OpenAI ("isn't supported for
  production workloads"); the old `codex mcp-server` is removed. Another reason
  to start from `codex exec` and keep app-server behind the adapter protocol.
- **Human attach is unavailable for `-p`/SDK workers everywhere.** Claude's
  `claude --bg` / `claude attach` cannot combine with `-p`; Codex has no
  documented attach to a UI-owned thread (issue #25914); Cursor's SDK has none.
  So the human path is a **handoff**: stop or wait for idle, checkpoint (native
  turn, git HEAD), lease → `human`, print the native resume command
  (`claude -p --resume <id>` / `codex exec resume <thread>` / `agent --resume
  <id>`), then **reclaim** diffs what happened. The report names these
  `worker handoff` / `worker reclaim`; this note adopts the names.
- **Intervention detection, two signals.** Primary: native turns the broker
  did not issue (Codex `thread/read`, Claude session JSONL, Cursor `listRuns`).
  Secondary: prompt-submit hooks (project config, so they fire in the human's
  session too) and git changes in the worktree outside broker turns. For
  0.3.1 the CLI adapters have only the secondary signals — Claude's JSONL is
  documented as internal and changing, and the other two need the long-lived
  protocols — so a reclaim without hook evidence marks the worker
  `possibly_modified_externally` rather than claiming a full account.
- **`adopt`.** A worker the user started natively can be registered
  (`worker adopt --harness codex --session <id>`) as observe-only.
- **Idempotent operations** by a client-supplied `op_id`, not only idempotent
  delegation; a crash-safe outbox of pending operations.
- **Wake-up options that exist today:** Claude Code cross-session messaging
  (a Claude worker can message a Claude orchestrator, v2.1.224+), Claude Code
  Channels (research preview, CLI only, ignored under `-p`), and Cursor's
  `stop` hook `followup_message` (bounded, turn-end only). All optional; the
  pull path stays the contract.
- **Concurrency cap** of two or three workers by default, since each worker
  draws on the user's plan quota; event logs hold prompts and code, so they
  stay gitignored and redacted.
- A **Copilot** adapter (headless CLI server, `resumeSession`) and a generic
  **ACP** adapter as the long-tail path (42 agents in the ACP registry).

Where the two differ: the Claude run wants a per-repo **broker daemon**
(asyncio, unix socket, SQLite) auto-started by the first call, the ChatGPT run
a lazily started supervisor with no UI. Both want it because an MCP stdio
server dies with its host chat. See D3 for why 0.3.1 ships neither.

## Already built, and how it maps

| Report element | What exists (slice) | Gap |
| --- | --- | --- |
| Canonical skill + per-harness adapters | `.agents/skills/<name>/SKILL.md`, `.claude/skills` symlink, `--ai codex` (D) | none |
| Orchestrator stays in its IDE chat | `/specyrd-orchestrate` loop over `orchestrate plan`, `prompt`, `handoff status` (3, 5) | the loop blocks on `prompt --channel cli` and polls files by hand |
| Launch a worker on another harness | `prompt --channel cli` runs the profile's `access.cli` **synchronously** (2) | no worker id, no session id kept, no resume, no events |
| Worker/presence registry | `work/.sessions/<agent>.yaml`, self-written, TTL (guidance 5/6) | nothing is written for a launched process; advisory only |
| Durable event log | none; `work/reviews/<ID>/READY-*.md` is the one completion signal (1) | new |
| Human intervention capture | guard hook adapters for Claude Code, Codex, Cursor on *tool calls* (5) | no prompt-submit hook, no event, no epoch |
| Harness vs model identity | roster `id/family/profile/channels`; profile `access.cli` names a harness implicitly (2) | no `harness` field; `billing_route` absent |
| Capability flags | profile `access.subagents`, `effort_controls`; roster `channels` (2) | per-adapter flags (`resume`, `interrupt`, …) absent |
| Worktree per task | `do-next-available-task` claims; `grind-session` worktrees; shared-checkout rule | no worker ↔ worktree binding record |
| Idempotent delegation | one claim per leaf in `registry.yaml` (1, 4) | a crashed launch can be re-run blindly |
| Completion → review gate | READY → packet → `review record` → gate, signed (1, 6) | unchanged; workers end by writing READY |
| Authority precedence, `needs_reconcile` | touch-zone stop rule in the orchestrate skill (5) | no state, no reconcile command |
| MCP server | none; every harness reaches specy-road through its shell | *open*, see D1 |

Nothing built so far has to change shape. The report's supervisor and event
log sit **beside** presence files and review records, in `work/`, and the
review gate stays the only completion authority.

## Decisions

**D1 (decided 2026-10-27: CLI only; no MCP server for now) — control
surface.** The report leads with an MCP server. Every harness in scope (Claude Code, Codex, Cursor, VS Code chats)
already runs shell commands, which is how the whole toolkit is driven today,
and the maintainer's standing rule is that the CLI never talks to a model API
itself. Recommendation: ship the orchestrator-facing surface as
`specy-road worker …` subcommands with `--json`, and update the orchestrate
skill to call them. An MCP server wrapping the same functions is a later,
optional extra (`pip install specy-road[mcp]`), useful mainly for hosts that
cannot run a shell. The report's own first experiment (prove the tool call is
visible) holds for either surface.

**D2 (decided 2026-10-27 as recommended) — adapter order and depth.** The report puts Codex app-server
first because it is the richest protocol. For 0.3.1 the recommendation is the
**documented one-shot CLIs with resume**, one adapter per harness, in this
order: `claude-code` (`claude -p`, JSON output, `--resume`), `codex`
(`codex exec`, JSON events, `resume`), `cursor` (`agent -p`, `--resume`).
They cover launch, events, completion and resume with a subprocess and no
long-lived JSON-RPC client; interrupt and steer are declared `unsupported`
where the CLI has no documented way. App-server and ACP adapters come later
behind the same protocol, and are what unlock interrupt/steer. The exact flags
are being verified against current docs before any adapter is written; a
profile's `access.cli` string stays the fallback for an unknown harness.

**D3 (decided 2026-10-27 as recommended) — no daemon.** Both reports want a resident broker because an MCP
stdio server dies with its host chat. With a CLI surface (D1) nothing has to
outlive the call except the worker itself, so the "supervisor" is the CLI
plus one **detached wrapper process per worker** (`start_new_session`, no
inherited stdio): it runs the harness CLI in the worktree, tails its JSON
output into the event log, and writes the exit. No socket, no lockfile, no
SQLite. State lives in files under `work/.workers/` (gitignored like
`work/.sessions/`, always in the main worktree): `<worker-id>.yaml` for the
record, `<worker-id>.events.jsonl` for the append-only log, `ops/<op-id>.yaml`
for the idempotency outbox. Restart recovery is reading the record, checking
the wrapper PID and native session id, and resuming through the adapter. The
long-lived protocol adapters (app-server, ACP) will need a resident process
holding the JSON-RPC connection; when they come it is the same per-worker
wrapper, not a per-repo daemon.

**D4 — harness is a first-class field.** Roster entries gain `harness` (enum
`claude-code | codex | cursor | generic`; `generic` = run `access.cli`) and an
optional `billing_route` label. `models show` and `worker list` print
`harness/model`, never the model alone. Schema change → adopters run
`refresh-schemas`, the path decisions A/B already use.

**D5 — writer lease, epoch, intervention events, `needs_reconcile`.** All in
7a, file-based. Lease holder is `broker | human | native | none`.
`worker message` refuses with `WORKER_LEASED_BY_HUMAN` while the lease is
`human`; `worker handoff` waits for idle (or terminates, since the CLI
adapters cannot interrupt), checkpoints, sets the lease and prints the native
resume command; `worker reclaim` diffs the worktree since the checkpoint,
reads any hook-recorded prompts, emits one `intervention` event
(`authority: human_authoritative`, epoch +1) and returns the lease. The
prompt-submit hooks of all three harnesses (Claude Code and Codex
`UserPromptSubmit`, Cursor `beforeSubmitPrompt`; verified against current
docs 2026-10-27) record the prompt when the session id matches a worker;
without hook evidence the worker is marked `possibly_modified_externally`. `worker reconcile`
compares events since the last sync with the leaf's touch zones and
dependencies and sets `needs_reconcile`; a conflicting human direction waits
for the user to confirm it in the coordinator chat as a contract amendment.

**D6 — dependencies.** None added for 7a–7c. MCP (D1) would be the first
optional extra; cmux is called as an external executable if present, never
embedded (its client is GPL-3.0-or-later).

**D7 — what completion means.** A worker finishing is an event, not an approval.
The worker still writes READY; `worker events` surfaces it; the coordinator
runs the review path exactly as before. This keeps the gate (and signed
reviews) the single authority the report asks for.

## Slice 7: scope for 0.3.1

**7a — worker contract.** `specy_road/worker_state.py`: `WorkerRecord`
(`worker_id`, `node_id`, `harness`, `model`, `provider_session_id`,
`worktree`, `branch`, `pid`, `state`, `lease`, `instruction_epoch`,
`contract_hash` = the leaf's brief hash, `checkpoint`, `last_event_seq`,
timestamps), `append_event()` / `events_since(seq)`, lease transitions, the
`op_id` outbox, idempotent delegation keyed `<node_id>:<attempt>`.
Package-owned schemas `worker-record.schema.json` and
`worker-event.schema.json` (validated from the package, like review records).
Roster `harness` / `billing_route`; policy `max_workers` (default 2).

**7b — adapters.** `specy_road/worker_adapters.py`: a `WorkerAdapter`
protocol (`capabilities()`, `launch()`, `send()`, `events()`, `interrupt()`,
`resume()`, `terminate()`) and the three CLI adapters plus `generic`. Each
returns a `Capabilities` record; unsupported operations raise one typed error
the CLI prints as `unsupported by <harness>`. Launch runs the harness in the
leaf's worktree with the prompt file `prompt` already writes.

**7c — `specy-road worker` CLI.** `delegate <ID> --model <roster id>` (plan
eligibility → claim → worktree → launch → returns the worker id at once),
`list`, `status <W>`, `events <W> [--since N]`, `sync` (every worker's delta
since the last sync, compact, acknowledges what it returned), `message <W>`,
`interrupt <W>`, `resume <W>`, `terminate <W>`, `handoff <W>`, `reclaim <W>`,
`adopt --harness H --session ID`, `reconcile <W>`, `open <W>` (prints the
best human-access target: resume command, worktree, log tail). All with
`--json` and `--op-id`. Prompt-submit hook adapters for intervention
(`session guard` gains a sibling `worker hook`). `/specyrd-orchestrate`
rewritten around `worker delegate` and `worker sync` (call `sync` at the start
of every turn); `handoff status` lists workers beside sessions.

**7c as built (2026-10-27).** `delegate` runs *after pickup*: it requires a
registry claim with a branch and refuses otherwise, because pickup switches
branches and pushes the registry — not something a coordinator's checkout
should do on a worker's behalf. The worktree is the coordinator's checkout
when it has the claim's branch checked out, else a linked worktree under
`work/.worktrees/<codename>`. `sync` keeps its acknowledgement marks in
`work/.workers/sync.yaml`. A roster `channels.cli` may carry `{session}` so
one custom command also serves `message`/`resume`; without it the default
resume command is used. `interrupt` exits 2 for every CLI adapter.
`reclaim` with no hook evidence writes the intervention from the diff stat
alone and sets `possibly_modified_externally`.

**7d — docs and hygiene.** `docs/orchestration.md` (already at the 400-line
cap: workers get `docs/orchestration-workers.md`), `optional-ai-tooling-patterns.md`
hook snippets, `suggested_prompts/`, CHANGELOG `[Unreleased]`, this note.

**Deferred past 0.3.1** (recorded so they are not lost): MCP server extra;
Codex app-server, Cursor SDK/ACP and Copilot long-lived adapters (interrupt,
steer, native history diff); generic ACP adapter; wake-ups (Claude
cross-session messaging, Claude Channels, Cursor `stop`-hook follow-up);
`--viewer cmux`; VS Code tree-view extension and session deep links; Claude
Managed Agents backend; JetBrains via ACP.

## Where this diverges from the report

- CLI before MCP (D1): the hosts in scope have shells, and the toolkit's
  contract is files and commands; an MCP layer is a wrapper, not a new source
  of truth.
- One-shot CLIs before app-server/ACP (D2): smallest change that gives
  launch/resume/events on all three harnesses; capability flags make the
  missing interrupt/steer explicit rather than faked, which is the report's
  own rule.
- No supervisor process (D3): a daemon is a new failure mode in a toolkit that
  has none; file state plus detached children gives the same restart recovery.

## Verification

Automated (fake harness binary in tests): delegate returns before the worker
finishes; events are appended and read back after the CLI process exits;
idempotent re-delegate; lease refusal; intervention epoch increments; reconcile
flags a touch-zone breach; resume after a killed worker; `unsupported`
reported, not emulated; schema validation of records and events; `handoff
status` and `orchestrate` skill text. The reports' PoC scenarios that need a
live, authenticated IDE (Cursor orchestrator, VS Code harness comparison,
Claude session double-open, which plan quota a `-p` worker draws from, cmux
attach) are listed in `docs/orchestration-workers.md` as manual checks with
pass criteria, and are not claimed until run.
