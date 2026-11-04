# Model profiles: choosing models for orchestration roles

This page is the canonical guide to filling the roster in
`roadmap/orchestration.yaml` (toolkit docs: `docs/orchestration.md` for the
roles and review gate, `docs/orchestration-models.md` for `models`, `prompt`,
and `orchestrate plan`). It covers where the profiles come from, the roster,
and how to keep it current. Each model has a profile under this directory with
its limits, prices, headless invocation, failure modes, and prompting rules. The
research behind the roster — role rankings, independent reviewer pairs, cheap
first-pass executors, capacity incidents, roster corrections, conflicting
reports, and confidence gaps — is in
[`docs/model-profiles-research-notes.md`](../docs/model-profiles-research-notes.md).

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
[orchestration proposal](https://github.com/shanevigil/specy-road/blob/main/docs/design-notes/model-aware-orchestration-proposal.md) §7.2,
weighted equally:

| Run | Researched | Schema | Roster | Raw output |
|---|---|---|---|---|
| ChatGPT (Deep Research) | 2026-10-20 | 1 | GPT Sol, Claude Opus, Gemini, Grok, DeepSeek | [proposal §7.4](https://github.com/shanevigil/specy-road/blob/main/docs/design-notes/model-aware-orchestration-proposal.md) |
| Claude (Research) | 2026-10-26 | 2 | Claude Opus and Fable, GPT Sol, Gemini, Grok, Meta Muse, Cursor Composer | [model-research-2026-10-26-claude.md](https://github.com/shanevigil/specy-road/blob/main/docs/design-notes/model-research-2026-10-26-claude.md) |

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
  `Watch out — reports differ:` with both values. They are also collected under
  *Watch out for: conflicting reports* in the research notes.
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
| GPT-5.6 Sol | `openai` | [gpt-5.6-sol](openai-gpt/gpt-5.6-sol.md) | previous | 1M / unknown | 4.00 / 20.00 (unknown) | unknown | 4 / 4 / 4 | Cursor |
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

**Candidate harness profiles** (2026-11-03, vendor documentation only; every
runtime check is `not run` because neither binary is installed). Both pin Gemini
4 Argon and run on the `generic` harness. Their `api_id` is the roster id, not
a vendor model id:

| Profile | Command in the profile | Role |
|---|---|---|
| [copilot-gemini-4-argon](github-copilot/copilot-gemini-4-argon.md) | `copilot -p "<prompt>" -s --no-ask-user --no-auto-update --model=gemini-4-argon --allow-tool='shell,write' --deny-tool='shell(git push),…,shell(gh:*),memory'` | one-shot reviewer |
| [agy-gemini-4-argon-high](google-antigravity/agy-gemini-4-argon-high.md) | `agy -p "<prompt>" --output-format json --print-timeout 60m --model gemini-4-argon-high` | generic; success is the envelope's `status: SUCCESS`, never the exit code |

Each profile's `## Runtime checks` lists what to run once the binary is
installed.

`cli_verified_from: unverified` in a profile means the same thing: verify the
command before use. "Yes" means a run quoted a vendor page; a human still has
not checked it.

Muse Wonder has no known headless command. For every model, the two runs'
flags differ; see *Watch out for: conflicting reports* in the research notes.

<!-- >>> harness facts: rendered by `specy-road refresh-profiles --render` from harness-facts.yaml; do not edit inside <<< -->

### Harness facts

Rendered from `harness-facts.yaml`. Each fact carries its label: `documented` (a vendor page or
repository doc), `runtime` (observed by running the binary) or `unverified`. The `access.cli` of
every profile whose `family` a harness's executor template names is rendered from it too;
`refresh-profiles --check` reports a hand edit to either as drift.

#### Claude Code (`claude-code`, binary `claude`)

- **Version:** `2.1.312` _[runtime: harness-captures/claude-code/version.txt (captured 2026-11-02)]_
- **Headless command:** `claude -p --output-format stream-json --verbose --session-id <uuid> --model <id> --permission-mode acceptEdits (prompt on stdin)` _[documented: specy_road/worker_adapters.py; docs/design-notes/harness-compatibility-triage.md]_
- **Executor template:** `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 claude -p "<prompt>"` _[documented: https://code.claude.com/docs/en/headless (profile source S4)]_
- **Session:** --session-id &lt;uuid&gt; chosen up front; --resume &lt;id&gt; to continue, from any directory or worktree on the machine (the session is found by its id); never --continue across worktrees. Transcripts are ~/.claude/projects/&lt;project&gt;/&lt;session-id&gt;.jsonl, kept 30 days by default (cleanupPeriodDays), so a worker idle longer cannot resume _[documented: https://code.claude.com/docs/en/headless (continue conversations); https://code.claude.com/docs/en/sessions; docs/design-notes/harness-compatibility-triage.md; 2026-11-02 triage F8]_
- **Permissions:** --permission-mode acceptEdits, or dontAsk with --allowedTools allow rules; bypassPermissions only inside an external sandbox. Since 2.1.302 -p silently denies unapproved tools. A denial does not stop the run - stream-json emits permission_denied system messages, the result lists them in permission_denials, and the process exits 0 (M8.7 run, 2.1.312); --permission-prompts none (2.1.259+) denies anything that would prompt and tells Claude not to retry; deny rules go in --disallowedTools, e.g. "Bash(git push *)" (a trailing ' *' is a prefix match) _[documented: https://code.claude.com/docs/en/headless (auto-approve tools; turn off permission prompts); docs/design-notes/M8.7-runtime-verification-harness-facts.md (exit 0 on a denial); harness-captures/claude-code/help.txt (--disallowedTools); 2026-11-02 triage F5]_
- **Instruction files:** `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md`, `CLAUDE.local.md` _[documented: https://code.claude.com/docs/en/memory; docs/install-and-usage.md (validate context lines); 2026-11-02 triage F1]_; size: under 200 lines per file (vendor target); a file over 4 MiB is skipped and none of it loads; .claude/rules/ is read recursively; subdirectory CLAUDE.md files and path-scoped rules load on demand, when Claude touches a file there, with a smaller per-file limit; the managed policy CLAUDE.md and ~/.claude/CLAUDE.md (and ~/.claude/rules/) load on every machine-level session; AGENTS.md and .claude/AGENTS.md only when none of the project files exists; AGENTS.override.md is never read; --bare skips all of these
- **Skill directories:** `.claude/skills`, `.claude/commands`, `.claude/agents` _[documented: https://code.claude.com/docs/en/headless (bare mode lists skills, custom commands and subagents as discovered; --agents &lt;json&gt; adds subagents; subagent messages carry parent_tool_use_id); docs/design-notes/harness-compatibility-triage.md; 2026-11-02 triage F3]_
- **Hooks:** PreToolUse hooks in .claude/settings.json fire under claude -p and block with exit 2; --bare skips every hook. Exit 1 (or any code but 0 and 2) does not block; a hook that times out does not block unless it sets onFailure "block" (2.1.295+); hookSpecificOutput.permissionDecision "deny" on exit 0 also blocks; -p runs a project's hooks with no trust prompt, even in a folder never trusted _[documented: https://code.claude.com/docs/en/hooks; https://code.claude.com/docs/en/headless (bare mode); docs/optional-ai-tooling-patterns.md (exit 2 observed in the sandbox run 2026-10-28); 2026-11-02 triage F4]_
- **Model families:** `anthropic` _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Quota:** a usage limit prints a message with a reset time; grind-session waits out a timed limit and stops on a spend cap or unrecognised wording. A retryable API failure emits system/api_retry (error "rate_limit", retry_delay_ms, attempt, max_retries) before retrying; the reset time is only in the message text. The exit code on a limit is not dependable - vendor issues report exit 0 with subtype success and the error only in result (#79500), exit 1 with api_error usage_limit_reached and nothing on stdout (#103820), and exit 1 "No messages returned from query" (#103253) - so read the result line and the transcript, never the exit code _[documented: https://code.claude.com/docs/en/headless (handle API retries); https://github.com/anthropics/claude-code/issues/79500; https://github.com/anthropics/claude-code/issues/103820; https://github.com/anthropics/claude-code/issues/103253; specy_road/claude_code_limits.py; 2026-11-02 triage F6]_
- **Autonomous git actions:**
  - commits when asked, with an attribution trailer by default; switch: unknown (attribution CLI setting not checked; Co-Authored-By trailer observed at runtime) _[runtime: docs/design-notes/M8.7-runtime-verification-harness-facts.md (claude 2.1.312, nested/sub commit 2026-11-02)]_
  - --worktree / -w creates its own git worktree; switch: never pass -w/--worktree; specy-road creates the worktree _[runtime: harness-captures/claude-code/help.txt]_
  - --bg / --background and routines run sessions specy-road does not own (-p rejects --bg); switch: never pass --bg; CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 _[documented: https://code.claude.com/docs/en/headless; docs/design-notes/harness-compatibility-triage.md; 2026-11-02 triage F7]_
  - claude -p stays open after its reply for background commands, background subagents and workflows, Monitor watches and pending /loop wakeups it started, ending them after 10 minutes of continuous idle waiting (a running background command or a pending /loop wakeup extends the wait past that cap); switch: CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1 or --bare (no background tasks); CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS changes the 10-minute cap; --max-budget-usd stops the remaining work _[documented: https://code.claude.com/docs/en/headless (background tasks at exit); 2026-11-02 triage F7]_
  - --cloud and ultrareview run sessions or reviews in the cloud; under -p, --cloud with a task description is rejected but --cloud &lt;session&gt; queues a message into an existing cloud session and exits; switch: never pass --cloud; do not run ultrareview as gate evidence _[documented: https://code.claude.com/docs/en/headless (basic usage); harness-captures/claude-code/help.txt; 2026-11-02 triage F7]_
  - native subagents (the Agent tool, forked skills) run inside the session; their messages carry parent_tool_use_id; switch: none needed (they run in the leaf's own session and worktree); --disallowedTools Agent removes the tool _[documented: https://code.claude.com/docs/en/headless (follow subagent messages); harness-captures/claude-code/help.txt (--disallowedTools); 2026-11-02 triage F7]_
  - auto memory - ~/.claude/projects/&lt;project&gt;/memory/MEMORY.md, first 200 lines or 25 KB loaded into every session and shared by every worktree of the repository; switch: --bare (reviewer launches already pass it); for executors, autoMemoryEnabled false in --settings or project settings, or CLAUDE_CODE_DISABLE_AUTO_MEMORY=1 _[documented: https://code.claude.com/docs/en/memory (auto memory); https://code.claude.com/docs/en/headless (bare mode); 2026-11-02 triage F2]_

#### Codex CLI (`codex`, binary `codex`)

- **Version:** `codex-cli 0.166.0` _[runtime: harness-captures/codex/version.txt (captured 2026-11-02 from codex-cli 0.166.0 with a fresh CODEX_HOME; triage F10)]_
- **Headless command:** `codex exec --json -m <id> -c sandbox_mode=workspace-write -c approval_policy=never -C <worktree> - (prompt on stdin)` _[runtime: specy_road/worker_adapters.py (codex-cli 0.165, run 2026-10-28)]_
- **Executor template:** `codex exec --model {api_id} --disable memories --disable multi_agent --disable goals -c sandbox_mode=workspace-write -c approval_policy=never "<prompt>"` _[runtime: model-profiles/openai-gpt/gpt-6.1-sol.md (cli_verified_from codex-cli 0.165.0, run 2026-10-28)]_
- **Session:** thread id from the thread.started event; codex exec resume &lt;id&gt; - to continue; --last is cwd-scoped. A resume carries only the conversation, so sandbox, approval, model and memory settings are passed again; 0.166.0 keeps acknowledged approval and permission settings on resume and fork; resume by id from a sibling worktree is undocumented _[documented: https://github.com/openai/codex/pull/4583; https://learn.chatgpt.com/docs/changelog (Codex CLI 0.166.0); docs/design-notes/harness-compatibility-triage.md; 2026-11-02 triage F11]_
- **Permissions:** -c sandbox_mode=workspace-write -c approval_policy=never (exec has no --ask-for-approval; its default sandbox is read-only); --full-auto is no longer supported (use --sandbox workspace-write) _[runtime: specy_road/worker_adapters.py (codex-cli 0.165); https://learn.chatgpt.com/docs/non-interactive-mode; 2026-11-02 triage F16]_
- **Instruction files:** `AGENTS.override.md`, `AGENTS.md` _[documented: docs/install-and-usage.md (validate context lines); https://github.com/openai/codex/issues/7138; 2026-11-02 triage F16]_; size: first non-empty of the two per directory from the git root down, truncated at project_doc_max_bytes (32 KiB) silently, with no warning; ~/.codex/AGENTS.override.md replaces the global file
- **Skill directories:** `.agents/skills` _[runtime: docs/design-notes/M8.7-runtime-verification-harness-facts.md (codex-cli 0.165.0 loads .agents/skills at exec start, 2026-11-02)]_
- **Hooks:** PreToolUse on Bash in .codex/hooks.json (or [hooks] in .codex/config.toml); exit 2 denies; project hooks load only when .codex/ is trusted, and an untrusted hook is skipped silently. Hooks are on by default (features list shows hooks stable true on a fresh CODEX_HOME, 0.166.0; [features] hooks = false turns them off); --dangerously-bypass-hook-trust runs enabled hooks without persisted trust for one invocation _[documented: https://learn.chatgpt.com/docs/hooks; harness-captures/codex/inventory-features.txt and help-exec.txt (0.166.0); docs/optional-ai-tooling-patterns.md; 2026-11-02 triage F14]_
- **Model families:** `openai` _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Quota:** a usage limit arrives as a failure whose free text names the reset ("You've hit your usage limit ... try again in &lt;duration&gt;"), so the reset time is read from that message; exit code on a limit unknown, and one failure exit is documented, so the event stream (turn.failed) is read, not the exit code _[runtime: docs/design-notes/M8.7-runtime-verification-harness-facts.md (turn.failed with exit 0 on model error, codex-cli 0.165.0, 2026-11-02); https://github.com/openai/codex/issues/4764 (message text); 2026-11-02 triage F12]_
- **Autonomous git actions:**
  - .git and the linked gitdir are read-only inside workspace-write, so the executor cannot commit; switch: none; the adapter commits on the worker's behalf (decision 2026-10-29, M8.2) _[documented: docs/design-notes/harness-compatibility-triage.md]_
  - --worktree runs the session in a new managed git worktree; switch: never pass --worktree _[runtime: harness-captures/codex/help.txt]_
  - fork and cloud start sessions or tasks specy-road does not own; switch: never run codex fork, codex exec fork or codex cloud for a leaf _[runtime: harness-captures/codex/help.txt]_
  - memories (memories.use_memories, memories.generate_memories); the 0.165.0 changelog enables memory v2 by default for fresh profiles, while the 0.166.0 features list on a fresh CODEX_HOME shows the memories feature stable false; the key names under v2 are not documented; switch: --disable memories and both memories keys false; per-profile CODEX_HOME _[documented: https://learn.chatgpt.com/docs/changelog (Codex CLI 0.165.0); harness-captures/codex/inventory-features.txt (0.166.0); docs/design-notes/harness-compatibility-triage.md; 2026-11-02 triage F13]_
  - multi_agent (stable, on in the 0.166.0 capture) lets the session spawn its own subagents; switch: --disable multi_agent _[runtime: harness-captures/codex/inventory-features.txt (0.166.0); 2026-11-02 triage F13]_
  - goals (stable, on in the 0.166.0 capture) keeps durable goals across turns; switch: --disable goals _[runtime: harness-captures/codex/inventory-features.txt (0.166.0); 2026-11-02 triage F13]_
  - codex queue queues a message for an existing session, and queue --resume (0.166.0) resumes an unloaded thread afterwards; switch: never run codex queue for a leaf _[documented: https://learn.chatgpt.com/docs/changelog (Codex CLI 0.166.0); harness-captures/codex/help.txt; 2026-11-02 triage F13]_

#### Cursor agent CLI (`cursor`, binary `agent`)

- **Version:** `2026.10.22-27dcf5f` _[runtime: harness-captures/cursor/version.txt (captured 2026-11-02)]_
- **Headless command:** `agent -p --output-format stream-json --force --trust --model <id> --workspace <worktree> "<prompt>"` _[documented: specy_road/worker_adapters.py; docs/design-notes/harness-compatibility-triage.md]_
- **Executor template:** `agent -p --force "<prompt>"` _[runtime: model-profiles/cursor-composer/composer-2.5.md (source S2); --force alone passes a fresh worktree's trust prompt and a bare agent -p exits 1, so --trust is not needed here (agent 2026.10.22-27dcf5f, 2026-11-02, docs/design-notes/harness-facts-2026-11-02-triage.md K13; https://cursor.com/docs/cli/reference/parameters; triage F22)]_
- **Session:** session id from the first stream event (or agent create-chat); --resume &lt;id&gt; to continue (with a new prompt in print mode undocumented), from any directory since 2026.07.06; agent ls is not headless; concurrent CLI processes no longer corrupt cli-config.json (2026.07.06) _[documented: https://cursor.com/docs/cli/changelog; https://cursor.com/docs/cli/reference/parameters; docs/design-notes/harness-compatibility-triage.md; 2026-11-02 triage F17]_
- **Permissions:** --force force-allows every command not denied; --trust skips a new worktree's trust prompt; pair with hooks or an external sandbox. Deny rules are permissions.deny tokens (Shell(git), Read(...), Write(...), WebFetch(...), Mcp(server:tool)) in ~/.cursor/cli-config.json or &lt;project&gt;/.cursor/cli.json and take precedence over allow rules; --sandbox enabled|disabled; --mode ask is read-only Q&A (reviewers) _[documented: https://cursor.com/docs/cli/reference/permissions; https://cursor.com/docs/cli/reference/parameters; harness-captures/cursor/help.txt (--mode); docs/design-notes/harness-compatibility-triage.md; 2026-11-02 triage F18]_
- **Instruction files:** `AGENTS.md`, `CLAUDE.md`, `.cursor/rules` _[documented: docs/install-and-usage.md (validate context lines); https://cursor.com/docs/cli/changelog; 2026-11-02 triage F19]_; size: no documented limit; only .cursor/rules with alwaysApply true load every session; nested AGENTS.md files apply once the agent edits or creates a file in their directory (2026.10.22)
- **Skill directories:** `.agents/skills`, `.cursor/skills`, `.claude/skills`, `.codex/skills` _[documented: docs/design-notes/harness-compatibility-triage.md]_
- **Hooks:** beforeShellExecution in .cursor/hooks.json answers allow or deny as JSON (failClosed true, or empty output fails open); also reads and merges .claude/settings.json hooks; preToolUse and postToolUse events also fire for subagents (2026.10.17); the preToolUse blocking contract is not documented. Project hooks load and block under agent -p --force, with or without --trust, an empty matcher matching every command; beforeShellExecution sees only the shell tool, so the agent's own file edit and delete tools pass it _[runtime: docs/optional-ai-tooling-patterns.md (Cursor CLI 2026.10.22, sandbox run 2026-10-28); https://cursor.com/docs/cli/changelog; 2026-11-02 triage F21; agent 2026.10.22-27dcf5f, composer-2.5, 2026-11-04 (a throwaway repo's appending hook fired under agent -p --force, and a deny hook blocked under -p --force --trust --workspace; the CR3 replay transcripts show the session guard rejecting git restore before the edit/delete tools discarded the files, docs/design-notes/context-regressions-2026-11-04-triage.md)]_
- **Model families:** `anthropic`, `openai`, `xai`, `cursor`, `google` _[documented: docs/orchestration-models.md (Cursor model ids carry vendor and effort); fresh CLI installs default to Auto model routing, so a launch without --model is routed dynamically (https://cursor.com/docs/cli/changelog, 2026.07.06; triage F21)]_
- **Quota:** unknown (no usage-limit event observed on this account during M8.7 runs) _[documented: docs/design-notes/M8.7-runtime-verification-harness-facts.md (still unknown, agent 2026.10.22, 2026-11-02)]_
- **Autonomous git actions:**
  - -w / --worktree makes its own worktrees under ~/.cursor/worktrees; switch: never pass -w/--worktree _[runtime: harness-captures/cursor/help.txt]_
  - /split-to-prs, /autopilot and Cloud Agents create branches and PRs; switch: do not use them on a leaf _[documented: docs/design-notes/harness-compatibility-triage.md]_
  - plan mode (--plan, --mode plan) and generate-rule write harness planning or rules; switch: never pass --plan; do not run generate-rule _[runtime: harness-captures/cursor/help.txt]_
  - agent persist starts sessions that survive terminal disconnects (/detach, agent persist attach); switch: none known; never run agent persist for a leaf _[documented: https://cursor.com/docs/cli/changelog (2026.08.26); harness-captures/cursor/help.txt; 2026-11-02 triage F20]_
  - /goal tracks a durable goal that continues across idle and headless runs (gated rollout); switch: none known; never invoke /goal on a leaf _[documented: https://cursor.com/docs/cli/changelog (2026.08.11); 2026-11-02 triage F20]_

#### Generic (the profile's own command) (`generic`, binary `access.cli`)

- **Version:** `none of its own; the version is that of whatever binary access.cli names` _[documented: docs/design-notes/M8.7-runtime-verification-harness-facts.md (by definition; not one binary, 2026-11-02)]_
- **Headless command:** `the roster channels.cli, else the profile's access.cli, with {prompt} (the prompt file path) or <prompt> (the prompt text) substituted` _[documented: docs/orchestration-workers.md (harness table); docs/orchestration-models.md]_
- **Executor template:** `the profile's own access.cli, written with "<prompt>" or {prompt}` _[documented: docs/orchestration-models.md (prompt --channel cli and generic workers run access.cli)]_
- **Session:** none; a generic worker cannot resume, interrupt or hand off _[documented: docs/orchestration-workers.md (harness table); specy_road/worker_adapters.py (Adapter.caps)]_
- **Permissions:** whatever the command's own flags grant; specy-road adds none _[documented: docs/design-notes/M8.7-runtime-verification-harness-facts.md (still unknown per access.cli; not exercised, 2026-11-02)]_
- **Instruction files:** `AGENTS.md` _[documented: docs/design-notes/M8.7-runtime-verification-harness-facts.md (specy-road init convention; not verified per generic binary, 2026-11-02)]_; size: unknown
- **Skill directories:** `.agents/skills` _[documented: docs/design-notes/M8.7-runtime-verification-harness-facts.md (init layout; per-binary load still unknown, 2026-11-02)]_
- **Hooks:** no hook of its own; the session guard's generic contract reads a JSON object with a command field on stdin and exits 2 to deny, for any harness that can call it _[documented: specy_road/tool_call_guard_adapters.py (generic adapter)]_
- **Model families:** none listed _[documented: docs/design-notes/M8.7-runtime-verification-harness-facts.md (roster contract; empty list by design, 2026-11-02)]_
- **Quota:** unknown; no usage is reported (every usage field is null) _[documented: docs/orchestration-workers.md (usage events)]_
- **Autonomous git actions:**
  - unknown; depends on the binary access.cli names; switch: unknown _[documented: docs/design-notes/M8.7-runtime-verification-harness-facts.md (still unknown per access.cli, 2026-11-02)]_

<!-- >>> end harness facts <<< -->

## Keeping this current

From proposal §7.3, plus the merge rules under *Where this comes from*:

- When a vendor ships a version, re-run the §7.2 prompt with its scope narrowed
  to that family and the current profiles pasted in. The new release becomes
  `latest`, the old latest becomes `previous`, and the one before that is
  archived.
- Run both researchers. Keep each raw output in a tracked file (the toolkit keeps
  its own in [`docs/design-notes/`](https://github.com/shanevigil/specy-road/tree/main/docs/design-notes)), merge with the rules above, and list
  new conflicts under Open questions and in the research notes' watch-out list.
- Treat a profile as stale when `researched` is old or its `api_id` is no longer
  the vendor's latest. Mark anything released more than 180 days before research
  as possibly stale. Slice 2's `models stale` will check this.
- Keep the front matter strict YAML, so `yaml.safe_load` reads it. Quote any
  value that contains a comma or colon, and quote `yes` and `no` so they stay
  strings. The raw research output does not follow this rule; normalize it when
  you merge.
