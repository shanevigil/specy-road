# Orchestration patterns research: roster split and harness layer (2026-11-05)

Read-only research for the maintainer. It answers two questions:

- **(a)** Should the roster schema split into core fields and an extension (harness) namespace?
- **(b)** Should specy-road keep building its own harness layer, or adopt an existing tool or pattern?

The maintainer has ruled that workers and orchestration are core. This report treats that as fixed and asks only how to build them.

Web evidence was gathered on 2026-11-05. Where a claim rests on third-party pages rather than vendor docs, it says so.

---

## 1. The article: Waehner, "Agentic technical debt and where orchestration belongs" (2026-11-03)

Source: https://www.kai-waehner.de/blog/2026/11/03/agentic-technical-debt-and-where-orchestration-belongs-in-ai-agent-architecture/

**Argument.** Agentic technical debt is the cost of shortcuts around agents. The post names prompts, tool wiring, memory, control logic and governance rules, "patched together faster than teams can test, standardize, or audit them". It extends the 2015 "Hidden Technical Debt in ML Systems" paper: *"In AI agents, the model call is the new small box."* The thesis is about placing concerns in the right layer: *"Debt starts when one layer takes over the job of another."*

**Reference architecture.** Four layers, plus a decision gate above them:

| Layer | Job | Examples given |
|---|---|---|
| Model | Reason or decide | Anthropic, OpenAI, Mistral, … |
| Agent harness | One agent's loop: tools, context, memory, sandbox | LangGraph, OpenAI Agents SDK, Google ADK, AWS Strands |
| Durable execution | Persist each step so long runs survive crashes inside one application | Temporal (including running LangGraph graphs) |
| Orchestration control plane | Triggers, sequencing across systems and teams, approvals, deadlines, compensation, audit | Kestra |
| Process-intelligence gate (above) | Decides which processes get an agent and measures the result | |

**Where each concern lives (the useful part):**

- **Model choice:** "decide high, route low". The orchestration step picks the kind of model and the harness routes the call.
- **Tool permissions and identity:** the control plane defines which identity and secrets a step may use, and the harness enforces them per call.
- **Retries:** the harness retries calls with no side effects. Side-effecting steps are retried by durable execution or the control plane, keyed on a business ID.
- **Human approval:** an explicit control-plane step with a timeout, an escalation path and a record. It is never a prompt instruction.
- **Budgets:** the harness caps one run, and the control plane caps per process, team or tenant.
- **Audit:** one trail across systems, not "held in one framework's traces".
- The post explicitly lists, as an anti-pattern, *"Governance inside each vendor's product"*.

**When a control plane is warranted.** *"A single agent in one application, such as a coding assistant … needs only its harness."* A control plane is justified when a process crosses systems or teams, moves money or changes production, needs end-to-end audit, or when *"agents from different vendors work on the same process."*

**Closing claim.** *"Value moves to the layers that hold process state, approvals and the audit record."* The post advises deciding early which layer owns approvals, budgets and audit.

**Caveats.** The article is a vendor-neutral-sounding blog that features Kestra prominently; the author has promoted Kestra and Kafka before. The architecture is an enterprise one (ERP, Kafka triggers). It contains no data on coding-agent orchestration specifically.

**Mapping to specy-road.**

- **The vendor CLIs are the harness layer.** Claude Code, Codex CLI and Cursor `agent` each run one agent's loop, tools, sandbox and session.
- **specy-road is a small control plane for one process (a roadmap leaf's life).** It owns:
  - approvals: the review gate, with distinct families and fresh sessions;
  - audit: review records, the worker event log, the decisions ledger;
  - concurrency and budget: `max_workers`, usage events;
  - the reassignment-and-retry part of compensation: `--rework`, `terminate`.
- **The article justifies it existing.** specy-road meets the "agents from different vendors work on the same process" test by design: an executor from one family is reviewed by others.
- **specy-road also has a thin durable-execution layer.** Its parts are the file-based event log, `reconcile`, and the ops outbox with `--op-id` idempotency. The article's "business ID" rule is exactly what the outbox does.

What the article argues against, in specy-road terms:

1. **Re-implementing harness concerns in the control plane.** Per-call tool enforcement (`tool_call_guard*`, about 1k lines) and model-call retry detection both belong to the harness. specy-road should declare the policy and verify after the run, and enforce only where a harness cannot.
2. **Putting approval rules in prompts.** specy-road already avoids this: the gate is code and READY approves nothing. That is a strength worth stating in the docs.

---

## 2. How existing systems separate "what a step is for" from "how/where it runs"

### 2.1 Kestra (Apache-2.0, JVM server)

- **Separation.** A task has a `type` (what it does, e.g. `io.kestra.plugin.scripts.shell.Commands`) and, for script tasks, a nested `taskRunner:` block with its own `type` (`io.kestra.plugin.core.runner.Process`, `…Docker`, cloud batch runners). Each runner is a plugin with its own schema. Task properties (`commands`, `inputFiles`, `outputFiles`, `namespaceFiles`, `workerSelector`) stay on the task. Runner properties stay inside `taskRunner`. *"Script tasks default to the Docker task runner if no `taskRunner` is specified."* The Process runner *"has no additional configuration properties — only the `type` is required."* Sources: https://kestra.io/docs/task-runners, https://kestra.io/docs/task-runners/types/process-task-runner
- **AI agents.** `io.kestra.plugin.ai.agent.AIAgent` takes a nested `provider:` block with its own `type` (e.g. `io.kestra.plugin.ai.provider.GoogleGemini`), `modelName`, and `apiKey: "{{ secret('…') }}"`. `memory:` and each tool are likewise typed sub-blocks. Credentials are always secret references, never literals. Outputs include `textOutput`, `jsonOutput` and `thinking`. I could not confirm a documented token-usage output from the page I read; a `maxCumulativeTokens` option implies the provider reports usage. Source: https://kestra.io/plugins/plugin-ai/agent/io.kestra.plugin.ai.agent.aiagent
- **The pattern is a typed polymorphic sub-block, discriminated by `type`, with the schema chosen by the type.** Core flow keys (`id`, `namespace`, `tasks`, `inputs`, `triggers`) are fixed. All plugin-specific shape lives under typed blocks.
- **Coding agents.** I found no Kestra task that drives Claude Code, Codex or Cursor CLIs. Kestra's coding-agent story runs the other way: an MCP server, Agent Skills and `kestractl` so coding agents can author flows (https://kestra.io/docs/claude-code-quickstart). In Kestra you would drive a CLI with a generic shell `Commands` task.
- **Versioning and migration.** Kestra 2.0 removed the `pluginDefaults` keyword "in all editions and at all scopes". Flows that still contain it fail to parse after upgrade. Enterprise users get "Policies" and an automatic migration; open-source users must inline the values. The same major release renamed ForEach to Loop and trigger `conditions` to `when`. The suggested tool is `kestra-migrate --check`. Sources: https://kestra.io/docs/workflow-components/plugin-defaults, https://kestra.io/docs/migration-guide/v2.0.0
  - **Lesson for specy-road:** a defaults or overlay layer (like `orchestration.local.yaml`) is the part most likely to hurt in a migration. Kestra paid for it with a hard break.
- **As a dependency: no.** It needs a JVM server plus a database (H2 or Postgres), it is a daemon, and it does not know these CLIs. At most it is an *upstream* caller of `specy-road` commands in an enterprise that already runs Kestra.

### 2.2 GitHub Actions (hosted service; `act` runs it locally, third-party)

- **Separation:**
  - `jobs.<id>.runs-on`: *"define the type of machine to run the job on"* (where).
  - `steps[*].uses`: *"Selects an action to run as part of a step in your job"* (what).
  - `with`: *"A `map` of the input parameters defined by the action."*
  - The action's own `action.yml` declares its inputs. Each plugin owns its own input schema, and the workflow schema only says "a map".
  - Source: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- **Versioning.** Actions are pinned by ref (`@v4`, or a SHA for supply-chain safety). The workflow syntax itself has no version field and changes additively.
- **Usage and cost.** Billed minutes per runner type, reported by the service. Not relevant locally.
- **Fit.** Pattern only. The useful idea is that the core schema treats plugin parameters as an opaque map validated by the plugin's own declaration, so the core never grows a key per vendor.

### 2.3 Temporal (MIT; needs a server, with a single-binary dev server available)

- **Separation.** Workflow code (deterministic orchestration) versus Activities (side effects, retried with policies). Task queues decide which worker process runs an activity.
- **Agents.** The OpenAI Agents SDK integration runs each model call as an Activity, so it *"retr[ies] durably and [is] not repeated during Workflow replay."* Non-model I/O becomes Activities exposed as tools. MCP servers are outside the durability guarantee. The Python package moved from `temporalio.contrib.openai_agents` to `temporalio.openai_agents` at 1.0. Sources: https://docs.temporal.io/develop/python/integrations/openai-agents, https://pypi.org/project/temporalio-openai-agents/
- **Versioning.** Workflow code versioning (patching and worker versioning) is a known source of complexity.
- **Fit: no.** It needs a long-running server (against the "no daemon" principle, at least for the CLI path). It is a heavy SDK (gRPC, protobuf). It solves crash-resume of *model calls*, but specy-road's long-running unit is a vendor CLI process that has its own session store and resume. specy-road's file event log plus reconcile is enough for the scale involved (≤ 20 workers on one machine).

### 2.4 Dagger (Apache-2.0)

- **Separation.** Functions run in containers on the Dagger engine. Where they run is always "a container on the engine".
- **Fit: no** for driving subscription CLIs. It needs a container engine, and container isolation fights with CLIs that keep OAuth in the host keychain or `~/.claude`. Included for completeness. I did not research its LLM features in depth; the evidence here is thin.

### 2.5 Agent-loop SDKs: Claude Agent SDK, OpenAI Agents SDK, LangGraph

- **Claude Agent SDK** (Python and TypeScript):
  - **What it is.** *"A library that runs the Claude Code binary."* It covers built-in tools, permissions, sessions (resume and fork via `ClaudeAgentOptions(resume=…, fork_session=True)`), hooks, subagents and MCP. The result message carries `session_id`, `usage` and `total_cost_usd`. Cost is documented as a client-side estimate.
  - **Licence.** The docs say use is *"governed by Anthropic's Commercial Terms of Service"*, except components with their own LICENSE. It is not a plain OSI licence statement; check the repo LICENSE before depending on it.
  - **Auth (important).** *"Unless previously approved, Anthropic does not allow third party developers to offer claude.ai login or rate limits for their products, including agents built on the Claude Agent SDK. Use the API key authentication methods…"*
  - Sources: https://code.claude.com/docs/en/agent-sdk/overview, https://code.claude.com/docs/en/agent-sdk/sessions, https://code.claude.com/docs/en/agent-sdk/cost-tracking
- **Claude Code headless** (`claude -p`, what specy-road drives today): https://code.claude.com/docs/en/headless
  - Documented `--output-format stream-json`, with *"The last line of the stream is a `result` message with the final response text, cost, and session metadata"*.
  - `--resume <id>`; `system/api_retry` events; `permission_denied` system messages and `permission_denials` on the result.
  - A `capabilities` array on `system/init` *"to feature-detect instead of comparing version strings"*.
  - `--max-budget-usd` (a per-run harness budget cap, as the article recommends) and `--permission-prompts none` for unattended runs.
  - **Risk flag:** *"`--bare` is the recommended mode for scripted and SDK calls, and will become the default for `-p` in a future release"*, and *"bare mode doesn't use your subscription login"*. specy-road's `billing_route: claude_subscription` workers depend on `-p` reading OAuth. When that default flips, subscription-billed executors launched without an explicit opt-out may fail authentication or silently need an API key. Track this.
- **OpenAI Agents SDK, LangGraph, Google ADK** (MIT/Apache): these are agent loops that call *model APIs* directly. Adopting them would replace the vendor CLIs and their subscription billing, which contradicts specy-road's deliberate choice. They are the wrong layer.

### 2.6 Coding-agent orchestrators and protocols

- **Agent Client Protocol (ACP)**: a JSON-RPC-over-stdio standard between a client and a coding agent.
  - The client sends `session/prompt`, the agent streams `session/update`, and the agent may request file, terminal and permission actions. The turn ends with a stop reason.
  - The official list includes Codex CLI (through an adapter from the ACP project), "Claude Agent" (through Zed's adapter, built on the Agent SDK), Cursor, Gemini CLI, Goose, OpenHands, Factory Droid, GitHub Copilot and many more (https://agentclientprotocol.com/overview/agents).
  - **Cursor ships it natively** as `agent acp`: sessions via `session/new` and `session/load`, permission requests the client must answer, and no stability label. The page does not say whether token usage or cost is reported (https://cursor.com/docs/cli/acp).
  - **Usage is not part of core ACP.** Libraries add it as an extension event, e.g. ExMCP's `usage` extension (https://hexdocs.pm/ex_mcp/acp_guide.html).
  - A community Cursor adapter notes that native ACP "does not expose `session/list`, `session/resume`, or `session/set_model`", so it falls back to stream-json for turns (https://github.com/raphaelluethy/cursor-acp; third-party).
  - **This is the closest thing to a commodity "drive any coding CLI" layer, but it is not yet complete for specy-road's needs:** no standard usage, uneven resume and model selection, and Claude/Codex need npm adapter packages.
- **acpx** (openclaw/acpx, MIT per its listings, labelled alpha): a headless ACP client with built-in adapters for codex, claude, gemini, cursor and others. It auto-downloads adapters via `npx` on first use (https://awesome.ecosyste.ms/projects/github.com%2Fjanitrai%2Facpx). Runtime `npx` downloads conflict directly with specy-road's supply-chain policy.
- **Codex app-server**: `codex app-server --stdio` speaks JSON-RPC. A `turn/completed` notification reportedly carries token usage, and threads can be resumed. Python wrappers (`openai-codex`, `codex-app-server-sdk`) were described as experimental with unstable APIs (https://pypi.org/project/codex-app-server-sdk/, https://codex.danielvaughan.com/2026/06/03/codex-app-server-stdio-subprocess-embedding-custom-clients-json-rpc-protocol/; mostly third-party). Verify the payload with `codex app-server generate-json-schema`.
- **OpenHands software-agent-sdk** (MIT per its paper and org page; one review says "Other"): a full agent stack plus an agent server (REST/WebSocket, Docker or Kubernetes). Third-party sources say it can run external agents over ACP. Heavy; it is aimed at its own agent loop over LiteLLM. Sources: https://github.com/OpenHands/software-agent-sdk, https://arxiv.org/html/2511.03690v2
- **Local multi-CLI worktree runners.** These are the nearest products to specy-road's worker layer, but none has a spec-and-review gate:
  - **Claude Squad:** Go TUI, tmux plus a worktree per agent, AGPL-3.0.
  - **Vibe Kanban:** Rust/Node; executor profiles keyed `CLAUDE_CODE` / `CODEX` / `CURSOR_AGENT`, with named variants (`DEFAULT`, `PLAN`, `HIGH`…) carrying flags, and a worktree per task.
  - **Orchestra:** Electron, Apache-2.0.
  - **Conductor:** macOS app; reportedly unmaintained since Aug 2026, per a single source.
  - **GitKraken Kepler:** commercial; per-task worktree plus agent sessions.
  - Sources: https://crystl.dev/blog/best-ai-agent-orchestration-tools/, https://deepwiki.com/BloopAI/vibe-kanban/11-glossary, https://isomoes.github.io/blog/tools/vibe-kanban-intro. All of these are third-party; licences and maintenance should be checked in the repos.
  - **Takeaway:** Vibe Kanban's "executor kind + named variant of flags" split is the same shape as specy-road's `harness` + `channels.cli`, with the variant named and reusable instead of an inline command per roster entry.
- **Usage reporting standard: OpenTelemetry GenAI semantic conventions** (status: Development).
  - Fields: `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` and `gen_ai.usage.cache_read.input_tokens`. Agent spans use operation `invoke_agent`, with `gen_ai.agent.*`.
  - VS Code's Copilot reports session totals on the agent span and per-call totals on LLM spans. That is the same session-versus-turn ambiguity specy-road's `worker_usage_delta.py` handles.
  - Sources: https://code.visualstudio.com/docs/agents/guides/monitoring-agents, https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained. The spec's location and version are in flux; secondary sources disagree.

### 2.7 Summary table

| System | What versus where | Config versioning | Usage/cost | Realistic dependency for specy-road? |
|---|---|---|---|---|
| Kestra | Task `type` + nested typed `taskRunner` / `provider` | Major-version breaks with migration tool (2.0 removed `pluginDefaults`) | Provider-dependent; not confirmed | No: JVM server, DB, daemon, no CLI drivers |
| GitHub Actions | `runs-on` / `uses` + opaque `with` validated by the action | Ref pinning; additive syntax | Service billing | Pattern only |
| Temporal | Workflow versus Activity + task queues | Workflow patching | None built in | No: server, heavy, wrong unit (model call, not CLI session) |
| Dagger | Function versus engine container | Module versions | N/A | No: container engine, OAuth keychain friction |
| Claude Agent SDK | Options object; one harness | SDK semver | `usage`, `total_cost_usd` (estimate) | Only for the Claude slice, and the auth policy pushes to API keys |
| OpenAI Agents SDK / LangGraph | Agent definition versus model provider | Semver | Per-call usage | No: wrong layer (calls APIs, not CLIs) |
| ACP (+ acpx) | Protocol; agent behind an adapter | Protocol versions | Not in core; extensions | Not yet: usage missing, adapters via npm, alpha client |
| Vibe Kanban / Claude Squad | Executor kind + variant | App-managed JSON | Partial | Pattern only (Rust/Go apps; AGPL for Squad) |
| OTel GenAI semconv | N/A | Spec versions | Standard attribute names | Names only, no dependency |

---

## 3. specy-road today (grounding)

- **Schema.** `roadmap/orchestration.yaml` is `version: 1` (`const`), with a flat `rosterEntry` (`additionalProperties: false`) of 19 keys: `id, family, roles, available, paused_until, unavailable_until, class, may_process, public_key, profile, harness, harness_bin, harness_model, routing, pinned, billing_route, channels, preflight, subagent_family_lock`. The policy block has 23 keys. Source: `specy_road/templates/project/schemas/orchestration.schema.json`.
- **The toolkit's own roster** (`sr/roadmap/orchestration.yaml`) has 16 entries.
  - All but the `human` entry carry harness fields. 11 of them carry a `channels.cli` shell template pointing at `sr/tools/*.sh` wrappers, so in practice the roster is mostly harness configuration.
  - Comments document vendor quirks inline: the Codex sandbox, Cursor Auto routing, and wrappers kept "until M8.3 lands".
- **The gate reads more than id/family/roles/available.** This is the key finding for (a):
  - `may_process`: the node-sensitivity rule in `review_gate.py`.
  - `public_key`: signed reviews (`review_gate.py`, `review_gate_ready.py`).
  - `routing_problem()` in `orchestration_config.py`, called from `review_gate.py`, decides whether an approval counts toward `reviewers_distinct_families`. It reads `routing`, `pinned`, `harness`, `channels.cli` (parsing its `--model`), `harness_model`, and the pinned profile's `api_id`.
  - So the family attestation, "is the family behind this approval actually known?", crosses the proposed core/extension line.
- **Worker layer size.**
  - `worker_*.py` totals about 4.9k lines in 30 modules.
  - Harness, guard, delegate and plan modules add about 3.1k more: `harness_*`, `tool_call_guard*`, `orchestration_*guard*`, `review_delegate*`, `orchestrate_*`.
  - The slimming report counts worker, harness and orchestration plumbing at 12.2k source lines.
- **Design decisions already documented** (`docs/orchestration-workers.md`):
  - The surface is the CLI; there is no MCP server.
  - Workers run on each vendor's documented one-shot CLI with resume.
  - No daemon: a detached wrapper per worker writes files.
  - The event log is authoritative. `authority` labels separate `system` facts from `worker_suggestion` (harness stdout).
- **Usage.** There is already a normalized per-turn `usage` event with `null` for anything not reported. It handles per-vendor quirks: Claude's running `total_cost_usd`, Codex resume reporting thread totals, and Cursor's camelCase. Cost is estimated from profile `cost_usd_per_mtok` when the harness reports none.
- **The slimming plan already proposes the split.** RECOMMENDATION.md M16.3 says: "Roster schema split into core fields and an extension namespace. `upgrade` migrates and `validate` accepts both forms for one release." M16.4 says: an `specy_road/orchestration/` subpackage with one public interface for the gate and the 0.3.2 GUI.

---

## 4. Findings

### 4.1 The roster split (question a)

**Is there a prevailing pattern?** Yes, and it is consistent across Kestra, GitHub Actions and Vibe Kanban. The core schema names *what the thing is for and who it is*. A *nested, typed* block names *how and where it runs*, and its schema is selected by a discriminator (`taskRunner.type`, `uses:` + the action's own `action.yml`, executor kind + variant). Kestra goes further: every vendor-specific credential or provider is a typed sub-block, and secrets are references.

None of these systems uses a flat "extension namespace" bag of unrelated keys. They use typed sub-objects. "Extension namespace" in the GitHub sense (an opaque `with:` map) works only because each action validates its own inputs.

**Pros of splitting (evidence-based):**

1. **Churn isolation.** Vendor CLIs change fast:
   - Claude Code's `-p` defaults are about to change (`--bare`);
   - Codex sandbox flags and app-server are still experimental;
   - Cursor's binary was renamed and ACP was added.

   In specy-road's own roster, nearly all comments and churn are in the harness fields. A nested `run:` block lets the harness schema evolve (even version separately) without touching what the gate reads.
2. **Per-harness validation.** A `oneOf` on `run.harness` can reject, for example, `harness_bin` patterns or `cli_resume` that make no sense for a given harness. The flat `additionalProperties: false` cannot express that.
3. **GUI and adopters.** The 0.3.2 GUI can show the core columns (id, family, roles, availability) for everyone and expand `run:` only when present. A project with only human or manual reviewers writes three lines per entry.
4. **The article's layering.** Identity, eligibility and permissions are declared by the control plane (core). How a run is launched is harness territory (extension).

**Cons and risks:**

1. **The line is not where the question draws it.** The gate needs `may_process`, `public_key`, and a *family attestation* that today is derived from `routing` / `pinned` / `harness` / `channels.cli` / `harness_model` / profile. A naive split would make the gate read into the extension block, defeating the purpose. Fix it in one of two ways:
   - move the attestation into core as a declared field (for example `family_pinned: true`, today's `pinned`), with the harness adapter answering "do I route dynamically?" through the orchestration interface; or
   - keep the derivation, but behind one function the gate calls, which is already almost true (`routing_problem`).
2. **Migration cost.** Every adopter roster changes shape. specy-road's plan already budgets one release of dual-read plus `upgrade`. Kestra's 2.0 shows the failure mode of skipping that: hard parse failures after upgrade.
3. **Overlay complexity.** `orchestration.local.yaml` patches availability (core) and adds whole entries (`roster_add`). After a split, the overlay rules must say which block they may touch. Kestra's experience suggests keeping overlays to core availability only.
4. **Verbosity.** One extra nesting level per entry. That is minor.

**Recommended shape** (a sketch, not a spec):

```yaml
version: 2
roster:
  - id: grok-4.7-low
    family: xai
    roles: [reviewer]
    may_process: [public]          # core: eligibility
    family_pinned: true            # core: gate attestation (today: pinned)
    available: true                # core (overlay-able)
    run:                           # extension: absent for humans / manual reviewers
      harness: cursor              # discriminator → per-harness schema
      model: grok-4.7-low          # today: harness_model
      profile: model-profiles/spacexai-grok/grok-4.7.md
      billing_route: cursor_subscription
      cli: '… cursor-review.sh grok-4.7-low {prompt}'
      # cli_resume, harness_bin, preflight, routing, subagent_family_lock
```

Optionally, as in Vibe Kanban, allow named `run_profiles:` at top level (for example `cursor-review-low`) that entries reference with `run: {use: cursor-review-low}`. This removes the 11-fold repetition of `${SPECY_ROAD_TOOLS:-…}` templates in the toolkit's roster. It adds a concept, though, so make it optional and only if the repetition proves painful for adopters, not just for the toolkit.

`public_key` stays in core (it is identity). `profile` sits on the boundary: it feeds both cost estimation and `api_id` routing. I place it in `run:` because the gate needs it only through the attestation function.

**Verdict on (a):** split, but as **core identity and eligibility, plus a typed `run:` block**, not as id/family/roles/available versus everything else. Do it in M16.3 together with M16.4's interface, so that `routing_problem` becomes an interface call rather than a schema dependency. Evidence for the pattern is strong (three independent systems). Evidence that it pays off for *adopters* is thin: the toolkit is still the main roster user.

### 4.2 Commodity versus specy-road-specific (question b)

| Slice | Commodity? | Why |
|---|---|---|
| Launch and resume command lines per CLI | Mostly commodity | Every multi-CLI runner rebuilds it. ACP aims to standardize it. Vendor docs define it. |
| Stream event parsing | Commodity in principle, not in practice | Each CLI's stream is vendor-documented, and ACP would unify it, but usage and limit signals are not standardized. |
| Usage and cost normalization | Partly commodity | The OTel GenAI names exist. Session-versus-turn deltas, subscription "cost is an estimate", and `paused_by_limit` are specific to driving subscription CLIs. |
| Process supervision (detached wrapper, pgid, liveness, orphans) | Commodity in general, but there is no lightweight Python library that matches the "no daemon, files only" rule | |
| Concurrency (`max_workers`, slot leases across checkouts) | Specific | Tied to registry claims, worktrees and multiple checkouts of one repo. |
| Human lease (handoff/reclaim, prompt-submit witness) | Specific | No surveyed tool has a single-writer lease between a broker and a human on the vendor's native session. |
| Tool and sandbox guards | Mostly commodity, at the harness | Each harness has native permission modes and sandboxes. specy-road's specific part is the *policy* (reviewers write nothing but their review file) and the post-run verification. |
| Post-run check (READY on branch at HEAD, touch zones, git state) | Specific | Tied to the spec and review contract. |
| Scheduling and plan (eligibility, ranking, spread, families) | Specific | Tied to roadmap graph, sensitivity and review-family rules. |
| Review gate, records, packets | Specific; the product's core value | The article's "approvals and audit" layer. |
| Outbox, idempotent ops, reconcile | Durable-execution pattern; Temporal is overkill | Small and file-based. |

---

## 5. Buy vs build

### 5.1 Candidates

The pivotal criterion: specy-road deliberately drives **subscription-billed vendor CLIs** (Claude Code, Cursor `agent`, Codex CLI). Anything that calls model APIs directly replaces the harness and its billing, so it is out of scope however good it is.

| Candidate | Licence | Maturity and maintenance | Drives these CLIs? | Python fit | Dependency weight | Offline/local | Slice it could replace |
|---|---|---|---|---|---|---|---|
| **Claude Agent SDK** (`claude-agent-sdk`) | Anthropic Commercial Terms per docs (check the repo LICENSE) | Official, active, frequent releases | Claude Code only (runs its binary) | Native Python, async | Moderate (pulls MCP and async deps; check the lock) | Yes, local process | Claude launch/resume/parse/usage (~170 + part of 400 lines) |
| **Codex app-server + Python wrappers** (`openai-codex`, `codex-app-server-sdk`) | Codex is Apache-2.0; wrappers vary | Protocol official; Python wrappers "experimental, unstable APIs" (third-party reports) | Codex only | Python, JSON-RPC over stdio | Light (a wrapper could be written in-house) | Yes | Codex launch/resume/parse/usage (~130 lines) |
| **Cursor `agent acp`** | Proprietary CLI; protocol open | Official, no stability label; usage not documented | Cursor only | Write your own JSON-RPC client | None (stdlib) | Yes | Cursor parse, partly (stream-json parsing; usage unknown) |
| **ACP (protocol) + acpx** | ACP open; acpx MIT (per listings) | acpx alpha; ACP agent list broad but adapter-based for Claude and Codex | All three, via adapters (Claude via Zed's Agent-SDK adapter, Codex via ACP project's adapter, Cursor native) | acpx is Node; ACP clients in several languages | Heavy for specy-road: Node runtime plus `npx` auto-downloads | Downloads on first use | All adapters and parsers (~1.3k lines), minus usage |
| **OpenHands software-agent-sdk / agent-server** | MIT (one source says "Other") | Active, funded, research-backed | Own agent; external agents over ACP (third-party claims) | Python | Heavy (server, Docker, LiteLLM) | Local Docker possible | Supervision and sandbox, but swaps the architecture |
| **LiteLLM** | MIT | Very active, but **two PyPI compromises in 2026** (1.82.7/1.82.8 in March; 1.107.0 in October per Cloudsmith) | No, calls model APIs | Python | Heavy | N/A | Cost normalization (price table) only |
| **OpenAI Agents SDK / LangGraph / Google ADK** | MIT / MIT / Apache-2.0 | Mature | No, own loop over APIs | Python | Moderate | Yes | None without abandoning the subscription-CLI model |
| **Temporal (+ OpenAI Agents integration)** | MIT | Mature | No (durable model calls, not CLI sessions) | Python SDK | Heavy (server, gRPC) | Dev server binary | Outbox, reconcile, crash-resume (~600 lines) at large cost |
| **Kestra** | Apache-2.0 | Mature; breaking 2.0 | No (generic shell task only) | YAML; JVM | Very heavy (JVM, DB) | Self-host | Upstream scheduling in enterprises; not inside specy-road |
| **Dagger** | Apache-2.0 | Mature | No | Python SDK | Container engine | Local engine | Sandbox isolation (conflicts with OAuth in keychain) |
| **Claude Squad** | AGPL-3.0 | Active (third-party) | Yes (tmux sessions) | Go | N/A | Yes | Pattern only; AGPL rules out embedding |
| **Vibe Kanban** | Apache-2.0 (verify) | Active (third-party) | Yes: Claude Code, Codex, Cursor and others, as executors with variants | Rust/Node app | App, not a library | Yes | Pattern for executor profiles and variants |
| **Aider / Goose / Plandex** | Apache-2.0 / Apache-2.0 (Linux Foundation AAIF) / MIT | Aider active; Goose active; Plandex cloud shut down, self-host only | No, each is its own agent | Aider Python | Moderate to heavy | Yes | None; they are alternative harnesses that could be *rostered*, not dependencies |

Sources for this table: §2 above, plus https://futuresearch.ai/blog/litellm-pypi-supply-chain-attack/ and https://cloudsmith.com/blog/litellm-1-107-0-compromised-on-pypi.md (LiteLLM incidents; the October one rests on a single source), https://dev.to/jovan_chan_9500711396d4e6/plandex-v2-review-2026-cloud-shut-down-self-hosted-survives-is-the-terminal-agent-still-worth-11pp (Plandex, third-party), and https://doolpa.com/article/goose-ai-agent (Goose licence and governance, third-party).

**No surveyed package covers specy-road's harness layer end to end** (launch + resume + parse + usage + leases + guards across all three CLIs, in Python, without a daemon or Node). The closest is ACP via acpx, which is alpha, Node-based and auto-downloads adapters, and which lacks standard usage reporting.

### 5.2 Per-slice decision

Scores are 1–5: **fit** (does a candidate do what specy-road needs), **risk** (higher means riskier to buy), and **build cost** to keep in-house (higher means more costly).

| Slice | Best buy candidate | Fit | Buy risk | Keep-build cost | Decision | Migration cost if acting |
|---|---|---|---|---|---|---|
| Launch/resume adapters | Vendor CLIs' own documented one-shot modes (already used); ACP later | 3 | 4 (ACP adapters via npm; Claude adapter sits on the Agent SDK and its auth policy) | 2 | **Build (keep), and design for ACP.** Keep one `Adapter` interface; add an `acp` adapter as a fourth harness when Cursor's ACP reports usage, starting with Cursor (native, no npm). Don't route Claude or Codex through npm adapters. | ACP adapter ~300–500 lines, stdlib JSON-RPC; existing adapters stay |
| Event parsing | Claude Agent SDK message types (Claude only); Codex app-server schema | 3 | 3 | 3 | **Build (keep), but consolidate.** One table-driven parser per harness against recorded fixtures (`tests/fixtures/worker_usage/turn_end_lines.json` already exists). Feature-detect via Claude's `system/init.capabilities`. | Folding into the M16.4 subpackage; line-negative |
| Usage/cost | LiteLLM price map; OTel GenAI semconv | 2 (LiteLLM) / 4 (OTel names) | 5 (LiteLLM supply chain) / 1 (names only) | 2 | **Build, adopt OTel names as a pattern.** Rename or alias `usage` detail fields to `gen_ai.usage.*`-compatible names in the GUI API; keep profile `cost_usd_per_mtok`. Do not depend on LiteLLM; do not vendor its price JSON (a data supply chain with no review). Expose Claude's `--max-budget-usd` as an optional per-run cap. | Small; field aliases in the event-to-GUI interface |
| Concurrency/leases | None found (Temporal would need a server) | 1 | 5 | 2 | **Build (keep).** This is the specy-road-specific state the 0.3.2 GUI should render. Collapse slot counting into the single state model (M16.4). | Already planned |
| Guards (tool/sandbox) | Harness-native permissions: Claude `--permission-mode` / `--disallowedTools` / `--permission-prompts none`; Codex `sandbox_mode`; Cursor `--sandbox` | 4 | 2 | 4 (`tool_call_guard*` plus role guards ~1k lines) | **Hybrid.** Declare policy in specy-road ("reviewer may write only `work/reviews/<ID>/REVIEW-<model>.md`"), compile it to each harness's native flags, and keep the post-run git check as the verifier. Retire in-process tool-call interception where a native flag covers it. This follows the article's layering: the control plane declares and the harness enforces. | Medium; needs per-harness evidence (M8.3 history shows the Codex sandbox is tricky) |
| Scheduling/plan | Kestra or Temporal as schedulers | 1 | 5 | 2 | **Build (keep).** Eligibility, sensitivity, families and fresh sessions are the product. | None |
| Durable state, outbox, reconcile | Temporal | 2 | 5 | 2 | **Build (keep).** File-based and no daemon; the outbox's `--op-id` is exactly the article's idempotency key. | None |

### 5.3 Overall buy/build recommendation

**Option A: keep building, adopt patterns only (recommended).**

- Do the typed `run:` split (4.1).
- Consolidate adapters behind one interface in `specy_road/orchestration/` (M16.4).
- Use OTel GenAI field names for usage.
- Move guards toward harness-native enforcement plus post-run verification.
- Add no new runtime dependency.
- **Cost:** mostly already budgeted in M16.3 and M16.4. The guard rework is new, medium-sized work.
- **Risk:** you keep owning vendor-CLI churn, about one adapter fix per vendor release that changes flags.

**Option B: A plus an ACP adapter (watch, then adopt for Cursor first).**

- **Trigger:** Cursor's `agent acp` documents usage and resume and model selection, or ACP adds standard usage.
- **Gain:** one parser for Cursor, and a path to any ACP-speaking agent (Goose, Gemini CLI, OpenHands) as a roster harness without new adapter code.
- **Cost:** about 300–500 lines with stdlib only. No Node, if limited to natively ACP-speaking CLIs.
- **Risk:** the protocol is still moving; the permission-request round-trip must be answered or the tool blocks.

**Option C: adopt the Claude Agent SDK for the Claude slice (not recommended now).**

- **Gain:** typed messages, `interrupt()`, and hooks as callbacks.
- **Costs:**
  - a heavier dependency under a Commercial-Terms licence;
  - the documented policy steers SDK-built agents to API-key auth, against `billing_route: claude_subscription`;
  - it covers one vendor of three.
- Revisit only if specy-road moves Claude workers to API billing.

**Rejected:**

- **Temporal, Kestra, Dagger:** server or engine weight, against the no-daemon and local-first design, and none drive these CLIs.
- **LiteLLM:** supply-chain record in 2026, and it is the wrong layer.
- **OpenAI Agents SDK, LangGraph, ADK, OpenHands:** they replace the harness CLIs and their billing.
- **acpx:** alpha, Node, and runtime `npx` downloads.

### 5.4 Risks to watch regardless of option

1. **Claude Code `-p` moving to `--bare` by default.** Bare mode does not read OAuth, so subscription-billed `claude -p` workers will break or flip to API billing when the default changes. Add a preflight that detects bare-by-default (through `system/init` capabilities or the CLI version) and passes the opt-out explicitly, and a test fixture for it. Source: https://code.claude.com/docs/en/headless
2. **Auth policy.** The Agent SDK overview says third-party products must not offer claude.ai login unless approved, and the headless page describes `claude -p` as "using the Agent SDK via the CLI". specy-road launches the *user's own* installed CLI under the user's own login, which is arguably different from a product "offering" login. It is still a policy question the maintainer should get a clear answer on before 0.3.2 markets orchestration as core. I am not able to resolve it from the docs.
3. **Vendor churn concentration.** Any buy option still leaves specy-road exposed through the adapter it buys. The typed `run:` block plus recorded-fixture tests is the cheapest mitigation.

---

## 6. Evidence quality

- **Strong** (vendor docs read directly): Kestra task runners, AIAgent shape and the `pluginDefaults` removal; GitHub Actions syntax; Claude Code headless and Agent SDK overview (auth note, `--bare` plan, cost as estimate); Cursor ACP page; Temporal integration docs.
- **Medium** (multiple secondary sources agree): the ACP agent list and adapter maintainers, OpenHands licence and ACP support, LiteLLM's March 2026 compromise, and the OTel GenAI usage attribute names.
- **Weak** (single secondary source or unverified): LiteLLM's October 2026 compromise; licences and maintenance of Vibe Kanban, Conductor, Claude Squad and Orchestra; Codex app-server usage payload fields; Plandex status; Kestra AIAgent token-usage outputs; the Claude Agent SDK's exact dependency weight.
- **Not researched in depth:** Factory, Sweep, Codex cloud and Cursor background agents. They are hosted services and not plausible dependencies for a local CLI toolkit.
