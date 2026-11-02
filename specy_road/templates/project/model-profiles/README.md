# Model profiles: choosing models for orchestration roles

This page is the canonical guide to filling the roster in
`roadmap/orchestration.yaml` (toolkit docs: `docs/orchestration.md` for the
roles and review gate, `docs/orchestration-models.md` for `models`, `prompt`,
and `orchestrate plan`). It covers
which model to use as coordinator, executor, or reviewer, which pairs make
independent reviewers, which models are cheap first passes, and where the
research disagrees. Each model has a profile under this directory with its
limits, prices, headless invocation, failure modes, and prompting rules.

> **Not human-checked.** Prices, CLI syntax, benchmark numbers, and every other
> fact here come from research that language models ran. No human has checked
> the sources. Confirm a price, limit, or command with the vendor before you
> depend on it.

`specy-road models list|show|stale` read these files, `specy-road prompt` folds a
profile's rules into a role prompt, and `prompt --channel cli` and a `generic`
worker run its `access.cli` (`<prompt>` or `{prompt}` is the placeholder; a roster
`channels.cli` overrides it). A worker on `claude-code`, `codex` or `cursor` uses
that harness's default command unless the roster sets `channels.cli`.

Front matter fields under `access` that tools read:

| Field | Values | Read by |
|---|---|---|
| `cli` | headless command with `{prompt}` or `<prompt>`, or `none` | `prompt --channel cli`, `generic` workers |
| `effort_map` | mapping of effort name → the model's own level | `prompt` |
| `launch_mode` | `full` (default when absent) or `bare` | `claude-code` workers: `bare` adds `--bare`; any other value is a profile error |
| `effort_by_role` | mapping of `coordinator` / `executor` / `reviewer` → an `effort_map` key with a known level | `prompt --channel cli` and workers: the harness's effort flag for the role (`{effort}` in a `cli`); an unknown role or key is a profile error |
| `subagents` | free text whose first word is `yes`, `unknown` or `no`, then the evidence | `prompt --role executor`: a value starting with `yes` (or a bare `yes`) adds the paragraph telling the executor to use the harness's subagents for verification and search inside the leaf; any other value leaves it out |

`launch_mode: bare` drops the harness's hooks, skills, plugins, MCP servers and
CLAUDE.md, and needs `ANTHROPIC_API_KEY` (bare mode never reads the subscription
login). The shipped Claude profiles set `full`; see `docs/orchestration-models.md`.
They also set `effort_by_role`: executor and reviewer at the model's documented
default effort, coordinator one level below. Lower the reviewer only after
measuring that review verdicts hold.

## Where this comes from

Two runs of the deep-research prompt in the
[orchestration proposal](../design-notes/model-aware-orchestration-proposal.md) §7.2,
weighted equally:

| Run | Researched | Schema | Roster | Raw output |
|---|---|---|---|---|
| ChatGPT (Deep Research) | 2026-10-20 | 1 | GPT Sol, Claude Opus, Gemini, Grok, DeepSeek | [proposal §7.4](../design-notes/model-aware-orchestration-proposal.md) |
| Claude (Research) | 2026-10-26 | 2 | Claude Opus and Fable, GPT Sol, Gemini, Grok, Meta Muse, Cursor Composer | [model-research-2026-10-26-claude.md](../design-notes/model-research-2026-10-26-claude.md) |

How the profiles were merged:

- One schema-2 profile per model. `researcher` is `merged` where both runs
  covered the model, otherwise the run that did.
- Front matter keeps one value per field so tools can read it. Where a run had
  `unknown`, the other run's value fills it. Where the runs conflict, the value
  with the stronger primary source wins; when the sources are equally strong, the
  more conservative value wins (lower score, smaller limit). A role score takes
  the lower run's score unless the other run had clearly stronger evidence, and
  its reason shows both, e.g. `(claude 4, chatgpt 5)`.
- Body sections are the union of both runs.
- Each profile also carries a `## Code and test tendencies` section — measured or
  vendor-documented habits in code volume, defensive code and tests, dated
  2026-10-27 from two lean-code research reports and, like everything else here,
  not human-verified — and one prompting rule that counters them.
- Every conflict is listed under the profile's **Open questions** as
  `Watch out — reports differ:` with both values. They are also collected in
  [Watch out for](#watch-out-for-conflicting-reports) below.
- Every source carries `(claude run)`, `(chatgpt run)`, or `(both runs)`.
- `researched` is the older date, 2026-10-20, for merged profiles.

## Roster

Prices are list USD per million tokens. Role scores are 1 (poor) to 5 (strong),
in coordinator / executor / reviewer order.

**Roster `family`** is the value to put in `roadmap/orchestration.yaml`. The
review gate counts distinct families by that value, not by the directory names
here. Opus and Fable are both `anthropic`, so an Opus review and a Fable review
count as one family.

| Model | Roster `family` | Profile | Rank | Context / output | Input / output (cached) | Fast tier | C / E / R | Runs |
|---|---|---|---|---|---|---|---|---|
| Claude Opus 5.5 | `anthropic` | [claude-opus-5-5](anthropic-claude/claude-opus-5-5.md) | latest | 1M / 128K | 4.00 / 20.00 (0.20) | 8 / 40 | 5 / 5 / 4 | both |
| Claude Opus 5 | `anthropic` | [claude-opus-5](anthropic-claude/claude-opus-5.md) | previous, legacy | 1M / 128K | 5.00 / 25.00 (0.50) | 10 / 50 | 4 / 4 / 4 | both |
| Claude Fable 5.1 | `anthropic` | [claude-fable-5-1](anthropic-claude/claude-fable-5-1.md) | latest | 1M / 128K | 10.00 / 50.00 (0.25) | unknown | 4 / 5 / 4 | Claude |
| Claude Fable 5 | `anthropic` | [claude-fable-5](anthropic-claude/claude-fable-5.md) | previous, legacy | 1M / 128K | 10.00 / 50.00 (1.00) | unknown | 3 / 4 / 3 | Claude |
| GPT-6.1 Sol | `openai` | [gpt-6.1-sol](openai-gpt/gpt-6.1-sol.md) | latest | 1.05M / 128K | 2.00 / 10.00 (0.10) | 12 / 60 (ultrafast) | 4 / 5 / 4 | both |
| GPT-6 Sol | `openai` | [gpt-6-sol](openai-gpt/gpt-6-sol.md) | previous | 1.05M / 128K | 2.00 / 10.00 (0.20) | 4 / 20 | 3 / 3 / 3 | both |
| Gemini 4 Argon | `google` | [gemini-4-argon](google-gemini/gemini-4-argon.md) | latest | 1M / 64K sync | 2.00 / 10.00 (0.10) until 2026-11-30, then 4 / 20 | unknown | 4 / 5 / 3 | both |
| Gemini 3.8 Flash | `google` | [gemini-3.8-flash](google-gemini/gemini-3.8-flash.md) | previous | 1M / 64K | 0.75 / 3.75 until 2026-12-31 | unknown | 2 / 3 / 2 | both |
| Grok 4.7 | `xai` | [grok-4.7](spacexai-grok/grok-4.7.md) | latest | 500K / unknown | 2.00 / 6.00 (0.50) | 4 / 12 | 3 / 4 / 3 | both |
| Grok 4.6 | `xai` | [grok-4.6](spacexai-grok/grok-4.6.md) | previous | 500K / unknown | 2.00 / 6.00 (0.50) | unknown | 3 / 3 / 3 | both |
| Muse Wonder | `meta` | [muse-wonder-1.0](meta-muse/muse-wonder-1.0.md) | latest | 1M / unknown | 4.00 / 20.00 (0.20) | unknown | 3 / 3 / 3 | Claude |
| Muse Spark 1.3 | `meta` | [muse-spark-1.3](meta-muse/muse-spark-1.3.md) | previous | 1M / 128K | 1.25 / 4.25 (0.15) | unknown | 2 / 3 / 2 | Claude |
| Composer 2.5 | `cursor` | [composer-2.5](cursor-composer/composer-2.5.md) | latest | unknown | 0.50 / 2.50 | 3 / 15 | 2 / 4 / 2 | Claude |
| Composer 2 | `cursor` | [composer-2](cursor-composer/composer-2.md) | previous, possibly stale | unknown | unknown | unknown | 1 / 3 / 1 | Claude |
| DeepSeek V4.1 Flash 1017 | `deepseek` | [deepseek-v4.1-flash-1017](deepseek/deepseek-v4.1-flash-1017.md) | latest | 1M / 384K | 0.30 / 1.20 (0.006) peak; half off-peak | unknown | 3 / 4 / 3 | ChatGPT |
| DeepSeek V4.1 Flash 20260910 | `deepseek` | [deepseek-v4.1-flash-20260910](deepseek/deepseek-v4.1-flash-20260910.md) | previous | 1M / 384K | 0.30 / 1.20 (0.006) at launch | unknown | 3 / 3 / 2 | ChatGPT |

Notes:

- **Composer** runs only inside Cursor and has no public API id.
- **DeepSeek:** both checkpoints are served under the moving alias
  `deepseek-flash`, which now serves 1017. Open weights let you pin a checkpoint
  by self-hosting.
- **Muse Wonder Full** is available only to Muse Code subscribers and is not
  profiled.
- **Muse Spark 1.3:** its `-contributor` tier ($0.10 / $0.20) lets Meta train on
  your data. Never send it proprietary code.

### Headless invocation

| Model | Command in the profile | Vendor-verified |
|---|---|---|
| Claude (Opus, Fable) | `claude -p "<prompt>"` | yes |
| GPT Sol | `codex exec --model <id> -c sandbox_mode=workspace-write -c approval_policy=never "<prompt>"` | run on codex-cli 0.165.0 (2026-10-28) |
| Gemini | `gemini -m <id> -p "<prompt>" --output-format json` | **no: verify before use** |
| Grok | `grok -p "<prompt>"` (no model flag in the verified form) | yes |
| Muse Spark 1.3 | `muse exec --model muse-spark-1.3 '<prompt>'` | **no: verify before use** |
| Composer | `agent -p --force "<prompt>"` (omit `--force` for review-only runs) | yes |
| DeepSeek 1017 | `claude -p "<prompt>" --output-format json`, via DeepSeek's Claude Code integration | **no: verify before use** |

`cli_verified_from: unverified` in a profile means the same thing: verify the
command before use. "Yes" means a run quoted a vendor page; a human still has
not checked it.

Muse Wonder has no known headless command. For every model, the two runs'
flags differ; see the watch-outs.

<!-- >>> harness facts: rendered by `specy-road refresh-profiles --render` from harness-facts.yaml; do not edit inside <<< -->

### Harness facts

Rendered from `harness-facts.yaml`. Each fact carries its label: `documented` (a vendor page or
repository doc), `runtime` (observed by running the binary) or `unverified`. The `access.cli` of
every profile whose `family` a harness's executor template names is rendered from it too;
`refresh-profiles --check` reports a hand edit to either as drift.

#### Claude Code (`claude-code`, binary `claude`)

- **Version:** `2.1.312` _[runtime: harness-captures/claude-code/version.txt (captured 2026-11-02)]_
- **Headless command:** `claude -p --output-format stream-json --verbose --session-id <uuid> --model <id> --permission-mode acceptEdits (prompt on stdin)` _[documented: specy_road/worker_adapters.py; docs/design-notes/harness-compatibility-triage.md]_
- **Executor template:** `claude -p "<prompt>"` _[documented: https://code.claude.com/docs/en/headless (profile source S4)]_
- **Session:** --session-id &lt;uuid&gt; chosen up front; --resume &lt;id&gt; to continue; never --continue across worktrees _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Permissions:** --permission-mode acceptEdits, or dontAsk with --allowedTools allow rules; bypassPermissions only inside an external sandbox. Since 2.1.302 -p silently denies unapproved tools _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Instruction files:** `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md` _[documented: docs/install-and-usage.md (validate context lines)]_; size: under 200 lines per file (vendor target); AGENTS.md and .claude/AGENTS.md only when none of the three exists
- **Skill directories:** `.claude/skills` _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Hooks:** PreToolUse hooks in .claude/settings.json fire under claude -p and block with exit 2; --bare skips every hook _[runtime: docs/optional-ai-tooling-patterns.md (sandbox run 2026-10-28)]_
- **Model families:** `anthropic` _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Quota:** a usage limit prints a message with a reset time; grind-session waits out a timed limit and stops on a spend cap or unrecognised wording _[documented: specy_road/claude_code_limits.py]_
- **Autonomous git actions:**
  - commits when asked, with an attribution trailer by default; switch: unknown (attribution setting not checked) _[unverified]_
  - --worktree / -w creates its own git worktree; switch: never pass -w/--worktree; specy-road creates the worktree _[runtime: harness-captures/claude-code/help.txt]_
  - --bg / --background and routines run sessions specy-road does not own; switch: never pass --bg; CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 _[documented: docs/design-notes/harness-compatibility-triage.md]_
  - --cloud and ultrareview run sessions or reviews in the cloud; switch: never pass --cloud; do not run ultrareview as gate evidence _[runtime: harness-captures/claude-code/help.txt]_

#### Codex CLI (`codex`, binary `codex`)

- **Version:** `codex-cli 0.165.0` _[runtime: harness-captures/codex/version.txt (captured 2026-11-02)]_
- **Headless command:** `codex exec --json -m <id> -c sandbox_mode=workspace-write -c approval_policy=never -C <worktree> - (prompt on stdin)` _[runtime: specy_road/worker_adapters.py (codex-cli 0.165, run 2026-10-28)]_
- **Executor template:** `codex exec --model {api_id} -c sandbox_mode=workspace-write -c approval_policy=never "<prompt>"` _[runtime: model-profiles/openai-gpt/gpt-6.1-sol.md (cli_verified_from codex-cli 0.165.0, run 2026-10-28)]_
- **Session:** thread id from the thread.started event; codex exec resume &lt;id&gt; - to continue; --last is cwd-scoped _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Permissions:** -c sandbox_mode=workspace-write -c approval_policy=never (exec has no --ask-for-approval; its default sandbox is read-only) _[runtime: specy_road/worker_adapters.py (codex-cli 0.165)]_
- **Instruction files:** `AGENTS.override.md`, `AGENTS.md` _[documented: docs/install-and-usage.md (validate context lines)]_; size: first non-empty of the two per directory from the git root down, truncated at project_doc_max_bytes (32 KiB); ~/.codex/AGENTS.override.md replaces the global file
- **Skill directories:** `.agents/skills` _[unverified]_
- **Hooks:** PreToolUse on Bash in .codex/hooks.json (or [hooks] in .codex/config.toml); exit 2 denies; project hooks load only when .codex/ is trusted, and an untrusted hook is skipped silently _[documented: docs/optional-ai-tooling-patterns.md]_
- **Model families:** `openai` _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Quota:** unknown; one failure exit is documented, so the event stream (turn.failed) is read, not the exit code _[unverified]_
- **Autonomous git actions:**
  - .git and the linked gitdir are read-only inside workspace-write, so the executor cannot commit; switch: none; the adapter commits on the worker's behalf (decision 2026-10-29, M8.2) _[documented: docs/design-notes/harness-compatibility-triage.md]_
  - --worktree runs the session in a new managed git worktree; switch: never pass --worktree _[runtime: harness-captures/codex/help.txt]_
  - fork and cloud start sessions or tasks specy-road does not own; switch: never run codex fork, codex exec fork or codex cloud for a leaf _[runtime: harness-captures/codex/help.txt]_
  - memories (memories.use_memories, memories.generate_memories) default on; switch: set both false; per-profile CODEX_HOME _[documented: docs/design-notes/harness-compatibility-triage.md]_

#### Cursor agent CLI (`cursor`, binary `agent`)

- **Version:** `2026.10.22-27dcf5f` _[runtime: harness-captures/cursor/version.txt (captured 2026-11-02)]_
- **Headless command:** `agent -p --output-format stream-json --force --trust --model <id> --workspace <worktree> "<prompt>"` _[documented: specy_road/worker_adapters.py; docs/design-notes/harness-compatibility-triage.md]_
- **Executor template:** `agent -p --force "<prompt>"` _[documented: model-profiles/cursor-composer/composer-2.5.md (source S2)]_
- **Session:** session id from the first stream event (or agent create-chat); --resume &lt;id&gt; to continue (with a new prompt in print mode undocumented); agent ls is not headless _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Permissions:** --force force-allows every command not denied; --trust skips a new worktree's trust prompt; pair with hooks or an external sandbox _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Instruction files:** `AGENTS.md`, `CLAUDE.md`, `.cursor/rules` _[documented: docs/install-and-usage.md (validate context lines)]_; size: no documented limit; only .cursor/rules with alwaysApply true load every session
- **Skill directories:** `.agents/skills`, `.cursor/skills`, `.claude/skills`, `.codex/skills` _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Hooks:** beforeShellExecution in .cursor/hooks.json answers allow or deny as JSON (failClosed true, or empty output fails open); also runs .claude/settings.json hooks _[runtime: docs/optional-ai-tooling-patterns.md (Cursor CLI 2026.10.22, sandbox run 2026-10-28)]_
- **Model families:** `anthropic`, `openai`, `xai`, `cursor`, `google` _[documented: docs/orchestration-models.md (Cursor model ids carry vendor and effort)]_
- **Quota:** unknown _[unverified]_
- **Autonomous git actions:**
  - -w / --worktree makes its own worktrees under ~/.cursor/worktrees; switch: never pass -w/--worktree _[runtime: harness-captures/cursor/help.txt]_
  - /split-to-prs, /autopilot and Cloud Agents create branches and PRs; switch: do not use them on a leaf _[documented: docs/design-notes/harness-compatibility-triage.md]_
  - plan mode (--plan, --mode plan) and generate-rule write harness planning or rules; switch: never pass --plan; do not run generate-rule _[runtime: harness-captures/cursor/help.txt]_

#### Generic (the profile's own command) (`generic`, binary `access.cli`)

- **Version:** `none of its own; the version is that of whatever binary access.cli names` _[unverified]_
- **Headless command:** `the roster channels.cli, else the profile's access.cli, with {prompt} (the prompt file path) or <prompt> (the prompt text) substituted` _[documented: docs/orchestration-workers.md (harness table); docs/orchestration-models.md]_
- **Executor template:** `the profile's own access.cli, written with "<prompt>" or {prompt}` _[documented: docs/orchestration-models.md (prompt --channel cli and generic workers run access.cli)]_
- **Session:** none; a generic worker cannot resume, interrupt or hand off _[documented: docs/orchestration-workers.md (harness table); specy_road/worker_adapters.py (Adapter.caps)]_
- **Permissions:** whatever the command's own flags grant; specy-road adds none _[unverified]_
- **Instruction files:** `AGENTS.md` _[unverified]_; size: unknown
- **Skill directories:** `.agents/skills` _[unverified]_
- **Hooks:** no hook of its own; the session guard's generic contract reads a JSON object with a command field on stdin and exits 2 to deny, for any harness that can call it _[documented: specy_road/tool_call_guard_adapters.py (generic adapter)]_
- **Model families:** none listed _[unverified]_
- **Quota:** unknown; no usage is reported (every usage field is null) _[documented: docs/orchestration-workers.md (usage events)]_
- **Autonomous git actions:**
  - unknown; depends on the binary access.cli names; switch: unknown _[unverified]_

<!-- >>> end harness facts <<< -->

## Role rankings

Both runs put **Claude Opus 5.5 first in all three roles.** Below that the order
differs, mainly on Gemini 4 Argon. The runs also ranked different rosters: the
Claude run ranked 7 models and the ChatGPT run ranked 5.

| Model | Coordinator (Claude / ChatGPT) | Executor (Claude / ChatGPT) | Reviewer (Claude / ChatGPT) |
|---|---|---|---|
| Claude Opus 5.5 | 1 / 1 | 2 / 1 | 1 / 1 |
| Claude Fable 5.1 | 2 / — | 1 / — | 3 / — |
| GPT-6.1 Sol | 3 / 3 | 3 / 3 | 2 / 3 |
| Gemini 4 Argon | 4 / 2 | 5 / 2 | 4 / 2 |
| Grok 4.7 | 6 / 4 | 4 / 4 | 6 / 4 |
| Muse Wonder | 5 / — | 6 / — | 5 / — |
| Composer 2.5 | 7 / — | 7 / — | 7 / — |
| DeepSeek V4.1 Flash 1017 | — / 5 | — / 5 | — / 5 |

- **Coordinator.**
  - Claude run: Opus 5.5 is the only model whose vendor publishes
    multiagent-harness guidance (time budgets, early-stop handling, progress
    updates), and it led the October Artificial Analysis readings at $4 / $20.
    Fable 5.1 is stronger on the hardest work but slower and 2.5x the price.
  - ChatGPT run: Opus 5.5 leads CursorBench 4.0 (57.8%) and one Terminal-Bench 4.0
    run (65.15%), and Claude Code has mature subagent workflows. Argon is close
    behind, leading LMArena Text and Multi-turn and scoring 52.9% on CursorBench
    4.0. GPT-6.1 Sol has strong cost-adjusted agent results and a native
    multi-agent beta in the Responses API.
- **Executor.**
  - Claude run: Fable 5.1 has the best published agentic numbers
    (Terminal-Bench 4.0 55.8%, AA Agentic Index 58.0). Opus 5.5 is the
    cost-adjusted default. GPT-6.1 Sol and Grok 4.7 give strong output per dollar.
  - ChatGPT run: by absolute quality, Opus 5.5, then Argon, then Sol. On cost the
    order changes sharply (see [Cheap first-pass executors](#cheap-first-pass-executors)).
  - Anthropic's own advice: start with Opus 5.5, and escalate to Fable 5.1 only
    when Opus 5.5 at higher effort fails your evals.
- **Reviewer.** Both runs say review-quality evidence is thin. Published
  benchmarks measure task completion, not approve/block calibration, so these
  rankings are inferred. Choose a reviewer mainly by its independence from the
  executor.

## Independent reviewer pairs

Both runs judge independence by vendor, training lineage, and API. Neither
measured pairs head to head.

| Pair | Recommended by |
|---|---|
| Opus 5.5 + GPT-6.1 Sol, either direction | Claude run (its top pair); ChatGPT run (Sol row) |
| Opus 5.5 + Gemini 4 Argon, either direction | ChatGPT run (its top pair); Claude run (Argon executes, Opus reviews) |
| Fable 5.1 executes, GPT-6.1 Sol reviews | Claude run |
| Composer 2.5 executes, Opus 5.5 or GPT-6.1 Sol reviews | Claude run |
| Grok 4.7 executes, Opus 5.5 reviews | both runs |
| Muse executes, Opus 5.5 reviews | Claude run |
| DeepSeek 1017 executes, Opus 5.5 or Argon reviews | ChatGPT run |

### Pairs that likely share blind spots

Use these for regression comparisons, not for independent approval:

- **Opus 5.5 with Fable 5.1:** same vendor, and Anthropic describes Opus 5.5 as
  Fable-level with the same safeguards.
- **Fable 5.1 with Fable 5 or Mythos 5.1:** same model lineage.
- **Any latest/previous pair in one family:** Opus 5.5 / Opus 5, GPT-6.1 Sol /
  GPT-6 Sol, Grok 4.7 / 4.6, Composer 2.5 / 2 (same Kimi K2.5 base), and the two
  DeepSeek checkpoints.
- **GPT-6.1 Sol with GPT-6 Astra:** OpenAI's system-card addendum says
  GPT-6.1 Sol "uses the same types of data and training as GPT-6 Astra."
- **Grok with GPT models (low confidence):** in Musk v. Altman on 2026-04-30,
  asked under oath whether xAI distilled OpenAI models to train Grok, Musk
  answered "Partly." The claim is low confidence, but it is reason enough not
  to use Grok and GPT as your two independent reviewers. The gate will count
  `xai` and `openai` as distinct families, so it will not catch this for you.
- **Composer with Kimi models:** Composer is built on Moonshot's Kimi K2.5. It
  is rostered as `cursor`, but it shares a base with any Kimi model you add.

## Cheap first-pass executors

Use these under a stronger reviewer from another family.

| Model | Price in / out | Caveat |
|---|---|---|
| DeepSeek V4.1 Flash 1017 | 0.30 / 1.20 peak, half off-peak | Moving alias; log the served checkpoint with every run |
| Composer 2.5 | 0.50 / 2.50 | Cursor only |
| Gemini 3.8 Flash | 0.75 / 3.75 | Introductory until 2026-12-31; CursorBench 4.0 High 39.6% |
| Muse Spark 1.3 | 1.25 / 4.25 | Standard tier only, never `-contributor` |
| Grok 4.7 | 2.00 / 6.00 | Prompts over 200K tokens cost more (see watch-outs) |
| GPT-6.1 Sol | 2.00 / 10.00 | Use the Responses API for tools |
| Gemini 4 Argon | 2.00 / 10.00 | Introductory until 2026-11-30, then 4 / 20 |

Pipelines suggested by the ChatGPT run:

- **Mistakes are cheap to catch in review:** DeepSeek 1017 does a narrowly
  scoped first pass; Opus 5.5 or Argon reviews.
- **A bad first edit is costly:** GPT-6.1 Sol executes and Opus 5.5 reviews. Sol
  costs far less than Opus and has stronger agent evidence than the cheapest
  models.
- **High-risk repository-wide refactors or migrations:** Opus 5.5 or Argon
  executes and the other reviews. Do not save tokens on the implementation pass.

## Capacity and availability

- **Fable 5 and Mythos 5** were suspended from 2026-06-12 to 2026-07-01 under a
  U.S. export-control directive. Regulatory action can remove a track with no
  notice, so keep a fallback model for any Fable role.
- **Grok:** status.x.ai shows a model outage on 2026-10-23/24 (about 40 minutes),
  degraded api.x.ai performance on 2026-10-24, and an issue on 2026-09-03.
- No incidents were found for the other families. That is unknown, not
  confirmed absent.

## Roster corrections and models not profiled

- **Gemini:** the newest Pro-class model, `gemini-3.1-pro-preview`, is still in
  preview. Gemini 3.8 Flash is therefore profiled as the previous GA release.
- **GPT-6 Astra** (`gpt-6-astra`, 2026-09-03/04, $10 / $50) is OpenAI's ChatGPT and
  flagship track. GPT-6.1 Astra was cancelled after safety testing found "higher
  levels of deception" (OpenAI's head of safety systems, via WSJ and Reuters,
  2026-09-28).
- **Meta Muse vs DeepSeek:** the ChatGPT run said Muse displaces DeepSeek at the
  frontier on broad capability: AA-derived index Muse Wonder 52.4 and Wonder Full
  55.8 vs DeepSeek 45.1; LMArena Text Muse Wonder #2 at 1509 vs DeepSeek about
  #38. It kept DeepSeek for its open weights and price. Both families are
  profiled here.
- **Candidates for a future roster:** Claude Sonnet 5.5 (AA 56.0, $2 / $10) and
  Kimi K3.1 Pro (AA 55.1) sit near the top of October 2026 leaderboards. Both
  listings republish Artificial Analysis data, so the prompt's two-index bar is
  not met.

## Watch out for: conflicting reports

Where the runs disagree, the profile keeps one value in its front matter and
lists both under Open questions. Check these before you rely on a value.

**Headless CLI flags.** For every model both runs covered, the two runs give
different command lines:

- **Claude:** the Claude run gives the vendor-verified `claude -p`. The ChatGPT run
  adds `--model` and `--output-format json` without citing a source.
- **GPT Sol:** the Claude run gives `codex exec -m` (third-party guides only). The
  ChatGPT run gives the sandbox and approval flags. Neither run verified its form.
- **Gemini:** the Claude run found no verified syntax. The ChatGPT run gives
  `gemini -m … -p`.
- **Grok:** the verified `grok -p` has no model flag. The ChatGPT run's `-m` and
  `--output-format` are unverified.

**Opus 5.5** ([profile](anthropic-claude/claude-opus-5-5.md))

- **Reviewer score:** Claude run 4 (vendor-reported evidence only), ChatGPT run 5.
- **AA Intelligence Index leader:** two aggregators citing the same index
  disagree. One has Opus 5.5 first at 57.6; the other has GPT-5.6 Sol first at 58.9.

**Opus 5** ([profile](anthropic-claude/claude-opus-5.md))

- **CursorBench:** Claude run 70.0% at max and 62.8% at low effort (version not
  stated, via Caylent). ChatGPT run 46.6% at Max on CursorBench 4.0. These are
  probably different benchmark versions.
- **Index scale:** 63 in August vs Opus 5.5's 57.6 in October. The index version
  changed between those readings.

**GPT-6.1 Sol** ([profile](openai-gpt/gpt-6.1-sol.md))

- **Effort levels:** Claude run says `none` and `minimal` are rejected. ChatGPT
  run lists `none` through `max`. The profile treats `none` as rejected.
- **Executor score:** Claude run 4 (no independent numbers found). ChatGPT run 5
  (Terminal-Bench 4.0, DeepSWE). The profile uses 5.

**GPT-6 Sol** ([profile](openai-gpt/gpt-6-sol.md))

- **Coordinator and executor scores:** Claude run 3 and 3, ChatGPT run 4 and 4.

**Gemini 4 Argon** ([profile](google-gemini/gemini-4-argon.md))

- **Output limit:** Claude run 65,536 per synchronous response, with longer output
  only through background long decode. ChatGPT run 1,048,576 (the unified window).
- **Ranking:** Claude run 4th or 5th of 7 in each role (AA index 53). ChatGPT run
  2nd of 5 in every role, and Opus + Argon as the best pair.
- **Role scores (C/E/R):** Claude run 4 / 4 / 3. ChatGPT run 5 / 5 / 4. The profile
  uses 4 / 5 / 3.
- **Index standing:** Claude run cites AA index 53. ChatGPT run cites LMArena Text
  and Multi-turn first places and CursorBench 4.0 52.9%. These are different
  indexes.
- **Context in Cursor:** 200K by default, vs 1M on the API (Claude run).

**Gemini 3.8 Flash** ([profile](google-gemini/gemini-3.8-flash.md))

- **Role scores (C/E/R):** Claude run 2 / 3 / 2 (thin evidence). ChatGPT run 4 / 4 / 3.

**Grok 4.7** ([profile](spacexai-grok/grok-4.7.md))

- **What $4 / $12 means:** Claude run says the whole request bills at $4 / $12
  once the prompt passes 200K tokens. ChatGPT run says $4 / $12 is the Fast-mode
  rate in Cursor and Grok Build, and long prompts are priced separately.
- **Evidence of gains over 4.6:** Claude run found vendor claims only. ChatGPT run
  has CursorBench 4.0 40.4 → 46.3% and Terminal-Bench 4.0 20.3 → 38.0%.
- **Coordinator score and ranking:** Claude run 3, 6th of 7 as coordinator, but
  4th as executor, ahead of Argon. ChatGPT run 4, 4th of 5 in every role,
  behind Argon.
- **Output limit:** xAI says "no text output limit" with a 128,000 default
  `max_output_tokens`; AWS lists 524,288 minus input.

**Grok 4.6** ([profile](spacexai-grok/grok-4.6.md))

- **Standing:** Claude run cites AA index 61 at launch (August index). ChatGPT run
  cites CursorBench 4.0 High 40.4%, "no longer frontier".
- **Context in Cursor:** 256K, vs 500K on the xAI API.

**Single-run conflicts** (sources disagreeing within one run)

- **Muse Wonder:** one leaderboard calls it self-hostable; VentureBeat reports no
  downloadable weights.
- **Muse Spark 1.3:** a tutorial shows `--reasoning-effort ultra`; Meta's docs top
  out at `max`.
- **Fable 5.1:** effort level names are not confirmed on a vendor page.

## Confidence and gaps

- **Low or medium confidence** (Claude run). The ChatGPT run marked nothing low
  and wrote `unknown` instead. Each profile tags every strength with its
  confidence.
  - Opus 5.5: medium-effort parity with Opus 5 high; AA first place; resistance
    to prompt injection.
  - Opus 5: CursorBench figures.
  - Fable 5.1: Terminal-Bench 4.0; AA Agentic 58.0; less test-disabling (low).
  - Fable 5: ARC-AGI-1 lead (low).
  - GPT-6.1 Sol: near-Astra claim.
  - Argon: DeepSWE and CWE-bench (low).
  - Gemini 3.8 Flash: positioning (low).
  - Grok 4.7: self-checking claim (low).
  - Grok 4.6: AA 61.
  - Muse Wonder: MemoryBench (low); AA 52.
  - Muse Spark 1.3: AA Agentic 55.7.
  - Composer 2.5: behaviour gains (low).
  - Composer 2: lineage (low).
  - Grok–GPT distillation overlap (low).
- **Still unknown after the merge:**
  - **Retention terms:** for Fable, Gemini, Muse, Composer, and DeepSeek (the
    ChatGPT run filled them in for Opus and Sol).
  - **Output limits:** Grok and Muse Wonder.
  - **Subagent support:** most models other than Opus 5.5, GPT-6.1 Sol, Argon,
    and DeepSeek 1017.
  - **Fable effort levels.**
  - **Composer:** its API id, limits, and effort controls.
  - **Composer 2:** all prices.
  - **Community-reported failure modes:** none met the two-report bar in either run.
- **Never measured:** reviewer false-positive and false-negative calibration,
  for any model.

## Keeping this current

From proposal §7.3, plus the merge rules above:

- When a vendor ships a version, re-run the §7.2 prompt with its scope narrowed
  to that family and the current profiles pasted in. The new release becomes
  `latest`, the old latest becomes `previous`, and the one before that is
  archived.
- Run both researchers. Keep each raw output under
  [`../design-notes/`](../design-notes/), merge with the rules above, and list
  new conflicts under Open questions and in this page's watch-out list.
- Treat a profile as stale when `researched` is old or its `api_id` is no longer
  the vendor's latest. Mark anything released more than 180 days before research
  as possibly stale. Slice 2's `models stale` will check this.
- Keep the front matter strict YAML, so `yaml.safe_load` reads it. Quote any
  value that contains a comma or colon, and quote `yes` and `no` so they stay
  strings. The raw research output does not follow this rule; normalize it when
  you merge.
