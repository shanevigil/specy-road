---
profile_schema: 2
family: OpenAI GPT
track: Astra
model: GPT-6.2 Astra
api_id: gpt-6.2-astra
checkpoint: unknown
alias_moves: unknown
version_rank: latest
release_date: unknown   # the dated report has no release-date row for this model
researched: 2026-11-19
researcher: field
supersedes: gpt-6-astra
access:
  context_tokens: 272000
  output_tokens: 128000   # API maximum, AST-CTX (checked); Codex catalogue states no separate output limit
  cli: codex exec --model gpt-6.2-astra --disable memories -c sandbox_mode=workspace-write -c approval_policy=never - < {prompt}
  cli_verified_from: 'not run with this model; the codex executor template (harness-facts.yaml) with the api_id the Codex catalog lists [S1]'
  subagents: 'yes Codex catalog lists multi_agent_version v2 and an ultra effort described as maximum reasoning with automatic task delegation [S1]'
  effort_controls: 'low, medium, high, xhigh, max, ultra (catalog default low) [S1]'
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 8.00, output: 40.00, cached_input: 0.40, fast_input: 16.00, fast_output: 80.00 }   # AST-PRICE; fast is twice standard
data_handling: 'Served in Codex; the Codex catalog marks it supported_in_api and lists a Fast service tier ("2x speed, increased usage") [S1]. Retention, training use and residency were not researched for this model.'
role_fit:
  coordinator: { score: 3, reason: 'Not piloted as a coordinator; no evidence either way', sources: [] }
  executor:    { score: 3, reason: 'Not piloted as an executor; no evidence either way', sources: [] }
  reviewer:    { score: 3, reason: 'Not piloted as a reviewer; same openai family as the other GPT profiles, so it adds no family diversity to a review pair with them', sources: [] }
---
## Orchestration: harness features to avoid

When this model runs as a roster **executor** on `codex`, the executor template and `access.cli` below pass these switches, for `specy-road prompt --channel cli` and generic-harness workers. **The default `worker delegate` codex launch does not pass them:** it turns memories off with `-c features.memories=false -c memories.use_memories=false -c memories.generate_memories=false` and the profile's own `CODEX_HOME`, and leaves multi_agent and goals at Codex's defaults (both on in the codex-cli 0.166.0 capture). A roster `channels.cli` that runs the executor template disables memories only; multi_agent stays on (operator 2026-11-19, supersedes the F15 avoid) and goals stays on (operator 2026-11-20, same as multi_agent, supersedes the F15 avoid):

| Feature | Switch |
|---|---|
| memories | `--disable memories` |

Orchestration guard hooks deny executors `git push`, `gh pr`, worktree and cloud commands; reviewers also deny `git commit`.

Under the default codex launch (`sandbox_mode=workspace-write`) an executor cannot commit: git metadata is read-only, in a linked worktree (its gitdir under the main checkout's `.git/worktrees/`, and the common `.git`) and in a plain checkout alike. Give a codex executor a `channels.cli` and `cli_resume` that add the worktree's gitdir and the common `.git` as writable roots (specy-road `https://github.com/shanevigil/specy-road/blob/main/docs/orchestration-workers.md`, Roster setup, "Known limitation").

## Strengths
- The Codex catalog describes it as "Our most capable model for complex coding and professional work." and lists it at priority 2 [S1] (confidence: low, vendor self-description)
- Codex catalog context window 272000 tokens (max_context_window 872000, effective_context_window_percent 95) [S1] (confidence: medium)
## Failure modes
- No failure modes observed; not piloted [S1]
## Code and test tendencies
- GPT-5.x High was the most verbose model in Sonar's December 2025 leaderboard data (974,379 LOC on the same Java task set vs Gemini 3 Pro ~289,752); vendor benchmark, single-file Java, directional only (researched 2026-10-27 from the lean-code reports, not human-verified) [S2]
- Codex PRs reverted least in the field: 6.1 percent vs 11.5 percent human (OR 0.50), median 63 changed lines (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S3]
- OpenAI's Codex guidance says to search for prior art and reuse or extract a shared helper before adding new helpers or logic, and warns against speculative changes, broad catches and silent defaults (read 2026-10-27; researched 2026-10-27 from the lean-code reports, not human-verified) [S4]
## Prompting rules
- Set effort explicitly; the Codex catalog default is low [S1]
- Do not send ultra to an executor: the catalog describes it as reasoning with automatic task delegation, and the default codex worker launch leaves multi_agent on [S1]
- Set sandbox and approval policy in the harness, and in a linked worktree give it write access to the git metadata, or it cannot commit (https://github.com/shanevigil/specy-road/blob/main/docs/orchestration-workers.md, "Known limitation", checked on codex-cli 0.165.0)
- Require a prior-art search before any new helper and a named reuse in the summary, and fix the output format; this family writes the most code per task but its merged work holds up [S2, S4]
## From the dated report (2026-11-19)
- API standard price per MTok is input $8, cached input $0.40, output $40; fast mode is twice that. Cache writes are $10. Above 272K input tokens, input and cache rates double and output costs 1.5 times (AST-PRICE, checked) [S5]
- API maximum output is 128000 tokens. The API context window is 1050000, with a 922000 input cap; context_tokens stays the Codex catalogue window 272000 (max 872000). Both figures are AST-CTX, checked [S5]
- Codex catalogue default effort is low. The API guide states no model default and says to start with medium (AST-EFF-DEF, checked) [S5]
- Not offered in Cursor (AST-CURSOR, checked) [S1, S5]
- The catalogue calls gpt-6-astra the previous generation for this kind of work (G62-PREV, checked); no gpt-6-astra profile ships [S1, S5]
## Open questions
- Release date stays unknown: the report's question list has no release-date row, and no checked row dates this model [S5]
- Role scores stay the not-piloted default: AST-ROLE is not checked (vendor text is not a measurement; no study here has used this model, and measuring model quality is outside this report) [S5]
- Whether Codex 0.166.0 runs this id stays unknown: AST-CODEX is not checked (needs a model call, RUNBOOK step 4, which is not approved) [S5]
## Sources
- S1: Codex model catalog (`codex debug models`), codex-cli 0.166.0, captured 2026-11-19, runtime
- S2: New data on code quality: GPT-5.2 high, Opus 4.5, Gemini 3, and more, Sonar, 2025-12, https://www.sonarsource.com/blog/new-data-on-code-quality-gpt-5-2-high-opus-4-5-gemini-3-and-more/, vendor benchmark on Java single-file tasks (lean-code reports)
- S3: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S4: Codex best practices (search for prior art before adding helpers), OpenAI, accessed 2026-10-27, https://developers.openai.com/codex/learn/best-practices, primary (lean-code reports)
- S5: Harness-facts report 2026-11-19, sr/docs/research/harness-facts-2026-11-19/report.md (AST-PRICE, AST-CTX, AST-EFF-DEF, AST-CURSOR, AST-ROLE, AST-CODEX, G62-PREV)
