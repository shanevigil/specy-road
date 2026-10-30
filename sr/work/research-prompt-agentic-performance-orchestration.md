# Deep research prompt: making specy-road's agentic use faster and better orchestrated

Date: 2026-10-30. Seed article: Martin Alderson, "Making agents fast"
(https://martinalderson.com/posts/making-agents-fast/).

## Role and goal

You are a senior engineer researching agent orchestration and agent performance on behalf of the
maintainers of **specy-road**, an open-source, roadmap-first coordination toolkit. Produce a
report that (1) verifies the landscape claims below, (2) maps the performance findings of the seed
article onto specy-road's actual execution loop, and (3) identifies orchestration patterns from
programmatic agent frameworks that specy-road should implement its own version of, under its design
constraints. Every recommendation must name the specy-road surface it changes and give an
impact/effort estimate.

## What specy-road is (read this before researching)

- A Python package plus validators and an optional PM UI. Consumer repos keep a canonical roadmap
  graph (`manifest.json` + JSON chunks), a registry (`roadmap/registry.yaml`), constitution,
  contracts, and planning narrative next to their code.
- It separates three roles around one roadmap leaf: **coordinator** (picks the leaf, creates
  branch/worktree, assembles the review packet, closes the gate, finishes), **executor** (reads a
  generated brief, changes only its touch zones, runs verifiers, commits, writes a hand-off file,
  stops), **reviewer** (reads only the review packet in a fresh session, records approve/block).
  The executor never reviews its own leaf. A review is a file bound to one commit; later commits make
  it stale. Policy lives in `roadmap/orchestration.yaml` (roster of models with family, roles,
  harness, profile; reviewers required; distinct-family rule; fresh-session rule; substitutions).
- **The key architectural difference from programmatic frameworks:** specy-road does not call model
  APIs. Its surface is the shell, and its "workers" are the vendors' own coding-agent CLIs run
  headless with resume (`claude -p`, `codex exec`, `cursor agent`, generic). Three recorded design
  decisions: **D1 no MCP server** (every harness can run a shell), **D2 CLI adapters** per vendor,
  **D3 no daemon** (a detached wrapper process per worker writes files that commands read). The
  intent is that each worker runs inside its vendor's full harness and therefore gets that harness's
  native skills, slash commands, hooks, built-in MCP servers, subagents, and permission model for
  free, rather than a thinner API-level reimplementation.
- Orchestration commands that exist today:
  - `specy-road grind-session --plan --json` — read-only planner: ready vs blocked leaves and
    `parallel_batches` (waves) for safe fan-out; `--step pickup` / `--step finish` for IDE-driven
    loops; `--implement-mode hook --implement-cmd …` for unattended loops; exit codes for
    dependency/gate blocks.
  - `specy-road worker delegate <NODE> --model <id>` — launch a claimed leaf on another harness;
    `worker sync [--ack]` run at the start of every coordinator turn to pull events; `message`,
    `resume`, `handoff`/`reclaim` (single-writer lease: broker | human | native), `terminate`,
    `reconcile`. Records live in `work/.workers/` as a YAML record plus an append-only JSONL event
    log (authoritative) and a raw output log (evidence). Interrupt is unsupported on every adapter.
  - `specy-road review-packet`, `review record`, `handoff status`,
    `mark-implementation-reviewed`, `finish-this-task` — the review gate, including a trial merge of
    the integration branch, escalation thresholds for repeated blocks and review rounds.
  - `specy-road prompt <NODE> --model <id> --role …` — generates role prompts from per-model
    profiles (limits, prices, headless CLI syntax, failure modes, prompting rules);
    `specy-road models list|show|stale`; `orchestrate plan` for routing against the roster.
  - `specy-road brief <NODE>` — the context packet an executor reads; `session start|guard` for
    presence when several agents share one checkout.
- Non-negotiables: tracked docs over chat; smallest change that satisfies the task; extend existing
  entrypoints before adding new ones; vendor neutrality (human, Claude Code, Cursor, Codex or a
  local model all fit any role).

## Part A. Verify the landscape claim

Hypothesis to test: *CrewAI, LangGraph, AutoGen/AG2, OpenAI Agents SDK, Google ADK, Semantic
Kernel, smolagents, Pydantic AI and similar frameworks orchestrate agents by calling model
inference APIs directly (through their own SDKs or LiteLLM/OpenRouter), with tools defined in
process; they do not drive vendor coding-agent CLIs or sessions. specy-road is unusual in using
those CLIs as the worker unit.*

For each framework, state with a dated citation to primary docs:
1. How the model is invoked (direct provider API, gateway, or local).
2. Whether it can natively run a coding-agent CLI (Claude Code, Codex CLI, Cursor agent, Gemini
   CLI, Aider, OpenHands) as a step, and whether anyone does this in practice.
3. Whether it supports MCP, skills, hooks, or subagents, and how that compares with what the
   vendor harness gives for free.

Then check the exceptions that may weaken the hypothesis: the Claude Agent SDK (programmatic access
to the Claude Code runtime), the Codex SDK / `codex exec --json`, Claude Code's own subagent and
Workflow facilities, Cursor's background agents and `agent` CLI, Gemini CLI headless mode,
OpenHands/SWE-agent-style harnesses, and any open-source projects that spawn `claude -p` or
`codex exec` as workers (search GitHub and recent writing from mid-2025 onward). Conclude with a
one-paragraph verdict: is specy-road's niche real, and what are the closest neighbours?

## Part B. Map "Making agents fast" onto specy-road's loop

The seed article argues that inference is often not the dominant cost; its example 60-second task
spends 6 s provisioning, 24 s inference, 18 s tool/MCP calls, 12 s suspend/resume. It recommends:
know whether your workflow is TTFT-bound or tok/s-bound; cut thinking budgets first; profile tool
calls (process spawn storms, shell startup cost, oversized tool output inflating uncached input);
build the tooling the agent wants by watching its workarounds and reading thinking traces; replace
polling with callbacks; prefer tools that parallelise internally over asking the model to
parallelise; mind hardware, sandbox CoW/snapshot IO, microVM resume, RAM, and broken IPv6.

For each of the following specy-road phases, estimate where wall-clock and tokens go, cite any
public measurements of the underlying harness, and propose concrete changes:

1. **Brief and prompt generation.** Is the generated brief/prompt sized for TTFT? Are per-model
   prompting rules reducing thinking budget per role (reviewers and coordinators likely need less
   than executors)? Which harness CLI flags control effort/thinking today (Claude Code, Codex,
   Cursor), and should model profiles record a per-role recommended effort?
2. **Worker launch and resume.** Cost of a cold headless CLI start versus resume; what each vendor
   CLI loads at start (hooks, MCP servers, skills); whether specy-road's wrapper can pre-warm or
   trim that. Compare with the article's provisioning and suspend/resume costs.
3. **The coordinator's `worker sync` loop.** This is polling by design (D3 no daemon). Quantify
   the latency it adds to a leaf's lifecycle, and evaluate alternatives that keep D3: filesystem
   watch, a harness hook on the worker side that writes an event immediately, an on-turn-end
   notification the coordinator's own harness can receive (Claude Code hooks, Cursor hooks), or
   `--wait` style blocking variants of `sync`.
4. **Tool-call overhead inside a leaf.** Executors chain many `specy-road …` and `git` commands.
   Measure or estimate Python CLI start-up cost per invocation, validator cost on large roadmaps,
   and whether a long-running `specy-road serve`-free alternative (a batch subcommand, a single
   JSON status call, cached validation) would cut shell spawns. Also assess `.zshrc`/`.bashrc` load
   per command under each harness.
5. **Tool output size.** Which specy-road commands emit output that lands in the model's context
   (review packets, briefs, `--json` planner output, validate diagnostics)? Which should be
   truncated, paginated, or made queryable instead of dumped?
6. **Parallelism.** `grind-session --plan` already computes waves. Evaluate having specy-road fan
   out a wave itself (multiple `worker delegate` calls, `max_workers`) versus asking the coordinator
   model to do it, per the article's reliability point. Cover worktree isolation, shared-checkout
   presence guards, registry commit contention, and integration-branch merge ordering.
7. **The review gate as suspend/resume.** The human approval step is specy-road's analogue of
   the article's suspend/resume. What state should be checkpointed so the resumed session is cheap
   (fresh-session reviewers are mandatory, so what is the minimal packet)? Is review latency
   dominated by human wait, reviewer cold start, or packet size?
8. **Sandboxes.** specy-road has an agentic-sandbox runbook for isolated VMs. Apply the article's
   hardware, CoW, NVMe, and IPv6 points to that path.

## Part C. Orchestration patterns worth porting (under D1–D3)

Survey the frameworks from Part A plus durable-execution systems (Temporal, Inngest, Restate,
LangGraph checkpointers, Prefect/Dagster where relevant) and Anthropic's and OpenAI's published
multi-agent guidance. For each pattern below, say what the best implementation looks like, whether
specy-road already has an equivalent (name it), what is missing, and the smallest CLI-and-files
design that adds it without an MCP server, daemon, or model API calls:

1. Explicit state machines / graphs with checkpoints and deterministic replay (compare with the
   worker record + event log + `instruction_epoch`).
2. Human-in-the-loop interrupts and resumption (compare with `handoff`/`reclaim` leases and the
   unsupported `interrupt`).
3. Supervisor / hierarchical agents, hand-offs between agents, and routing by capability (compare
   with the roster, `orchestrate plan`, `may_process`, substitutions).
4. Fan-out/fan-in with join semantics, partial-failure handling, retries with backoff, and
   idempotent steps (compare with waves, exit codes, escalation thresholds).
5. Structured outputs and typed contracts between steps (compare with READY/PACKET/REVIEW files,
   JSONL events, `--json` flags).
6. Observability: tracing, spans per tool call, token and cost accounting per leaf, per role, per
   model (what does specy-road record today, what could it parse from each harness's JSON output
   stream or transcript?).
7. Evaluation and regression harnesses for agent behaviour (compare with the dogfood fixture,
   `context-regressions.yaml`, model-profile staleness checks).
8. Memory and context management across leaves (compare with briefs, archived context search, the
   "give the agent the tool it wants" advice).
9. Guardrails and permission policies (compare with touch zones, the review gate, harness
   permission flags recorded in profiles).
10. Budget and rate-limit awareness (usage-limit handling in `grind-session`, service tiers,
    time-of-day load).

Rank the ten by expected value for specy-road's users. Reject patterns that only make sense when
you own the inference loop, and say why.

## Part D. What the vendor harness already gives, and what specy-road must not duplicate

For Claude Code, Codex CLI, Cursor agent, and Gemini CLI: list the native capabilities relevant to
orchestration (subagents, hooks, skills, MCP, headless JSON output, resume, effort flags, usage
reporting, sandboxing). Mark each as *rely on it*, *wrap it*, or *fill the gap* from specy-road's
point of view. Flag any capability that is unstable or recently changed, with dates.

## Part E. Measurement plan

Propose the minimal instrumentation specy-road could add so maintainers can reproduce the seed
article's timeline for one leaf: phase timestamps in the event log, tool-call counts and bytes,
per-invocation CLI start-up time, tokens in/out per role where the harness exposes them. Specify
what to record, where (event log fields vs a separate file), and how it stays vendor-neutral.

## Output format

1. **Verdict on Part A** in one paragraph, then a table: framework | model invocation | can drive
   coding-agent CLIs? | MCP/skills/hooks/subagents | source and date.
2. **Timeline model** for one specy-road leaf, modelled on the article's 60-second example, with
   your best estimates and the assumptions behind them.
3. **Recommendations**, ranked, each with: title; what changes (command, file, or doc); which
   constraint it respects (D1–D3, vendor neutrality, smallest change); impact (high/med/low);
   effort (S/M/L); evidence; risks.
4. **Patterns rejected** and why.
5. **Open questions** that need a measurement or a maintainer decision.
6. **Sources**: primary documentation first, each with the date accessed; separate clearly what
   you verified from what you inferred. Where sources disagree, say so.

Keep the report under roughly 6,000 words. Prefer dated primary sources (vendor docs, changelogs,
repositories) over secondary commentary. Do not invent specy-road commands; when you are unsure
whether something exists, say "verify in repo".
