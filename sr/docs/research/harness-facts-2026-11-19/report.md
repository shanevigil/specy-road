# Harness facts for specy-road 0.3.1 (dated 2026-11-19)

Answers specy-road's request "dated harness facts for specy-road's 0.3.1 refresh" (2026-11-16, with the 2026-11-18 addendum on GPT-6.2 Sol and Astra), for its roadmap leaves M22.73 (refresh) and M22.72 (gate). Prepared in the private notes, a private-notes leaf

## How to read this report

- **One row per fact the request asks for.** The row ids are fixed in `questions.md`, which was committed before any value was collected.
- **Date** is the day the value was observed at its source: the day a host record was made, or the day a page or commit was read.
- **Status** is `checked` when the value comes from a primary source named in the row:
  - this host's `--version`, `--help` or model catalogue output, run as the test user the test user;
  - a run record of this repository;
  - a public page, quoted verbatim;
  - specy-road's own git history, read with `git show`.

  Otherwise the status is `not checked`, with the reason.
- **Version scope.** A `checked` host row holds for the version named in it, and for no later one. On 2026-11-19 the test user had Claude Code 2.1.319, codex-cli 0.166.0 and Cursor Agent 2026.11.05.
- **Two users, two installations.** The maintainer user of this host has its own CLIs. The briefing evaluation [B], a secondary source, gives them as Claude Code 2.1.325, codex-cli 0.166.0 and Cursor 2026.11.13 on 2026-11-16; they are not re-checked here. The installed-version rows give both, each dated. Only the the test user half is checked.
- **Claims are never results.** The request's figures, including its "local observation, unverified" catalogue table, and the briefing evaluation's claims are re-checked against a primary source or marked `not checked`.
- **Page summaries are not quotes.** Lines of a public note marked as a reading tool's summary, not verbatim, are not used as evidence for a `checked` value.

**Coverage on 2026-11-19.** 64 of 71 rows are `checked`. The 7 that are not:

- **Need a model call** (RUNBOOK step 4, not approved): whether Codex runs the two GPT-6.2 ids (SOL-CODEX, AST-CODEX).
- **No limit is in a committed record:** Codex and Cursor limit messages (CX-LIMIT, CU-LIMIT). For Cursor, the text is quoted from a coordinator observation, pending a private-notes leaf's record.
- **Not measured in this repository:** role suitability for the two GPT-6.2 models (SOL-ROLE, AST-ROLE).
- **Not covered by the newest host data:** the flag help of Claude Code versions after 2.1.319 (CC-FLAG-DIFF, the part after 2.1.319).

## Claude Code

| id | fact | value | date | source | status |
|---|---|---|---|---|---|
| CC-VER-INST | Installed version | Two dated facts. the test user: `2.1.319 (Claude Code)` on 2026-11-19 [H1], the same as on 2026-11-14 [R1]. Not part of the check: 2.1.325 on 2026-11-16 (maintainer user, per [B], not re-checked here). The two installations are separate. | 2026-11-19 | [H1] `claude/version.txt`; [R1]; maintainer half [B] only | checked |
| CC-VER-PUB | Published version, release date | npm `latest` (and `next`) is `2.1.329`, published 2026-11-19T18:40:25Z. The npm `stable` tag is `2.1.311`. For comparison: 2.1.319 (the test user) was published 2026-11-06T00:58:56Z and 2.1.325 (maintainer) on 2026-11-13T20:07:25Z. | 2026-11-19 | [P1] | checked |
| CC-FLAG-P | `-p` | Present, help text the same at 2.1.312 (specy-road's capture) and 2.1.319 (host, 2026-11-19). No change to `-p` itself was found in the changelog from 2.1.319 to 2.1.329 [P2]. | 2026-11-19 | [H2]; [P2] | checked |
| CC-FLAG-MODEL | `--model` | Present, help text the same. It takes an alias (`fable`, `opus`, `sonnet`) or a full name. The changelog read has one `--model` line, a 2.1.321 fix to `claude agents` ignoring it [P2]. | 2026-11-19 | [H2]; [P2] | checked |
| CC-FLAG-OUT | `--output-format stream-json` | Present, help still lists `stream-json`, text the same. No `--output-format` or stream-json change was found from 2.1.319 to 2.1.329 [P2]. specy-road adds `--verbose` [S1]. | 2026-11-19 | [H2]; [P2]; [S1] | checked |
| CC-FLAG-RESUME | `--resume` | Present, text the same. Changelog: 2.1.319 "Fixed `claude -p --resume` with a prompt losing a deferred tool call when its MCP server is missing: the run now exits 1". 2.1.328 adds `CLAUDE_CODE_DISABLE_DEFERRED_TOOL_RESUME`, which lets a host stop `claude -p --resume` and `--continue` from running deferred tool calls [P2]. | 2026-11-19 | [H2]; [P2] | checked |
| CC-FLAG-SID | `--session-id` | Present (must be a valid UUID), text the same. No change found from 2.1.319 to 2.1.329 [P2]. | 2026-11-19 | [H2]; [P2] | checked |
| CC-FLAG-DSP | `--dangerously-skip-permissions` | Present, text the same. The only changelog line found is a 2.1.321 fix to `claude agents` ignoring it [P2]. specy-road's `claude-worker.sh` and `fable-worker.sh` pass it [S1]. | 2026-11-19 | [H2]; [P2]; [S1] | checked |
| CC-FLAG-DIFF | Flag changes since 2.1.312 | **2.1.312 to 2.1.319, by help diff:** no option or subcommand added or removed; only the `auto-mode` description changed [H2]. **After 2.1.319, by changelog only:** <br>- 2.1.321: `--settings <file>` for `claude remote-control`; <br>- 2.1.323: start-up stops when a `--settings` file is not valid JSON and has a `sandbox` key; <br>- 2.1.323: `claude -p` no longer runs Bash unsandboxed when `--settings` that turn the sandbox on fail; <br>- 2.1.326: a start-up warning for odd `--allowedTools`, `--disallowedTools` or `--tools` entries; <br>- 2.1.329: saved scheduled tasks need scheduling again [P2]. <br>The changelog read lacks the 2.1.313, 2.1.315 and 2.1.320 sections [P2]. | 2026-11-19 | [H2]; [P2] | not checked: the help of versions after 2.1.319 was not captured (this host's the test user has 2.1.319), so later changes rest on the changelog alone, which was read with gaps |
| CC-SBX-WT | 2.1.323 sandbox and `git worktree` | Changelog 2.1.323: "Changed the sandbox on macOS and Linux: `git worktree add`, `move` and `remove` now fail read-only, as do commits in a worktree the session wasn't started in or given, even one inside the project". It concerns Claude Code's own sandbox. That this sandbox is opt-in is a claim [B], not re-read here. the test user's 2.1.319 predates the change; the maintainer's 2.1.325 has it. | 2026-11-19 | [P2] | checked |
| CC-PERM-GIT | 2.1.325 read-only git in another repository | Changelog 2.1.325: "Changed read-only git commands to ask first in a repository that isn't the project's or one you trusted; name it with…". The rest of the sentence (`--add-dir` as the remedy) was paraphrased, not quoted. Whether a linked worktree's main checkout counts as "the project's" is not stated. the test user's 2.1.319 predates the change. | 2026-11-19 | [P2] | checked |
| CC-MODEL-F52 | `claude-fable-5-2` | Changelog 2.1.321: "Added Claude Fable 5.2 (`claude-fable-5-2`), now the default Fable model". Docs: "Fable 5.2 requires Claude Code v2.1.321 or later" [P3]. Deprecations page: Active, retirement "Not sooner than November 9, 2027" [P3]. So the test user's 2.1.319 is below the required version. Cursor's the test user catalogue lists `claude-fable-5-2-{low,medium,high,xhigh,max}` and `-fast` variants [H1]. | 2026-11-19 | [P2]; [P3]; [H1] | checked |
| CC-MODEL-ALIAS | `fable` alias | Docs: "Unless you set `ANTHROPIC_DEFAULT_FABLE_MODEL`, the `fable` alias resolves to Fable 5 in Claude apps gateway sessions and to Fable 5.2 everywhere else" [P3]. 2.1.319's help accepts `fable` as an alias [H1]. The check covers the documented resolution and the help text only. Not checked: what `fable` resolves to in a 2.1.319 run on this host, which needs a model call (RUNBOOK step 4, not approved); see Open questions. | 2026-11-19 | [P3]; [H1] | checked |
| CC-MODEL-F51 | Fable 5.1 still offered | Yes. Deprecations page: `claude-fable-5-1` Active, retirement "Not sooner than September 1, 2027". Docs: select it by model id (`claude --model claude-fable-5-1`). A `claude-fable-5-1` saved in user settings moves to `fable` on Pro, Max, Ultra, Team and Enterprise plans; "Console accounts, third-party providers, and project, local, or managed settings keep `claude-fable-5-1`" [P3]. Cursor's catalogue also lists `claude-fable-5-1-*` [H1]. | 2026-11-19 | [P3]; [H1] | checked |
| CC-RESOLVED | Field that reports the model that ran | Two stream-json fields: the `system`/`init` event's `model` (line 1), and each `assistant` event's `message.model`. When a safeguard moves the session to another model, Claude Code emits `system`/`model_refusal_fallback` with `original_model` and `fallback_model`. After such a fallback, `init` still names the requested model, so the per-message model is the reliable field [R4]. A message Claude Code writes itself carries model `<synthetic>` [R5]. Seen at 2.1.319. | 2026-11-14 | [R2]; [R4]; [R5] | checked |
| CC-OUT | Output format parsed | `--output-format stream-json --verbose`, one JSON object per line: `system`/`init`, `assistant`, `user` (tool results), and a final `result`. Every line of the 2.1.319 runs parsed. | 2026-11-14 | [R2]; [R4] | checked |
| CC-LIMIT | Limit or reset message | Seen on this host: "You've hit your 5-hour limit", written as an `assistant` message with model `<synthetic>`; the run then ends with an error `result`. That was in two runs between 2026-11-09 and 2026-11-12, and the record does not hold the version [R5]. Changelog 2.1.323: "Improved the Fable limit message in `-p`, SDK, IDE and cloud sessions: it now says when the limit resets…" [P2]. The new wording itself was not quoted. | 2026-11-19 | [R5] Part D; [P2] | checked |
| CC-BILL | Billing for unattended runs | Docs: "In non-interactive mode with the `-p` flag … Claude Code never asks for consent. When a Fable request there would bill to usage credits, Claude Code bills it without asking." Also: "Depending on your plan and seat tier, Fable usage can bill to usage credits instead of drawing on your plan's included limits." API prices per MTok, input / output / cache hits: Fable 5.2 $8 / $40 / $0.20; Fable 5.1 $10 / $50 / $0.25 [P3]. | 2026-11-19 | [P3] | checked |

## Codex CLI

| id | fact | value | date | source | status |
|---|---|---|---|---|---|
| CX-VER-INST | Installed version | Two dated facts. the test user: `codex-cli 0.166.0` on 2026-11-19 [H1], the same as on 2026-11-14 [R1]. Not part of the check: 0.166.0 on 2026-11-16 (maintainer user, per [B], not re-checked here). | 2026-11-19 | [H1] `codex/version.txt`; [R1]; maintainer half [B] only | checked |
| CX-VER-PUB | Published version, release date | **Latest:** `0.170.0`, "released this 18 Nov 03:40". **Earlier:** 0.169.1 on 17 Nov 22:21; 0.169.0 on 13 Nov 08:37; 0.168.0 on 13 Nov 03:54. **Latest pre-releases by publication time:** `0.171.0-alpha.13.1`, 19 Nov 22:01, and `0.172.0-alpha.2`, 19 Nov 15:40. The releases page shows no year; 2026 follows from PR 60041's date, "Nov 7, 2026" [P4]. | 2026-11-19 | [P4] | checked |
| CX-FLAG-EXEC | `exec` | `codex exec` exists. Its help on 2026-11-19 is byte-identical to specy-road's 0.166.0 capture (same sha256). `codex review` also exists [H1]. | 2026-11-19 | [H2]; [H1] | checked |
| CX-FLAG-M | `-m` | `-m, --model <MODEL>` present, text the same. | 2026-11-19 | [H2] | checked |
| CX-FLAG-S | `-s workspace-write` | `-s, --sandbox <SANDBOX_MODE>` present; values `read-only`, `workspace-write`, `danger-full-access`. | 2026-11-19 | [H2] | checked |
| CX-FLAG-ADDDIR | `--add-dir` | Present: "Additional directories that should be writable alongside the primary workspace". | 2026-11-19 | [H2] | checked |
| CX-FLAG-SKIPGIT | `--skip-git-repo-check` | Present, text the same. | 2026-11-19 | [H2] | checked |
| CX-FLAG-O | `-o` | `-o, --output-last-message <FILE>` present, text the same. specy-road's `codex-review.sh` also passes `--json` [S1]. | 2026-11-19 | [H2]; [S1] | checked |
| CX-FLAG-MULTI | Replacement for `--disable multi_agent` | 0.168.0 release notes: "Codex warns when `features.multi_agent` is explicitly configured and points to `agents.enabled` for disabling subagent tools." The change is titled "Deprecate the `multi_agent` feature flag" (#59479) [P4]. The exact form of the `agents.enabled` setting on the command line is not on the pages read. At 0.166.0, `multi_agent` is a stable feature, on by default, and `--disable <FEATURE>` equals `-c features.<name>=false` [H1]. specy-road's bundled executor template passes `--disable multi_agent`; its adapter does not [S1, S2]. | 2026-11-19 | [P4]; [H1]; [S1]; [S2] | checked |
| CX-FLAG-DIFF | Flag changes since 0.166.0 | **Same version, by help diff:** `exec --help` is identical. The top-level help differs only in that specy-road's capture lists an `app` subcommand which this host's 0.166.0 does not [H2]. **After 0.166.0, by release notes only:** 0.168.0 deprecates the `multi_agent` feature flag; 0.169.0 adds `--trust` to `codex exec` and `codex review` [P4]. | 2026-11-19 | [H2]; [P4] | checked |
| CX-TRUST | 0.169.0 project trust and `--trust` | 0.169.0 notes: "`codex exec` keeps project configuration and MCP servers disabled in untrusted directories, even with `--sandbox workspace-write`", and "Use `--trust` with `codex exec` or `codex review` to explicitly save project trust." PR 60041: "The grant persists with `--ephemeral`", it "cannot be combined with `--ignore-user-config`" and it "refuses explicitly untrusted projects" [P4]. This host's 0.166.0 has no `--trust` [H2]. specy-road's adapter gives every launch its own `CODEX_HOME`, so no project is trusted there [S1]. | 2026-11-19 | [P4]; [H2]; [S1] | checked |
| CX-SBX-GIT | Sandbox and `.git` in an unattended run | Under `workspace-write`, Codex 0.166.0 ran the fixture's tests but could not commit, because `.git` was read-only. Under `--dangerously-bypass-approvals-and-sandbox` inside an outer bubblewrap sandbox, it committed. | 2026-11-14 | [R8]; [R4] | checked |
| CX-MODEL-TERRA | `gpt-6.1-terra*` through Codex | The catalogue offers one id, `gpt-6.1-terra`. Its fields: context window 500000, default effort `low`, efforts `low` to `ultra`, and "Efficient model that excels at visual understanding and computer use." [H1]. `-m gpt-6.1-terra` ran and was served as `gpt-6.1-terra` in every recorded run that requested it (2026-11-12, 2026-11-14) [R2, R3]. Effort goes through `-c model_reasoning_effort=<e>`, not an id suffix [S1]. | 2026-11-19 | [H1]; [R2]; [R3]; [S1] | checked |
| CX-RESOLVED | Field that reports the model that ran | The `--json` events carry no model field. The model is in the session rollout file (`sessions/YYYY/MM/DD/rollout-*.jsonl` under `CODEX_HOME`): `turn_context` events, `payload.model`. This is the model the client sent; a server-side substitution would not show [R5]. Seen at 0.166.0. | 2026-11-14 | [R4]; [R3]; [R2]; [R5] Part B2 | checked |
| CX-OUT | Output format parsed | `exec --json`, JSON lines: `thread.started` (thread id), `turn.started`, `item.completed` (`command_execution`, `file_change` and others), `turn.completed` (usage), and `turn.failed` or `error`. `-o` writes the final message to a file. | 2026-11-14 | [R2]; [H1] `codex/help-exec.txt` | checked |
| CX-LIMIT | Limit or reset message | No limit event in any record here, and none on the pages read. specy-road documents a turn failure whose text names the reset ("You've hit your usage limit ... try again in <duration>") [S2]. | 2026-11-19 | [S2] | not checked: no limit was hit in a recorded run; specy-road's text is its own record, not re-observed here |
| CX-BILL | Billing for unattended runs | Codex pricing page: "ChatGPT Work and Codex share pricing, credits, and usage limits."; "API-key sessions use separate API pricing, not your ChatGPT allowance."; "Local messages and cloud chats share your plan's usage allowance." No billing text specific to `codex exec` was found [P5]. | 2026-11-19 | [P5] | checked |

## Cursor Agent CLI

| id | fact | value | date | source | status |
|---|---|---|---|---|---|
| CU-VER-INST | Installed version | Two dated facts. the test user: `2026.11.05-86047df` (binary `cursor-agent`) on 2026-11-19 [H1], the same as on 2026-11-14 [R1]. Not part of the check: `2026.11.13-eacade1` (binary `agent`) on 2026-11-16 (maintainer user, per [B], not re-checked here). | 2026-11-19 | [H1] `cursor/version.txt`; [R1]; maintainer half [B] only | checked |
| CU-VER-PUB | Published version, release date | The CLI changelog's top entry is `v2026.11.17`. Its entries carry no dates, so no release date is published [P6]. | 2026-11-19 | [P6] | checked |
| CU-FLAG-ROSTER | Agent CLI flags in specy-road's roster and adapter | **Reviewer wrapper** `cursor-review.sh`: `agent -p --force --model <id> --output-format stream-json <prompt>`. <br>**Default executor:** `agent create-chat`, then `agent -p --resume <chat> --output-format stream-json --trust --sandbox enabled --model <id> --workspace <worktree> [--add-dir <dir>] <prompt>`. A roster entry with `cursor_force: true` gets `--trust --force` instead of `--trust --sandbox enabled`. The entries with `cursor_force: true` are `claude-opus-5-5-high`, `grok-4.7-exec` and `composer-2.5`. <br>**Default reviewer:** `agent -p [--resume <id>] --output-format stream-json --mode ask --trust --model <id> <prompt>`. <br>All of these flags are in the 2026.11.05 help, unchanged. | 2026-11-19 | [S1]; [H2] | checked |
| CU-FLAG-DIFF | Flag changes since 2026.10.22 | From 2026.10.22 (specy-road's capture) to 2026.11.05 (host, 2026-11-19): no option or subcommand added or removed; only the `update` subcommand gained `[options]`. Builds 2026.11.13 and later are not on this host's the test user. | 2026-11-19 | [H2] | checked |
| CU-SBX | Sandbox, trust, permission | On this host, `--sandbox enabled` was not enforced (2026.11.05). The stream showed the requested policy (`TYPE_WORKSPACE_READWRITE`, no network), but pip still downloaded from PyPI; only the outer bubblewrap sandbox refused writes [R4]. specy-road's roster notes that Cursor's sandbox does not start on this host (AppArmor) [S1]. `--trust` skips the workspace trust prompt [H1]. `--model` rewrites `cli-config.json`, which fails with `EBUSY` when that file is mounted read-only [R3]. | 2026-11-14 | [R4]; [R3]; [H1]; [S1] | checked |
| CU-MODEL-GROK | `grok-4.7-*` ids | the test user's catalogue lists `grok-4.7-low`, `-medium`, `-high` and `-xhigh`, each with a `-fast` variant [H1]. `grok-4.7-medium` selects model id `grok-4.7` with parameters `context=256k`, `reasoning_effort=medium` and `fast=false`. It was served as "Grok 4.7 256K Medium" (2026.11.05) [R6, R3]. Cursor's models page names "Grok 4.7", "Grok 4.7 (Fast)", "Grok 4.7 500k" and "Grok 4.7 500k (Fast)" [P6]. | 2026-11-19 | [H1]; [R6]; [R3]; [P6] | checked |
| CU-MODEL-TERRA | `gpt-6.1-terra*` through Cursor | Not offered. the test user's catalogue has no `gpt-6.*` id; its newest Terra is `gpt-5.6-terra-*` [H1]. No `gpt-6.1-terra` appears on Cursor's docs pages read [P6]. | 2026-11-19 | [H1]; [P6] | checked |
| CU-RESOLVED | Field that reports the model that ran | Only the stream-json `system`/`init` event's `model`, as a display name ("Composer 2.5", "Grok 4.7 256K Medium"), or `Auto` when routing is on. The stream carries no model id. Seen at 2026.11.05. | 2026-11-14 | [R3]; [R4]; [R2] | checked |
| CU-OUT | Output format parsed | `--output-format stream-json`: `system`/`init`, `assistant`, `tool_call` (`started` and `completed`) and a final `result`. Every line of the 2026.11.05 runs parsed. | 2026-11-14 | [R2]; [R4] | checked |
| CU-LIMIT | Limit or reset message | **Observed once, not yet in a committed record.** In a `-p --output-format stream-json` run (Cursor 2026.11.05, model `claude-opus-5-5`, run `20261119T232135Z-rec-cursor-s9-pin-opus`), the coordinator read this on stderr on 2026-11-19 [C1]. The account's figures, plan name and cycle date are left out here: "ActionRequiredError: You've hit your usage limit for Opus … Switch to a different model or set a Spend Limit to continue with Opus. Your usage limits will reset when your monthly cycle ends on <date>." Reading it: the limit is per model (Opus), the reset is the end of the monthly billing cycle, and the text arrives on stderr, not as a stream-json event. No other limit event is in any record here. specy-road lists the Cursor quota as unknown [S2]. | 2026-11-19 | [C1]; [S2] | not checked: pending source; the run's record (with its `transcript-stderr.log` hash) lands with a private-notes leaf, and until then the text rests on a coordinator observation that a reviewer cannot re-read from the repository |
| CU-BILL | Billing for unattended runs | Models page: "Each paid plan includes one pool of usage for Cursor models."; the pool "is shared across everything on your subscription: Agent in the editor, CLI, Cloud Agents…"; "It refreshes weekly"; "Third-party models like Claude, GPT, and Gemini aren't part of the included pool." Pricing page: "Third Party model usage in Cursor is not included in the monthly prices shown and must be purchased separately." [P6] | 2026-11-19 | [P6] | checked |

## GPT-6.2 Sol (`gpt-6.2-sol`)

The request's "local observation, unverified" table is re-checked here against this host's Codex catalogue (the test user, codex-cli 0.166.0, 2026-11-19) [H1] and OpenAI's model pages [P5]. Every catalogue value in the request's Sol row matches.

| id | fact | value | date | source | status |
|---|---|---|---|---|---|
| SOL-ID | Model id | `gpt-6.2-sol`. The model page says "Model ID: `gpt-6.2-sol`" [P5]; the Codex catalogue slug is `gpt-6.2-sol`, display name "GPT-6.2-Sol", `supported_in_api: true` [H1]. | 2026-11-19 | [P5]; [H1] | checked |
| SOL-CTX | Context window | **API:** a 1,050,000 context window, 922,000 maximum input tokens and 128,000 maximum output tokens [P5]. **Codex catalogue:** `context_window` 500000 (as the request reported), `max_context_window` 872000, `effective_context_window_percent` 95 [H1]. | 2026-11-19 | [P5]; [H1] | checked |
| SOL-EFF-DEF | Default effort | Codex catalogue: `default_reasoning_level` `low` (as the request reported) [H1]. OpenAI's API guide does not state a model default; it advises "Start with `medium` for a new integration." [P5] | 2026-11-19 | [H1]; [P5] | checked |
| SOL-EFF-SUP | Supported efforts | Codex catalogue: `low`, `medium`, `high`, `xhigh`, `max`, `ultra` (as the request reported) [H1]. API: "The API rejects requests that set reasoning effort to `none`." [P5] | 2026-11-19 | [H1]; [P5] | checked |
| SOL-PRICE | Prices | API Standard, per 1M tokens: input $2, cached input $0.1, cache writes $2.5, output $10. "Batch costs 50% of Standard rates. Fast mode costs twice the Standard rate". Above 272K input tokens, input and cache rates double and output costs 1.5 times as much, for the full request [P5]. | 2026-11-19 | [P5] | checked |
| SOL-LIMITS | Usage limits | API rate limits: Build tier 5,000 RPM and 1,000,000 TPM; Launch 10,000 RPM and 4,000,000 TPM; Grow 15,000 RPM and 40,000,000 TPM [P5]. No per-model limits for Codex subscription plans were found; Codex shares "pricing, credits, and usage limits" with ChatGPT Work [P5]. | 2026-11-19 | [P5] | checked |
| SOL-CODEX | Headless through Codex | The id is in the Codex 0.166.0 catalogue with visibility `list` [H1]. The form specy-road uses for other OpenAI models is `codex exec --json -m <id> [-c model_reasoning_effort=<e>] ...` [S1]. Whether 0.166.0 runs this id and reports it as served was not observed. | 2026-11-19 | [H1]; [S1] | not checked: needs a model call (RUNBOOK step 4), which is not approved |
| SOL-CURSOR | Headless through Cursor | Not offered. the test user's Cursor catalogue has no `gpt-6.2-*` id [H1], and Cursor's docs pages read do not mention GPT-6.2 [P6]. | 2026-11-19 | [H1]; [P6] | checked |
| SOL-FAIL | Known failure modes | From OpenAI's GPT-6.2 guide, which covers the family: "When the model loses access to reasoning items, answer quality can decline". "GPT-6.2 Astra and Sol don't support Flex processing (`service_tier: flex`)." "Models starting with GPT-6.2 append top-level `instructions` after `input` in the Responses API." No known-issues page was found [P5]. | 2026-11-19 | [P5] | checked |
| SOL-PROMPT | Prompting guidance | Family-level only: "Use the following prompts as a starting point across the GPT-6.2 model family."; "Higher reasoning effort can help it persist through the final checks on complex or long-running tasks."; "Describe the codebase's conventions and any behavior that existing callers rely on." No Sol-specific guidance was found [P5]. | 2026-11-19 | [P5] | checked |
| SOL-ROLE | Role suitability | Vendor positioning only: "Our go-to model for everyday work, from coding to powering agents at scale."; "Use GPT-6.2 Astra for the most demanding tasks or GPT-6.2 Sol for complex work at lower cost." [P5] | 2026-11-19 | [P5] | not checked: vendor text is not a measurement; no study here has used this model, and measuring model quality is outside this report |
| SOL-FAMILY | Review-family independence | specy-road's roster policy requires 2 reviewers from distinct families (`reviewers_required: 2`, `reviewers_distinct_families: true`). Its OpenAI entries (`gpt-6.1-*`, `gpt-5.6-*`) are family `openai`, so an OpenAI model is not independent of them. | 2026-11-19 | [S1] `sr/roadmap/orchestration.yaml` | checked |

## GPT-6.2 Astra (`gpt-6.2-astra`)

| id | fact | value | date | source | status |
|---|---|---|---|---|---|
| AST-ID | Model id | `gpt-6.2-astra`. The model page says "Model ID: `gpt-6.2-astra`" [P5]; the Codex catalogue slug is `gpt-6.2-astra`, display name "GPT-6.2-Astra", `supported_in_api: true` [H1]. | 2026-11-19 | [P5]; [H1] | checked |
| AST-CTX | Context window | **API:** a 1,050,000 context window, 922,000 maximum input tokens and 128,000 maximum output tokens [P5]. **Codex catalogue:** `context_window` 272000 (as the request reported), `max_context_window` 872000, `effective_context_window_percent` 95 [H1]. | 2026-11-19 | [P5]; [H1] | checked |
| AST-EFF-DEF | Default effort | Codex catalogue: `default_reasoning_level` `low` (as the request reported) [H1]. The API guide advises "Start with `medium` for a new integration." [P5] | 2026-11-19 | [H1]; [P5] | checked |
| AST-EFF-SUP | Supported efforts | Codex catalogue: `low`, `medium`, `high`, `xhigh`, `max`, `ultra` (as the request reported) [H1]. The API rejects `none` [P5]. | 2026-11-19 | [H1]; [P5] | checked |
| AST-PRICE | Prices | API Standard, per 1M tokens: input $8, cached input $0.4, cache writes $10, output $40. Batch is 50% of Standard and fast mode twice. Above 272K input tokens, input and cache rates double and output costs 1.5 times as much [P5]. | 2026-11-19 | [P5] | checked |
| AST-LIMITS | Usage limits | API rate limits as for Sol: Build 5,000 RPM and 1,000,000 TPM; Launch 10,000 RPM and 4,000,000 TPM; Grow 15,000 RPM and 40,000,000 TPM [P5]. No per-model limits for Codex subscription plans were found [P5]. | 2026-11-19 | [P5] | checked |
| AST-CODEX | Headless through Codex | The id is in the Codex 0.166.0 catalogue with visibility `list` [H1]; the form would be as SOL-CODEX [S1]. Not observed. | 2026-11-19 | [H1]; [S1] | not checked: needs a model call (RUNBOOK step 4), which is not approved |
| AST-CURSOR | Headless through Cursor | Not offered. the test user's Cursor catalogue has no `gpt-6.2-*` id [H1], and "Astra" does not appear on Cursor's docs pages read [P6]. | 2026-11-19 | [H1]; [P6] | checked |
| AST-FAIL | Known failure modes | As SOL-FAIL (the guide covers the family): reasoning items, no Flex processing, and `instructions` appended after `input` in the Responses API. No known-issues page was found [P5]. | 2026-11-19 | [P5] | checked |
| AST-PROMPT | Prompting guidance | Family-level guidance as SOL-PROMPT, plus "GPT-6.2 Astra is more concise and direct by default than earlier models." [P5] | 2026-11-19 | [P5] | checked |
| AST-ROLE | Role suitability | Vendor positioning only: "Our most capable model for your hardest projects, from start to finish." [P5] | 2026-11-19 | [P5] | not checked: vendor text is not a measurement; no study here has used this model, and measuring model quality is outside this report |
| AST-FAMILY | Review-family independence | As SOL-FAMILY: an OpenAI model is family `openai` under specy-road's roster, so it is not independent of the other OpenAI reviewer entries, nor of `gpt-6.2-sol`. | 2026-11-19 | [S1] `sr/roadmap/orchestration.yaml` | checked |
| G62-PREV | "Previous generation" labels | Confirmed in the Codex catalogue. `gpt-6.1-sol`: "Previous generation model for coding and everyday work." `gpt-6-astra`: "Previous generation model for complex coding and professional work." The catalogue also has `gpt-6-sol`, `gpt-5.6-sol`, `gpt-5.6-terra` and `gpt-5.6-luna` as "Legacy" models. `gpt-6.2-astra`'s description in full is "Our most capable model for complex coding and professional work." [H1] No OpenAI page read uses "previous generation" [P5]. | 2026-11-19 | [H1]; [P5] | checked |

## What changed since specy-road's captured versions

specy-road captured Claude Code 2.1.312, codex-cli 0.166.0 and Cursor 2026.10.22 on 2026-11-02. On 2026-11-19, the test user on this host had 2.1.319, 0.166.0 and 2026.11.05, and the latest published versions were 2.1.329, 0.170.0 and 2026.11.17.

**Claude Code**
- **2.1.312 to 2.1.319, by help diff:** no flag or subcommand added or removed; the six headless flags have the same help text [H2].
- **Later, by changelog [P2]:**
  - 2.1.321 adds Fable 5.2 and needs 2.1.321 or later for it;
  - 2.1.323 makes the sandbox fail `git worktree` lifecycle commands, adds the reset time to the Fable limit message, and stops start-up on an invalid sandbox `--settings` file;
  - 2.1.325 makes read-only git ask first in a repository other than the project's;
  - 2.1.326 warns on odd `--allowedTools`, `--disallowedTools` and `--tools` entries;
  - 2.1.328 adds `CLAUDE_CODE_DISABLE_DEFERRED_TOOL_RESUME`.

**Codex**
- **0.166.0:** `exec --help` is unchanged [H2].
- **0.168.0:** deprecates the `multi_agent` feature flag in favour of `agents.enabled` [P4].
- **0.169.0:** keeps project config and MCP servers off in untrusted directories, and adds `--trust` to `codex exec` and `codex review` [P4].
- **Latest:** 0.170.0 (2026-11-18) [P4]. No Codex version after 0.166.0 is installed for the test user on this host.

**Cursor**
- **2026.10.22 to 2026.11.05:** no flag or subcommand added or removed; only the `update` line changed [H2].
- **Later:** builds up to v2026.11.17 have been published [P6], and none of them is installed for the test user.

**Models**
- Fable 5.2 is out and Fable 5.1 is still active [P3].
- GPT-6.2 Sol and Astra are in the Codex catalogue but not in Cursor's [H1].

**specy-road's own wrappers** (at the commits read [S1]): `claude-review.sh`, `codex-review.sh` and `cursor-review.sh` now print the harness's native event stream ("the native event stream (M22.71)"), with `--json` added to the Codex reviewer. The 2026-11-16 briefing evaluation describes the older behaviour, which printed only the final JSON.

## Open questions

1. Whether Codex 0.166.0 runs `gpt-6.2-sol` and `gpt-6.2-astra` and reports them as served, and what `fable` resolves to in a 2.1.319 run. Each needs a model call (RUNBOOK step 4), which is not approved.
2. The help text of Claude Code after 2.1.319, Codex after 0.166.0 and Cursor after 2026.11.05. None of these is installed for the test user.
3. Whether a linked worktree's main checkout counts as "the project's" under Claude Code 2.1.325's read-only git rule.
4. Whether Codex's `--json` stream at 0.169.0 or later carries a model field. At 0.166.0 it does not, so specy-road's M22.71 must read the rollout file.
5. The command-line form of Codex's `agents.enabled` setting.
6. Codex limit and reset messages: no Codex limit was hit in any run recorded here. For Cursor, the Opus limit text seen in a private-notes leaf's run becomes checkable once that run's record is committed (CU-LIMIT).

## Maintainer decisions this report respects

It states facts and does not recommend changing these decisions:

- older models stay allowed while their providers offer them, because a roster pin is only a default;
- reviewers stay untrusted, with no `--trust` in a reviewer launch.

The flag listings above are reported as found. The Cursor reviewer launch's `--trust` is Cursor's workspace-trust flag, which is not Codex's `--trust`.

## Sources

**This host, as the test user** (commands run under the per-run-isolation launcher, sha256 e095f347…, with no model call):

- **[H1]** (private notes),codex,cursor}/`, commit 098b5b6, collected 2026-11-19 at 23:08 UTC. Each harness's `--version`, `--help` and catalogue output. The Codex catalogue files `debug-models.txt` and `models_cache.json` are committed reduced: the vendor prompt-text fields are replaced by a marker, and every metadata field is kept. Raw sha256 values are in `codex/REDUCED.md`.
- **[H2]** (private notes), commit 8733479. It compares [H1]'s help files with specy-road's captures [S2] at specy-road d95cacd3.

**Public pages.** Each was read 2026-11-19, about 23:00–23:15 UTC, page text only and with no sign-in. Notes with verbatim excerpts are in (private notes), commit 48c3404. Lines a reading tool summarised are not used as checked evidence.

- **[P1]** npm registry, `@anthropic-ai/claude-code`: https://registry.npmjs.org/@anthropic-ai/claude-code
- **[P2]** Claude Code changelog: https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md. The 2.1.313, 2.1.315 and 2.1.320 sections were not in the text read.
- **[P3]** Claude Code model configuration: https://code.claude.com/docs/en/model-config. Claude model deprecations: https://platform.claude.com/docs/en/about-claude/model-deprecations. Claude API pricing: https://platform.claude.com/docs/en/about-claude/pricing.
- **[P4]** Codex releases: https://github.com/openai/codex/releases, with tags `rust-v0.168.0` and `rust-v0.169.0`. Pull request 60041: https://github.com/openai/codex/pull/60041.
- **[P5]** OpenAI model pages: https://developers.openai.com/api/docs/models/gpt-6.2-sol and https://developers.openai.com/api/docs/models/gpt-6.2-astra. GPT-6.2 guide: https://developers.openai.com/api/docs/guides/latest-model. Codex models and pricing: https://learn.chatgpt.com/docs/models and https://learn.chatgpt.com/docs/pricing.
- **[P6]** Cursor CLI changelog: https://cursor.com/docs/cli/changelog. Also https://cursor.com/changelog, https://cursor.com/docs/models, https://cursor.com/pricing, https://cursor.com/docs/cli/headless and https://cursor.com/docs/cli/overview.

**Records of the private notes**, each cited by path and the commit that last changed it:

- **[R1]** (private notes) (`versions.txt`, `claude.txt`, `codex-exec.txt`, `cursor-agent.txt`), commit 84f8db3. `--version` and `--help` run as the test user on 2026-11-14.
- **[R2]** (private notes), commit 17c62c9. Run records of 22 captures on 2026-11-14, made as the test user under the per-run-isolation launcher.
- **[R3]** (private notes), commit da2c1cf. 25 Cursor and Codex captures on 2026-11-12.
- **[R4]** (private notes), commit ea86796. Harness runs under bubblewrap on 2026-11-09, with Claude Code 2.1.319, Codex 0.166.0 and Cursor 2026.11.05.
- **[R5]** (private notes), commit 9cb9b8b. Part B2 covers Codex rollouts; Part D covers Claude Code worker runs, 2026-11-09 to 2026-11-12.
- **[R6]** `tools/recorder/cursor-pins.json`, commit 5a78dd4. What `cursor-agent --model <id>` wrote, probed with 2026.11.05 on 2026-11-14.
- **[R7]** (private notes). The same comparison as [H2], for [R1]'s 2026-11-14 help files, at specy-road bb4b4d59.
- **[R8]** (private notes), commit 17c62c9. Covers the narrow-profile runs of 2026-11-14.

**specy-road**, read only with `git show` and `git log` on 2026-11-19, at commit bb4b4d59ce3b48ef80f9d5e73f998fa34f244d88. Every file below is unchanged at d95cacd3be1321c82cf8fbccc78ae61abe8ae292: that commit changes only `sr/roadmap/registry.yaml` and `sr/roadmap-context.md`.

- **[S1]** `sr/roadmap/orchestration.yaml`; `sr/tools/claude-worker.sh`, `fable-worker.sh`, `claude-review.sh`, `codex-review.sh`, `cursor-review.sh`; `specy_road/orchestration/workers/worker_adapters.py` and `worker_adapter_codex.py`.
- **[S2]** `specy_road/templates/project/model-profiles/harness-facts.yaml` and `harness-captures/` (claude-code, codex and cursor, captured 2026-11-02).

**Coordinator observation** (pending a committed record):

- **[C1]** Run `20261119T232135Z-rec-cursor-s9-pin-opus` of a private-notes leaf. It is a capture made as the test user under the per-run-isolation launcher, listed in (private notes) at commit 634f4c3. Its `transcript-stderr.log` was read on this host by the coordinator on 2026-11-19, and the text was relayed to the executor. The record itself is not committed yet; it lands with a private-notes leaf.

**Inputs from the request** (untrusted, secondary):

- **[Q]** The request, the harness-facts request of 2026-11-16 (private notes), with its 2026-11-18 addendum. Its figures are claims; no row rests on [Q] alone.
- **[B]** (private notes), the briefing evaluation of 2026-11-16, a secondary source. Here it is cited for the maintainer user's installed versions and for claims that are marked as claims. The maintainer-user versions rest on [B] alone and are not re-checked; in the three installed-version rows only the the test user half is checked.

## Limits

- **Published versions, prices and limits change fast.** Every row is dated, and none holds after its date without a new check.
- **The host data covers the test user only.** The maintainer user's versions come from the briefing evaluation, two days older.
- **Model catalogues depend on the account.** The Codex and Cursor catalogues are the test user's, and specy-road's 2026-11-02 Cursor capture was made under another account.
- **Public pages were read by a page-reading tool.** Quotes are excerpts of at most about 125 characters, and some pages were read only in part, such as gaps in the changelog sections. A summarised line is never used as checked evidence.
- **A model name in a stream is what the harness reports,** not proof of the model that served the run. This applies to Cursor's display names and to Codex's rollout `model`.
- **No paid API was used and no model was called** for this report. No specy-road code was copied out; only facts read with `git show` are cited.
