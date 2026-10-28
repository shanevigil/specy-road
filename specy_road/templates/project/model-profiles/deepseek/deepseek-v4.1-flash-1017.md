---
profile_schema: 2
family: DeepSeek
track: Flash
model: DeepSeek-V4.1-Flash-1017
api_id: deepseek-flash
checkpoint: V4.1-Flash-1017
alias_moves: 'yes'
version_rank: latest
release_date: 2026-10-17
researched: 2026-10-20
researcher: chatgpt
supersedes: deepseek-flash (checkpoint V4.1-Flash-20260910)
access:
  context_tokens: 1048576
  output_tokens: 393216
  cli: claude -p "<prompt>" --output-format json
  cli_verified_from: unverified
  subagents: yes DeepSeek's official Claude Code configuration sets CLAUDE_CODE_SUBAGENT_MODEL=deepseek-flash [S4]
  effort_controls: 'none, low, high, max'
  effort_map: { minimal: low, low: low, medium: high, high: high, max: max }
cost_usd_per_mtok: { input: 0.30, output: 1.20, cached_input: 0.006, fast_input: unknown, fast_output: unknown }
data_handling: 'DeepSeek''s Responses interface is stateless, but the reviewed primary material did not establish a precise default API-log retention period or a zero-data-retention commitment, so provider-side API retention is unknown [S6, S7]. DeepSeek Harness documents a local-first design [S7]. V4.1 Flash open weights are published, which allows private or self-hosted deployment, subject to substantial infrastructure requirements [S6].'
role_fit:
  coordinator: { score: 3, reason: 'Very large context and output, cheap inference and harness subagents help, but broad independent capability trails the leading closed models', sources: [S1, S2, S3] }
  executor:    { score: 4, reason: 'Low price plus vendor-reported DeepSWE v1.1 77.0 and Terminal-Bench 4.0 42.3 suit cheap first-pass execution', sources: [S1, S3] }
  reviewer:    { score: 3, reason: 'Useful reasoning capacity, but weaker independent broad scores and no dedicated review calibration make it better as an executor under a stronger reviewer', sources: [S1, S8] }
---
## Strengths
- The 2026-10-17 update raises vendor-reported Terminal-Bench 4.0 from 31.2 to 42.3, DeepSWE v1.1 from 74.2 to 77.0, ProgramBench from 20.3 to 29.1, and Automation-Bench from 54.8 to 60.5 [S1] (confidence: high)
- Supports 1,048,576 context tokens and 393,216 max output tokens, which is large for a low-cost executor [S2] (confidence: high)
- Peak pricing is $0.30 input, $0.006 cache-hit input, and $1.20 output per MTok; off-peak rates are half those values [S3] (confidence: high)
- DeepSeek's official Claude Code integration supports the model as both main agent and subagent, and recommends a 786,432-token auto-compaction threshold for the 1M configuration [S4] (confidence: high)
- Open weights are published, which allows private deployment; the other four families profiled in this run are proprietary [S6] (confidence: high)
## Failure modes
- The API id is an unversioned moving alias: deepseek-flash now serves 1017 and previously served the September checkpoint | trigger: reproducibility tests pin only the API string | mitigation in prompt: record the provider-reported model version with every run; do not treat deepseek-flash as immutable [S1, S3]
- Generic effort names collapse silently: minimal maps to low, and medium and xhigh map to high | trigger: a vendor-neutral orchestrator assumes effort names mean the same thing across vendors | mitigation in prompt: map explicitly to none, low, high, or max and record the mapped level [S5]
- The default output allowance is much lower than the model maximum unless configured | trigger: the orchestrator assumes 393,216 output tokens are available automatically | mitigation in prompt: set max_tokens deliberately; documented defaults vary by thinking mode and effort [S5]
- Alias and compatibility layers can hide the real underlying model | trigger: using the retired deepseek-v4-flash names | mitigation in prompt: use deepseek-flash, then log the returned provider model version separately [S3]
## Code and test tendencies
- No measured code-shape or test data for this family in either lean-code report (2026-10-27); the generic lean rules apply unmodified (researched 2026-10-27 from the lean-code reports, not human-verified) [S10]
## Prompting rules
- Put stable role and policy constraints in the system message; DeepSeek's OpenAI-format examples support a system message [S5]
- Map reasoning effort mechanically: none for non-thinking, low for inexpensive bounded tasks, high for normal complex work, max for the hardest coding-agent tasks [S5]
- Under Claude Code, set both the main model and the subagent model explicitly to deepseek-flash so Claude model-name defaults do not route to another DeepSeek tier [S4]
- Set auto-compaction before the full 1M context is exhausted; DeepSeek's own Claude Code setup recommends 786,432 tokens [S4]
- Treat unsupported or compatibility-mapped API parameters as an integration test requirement; do not assume OpenAI or Anthropic API compatibility is exact [S5]
- No family-specific lean rule exists: keep the project's `## Lean changes and tests` block and require the `## Added` inventory in the summary [S10]
## Change from previous version
- improved: Terminal-Bench 4.0 vendor-reported result rose 11.1 points, from 31.2 to 42.3 [S1]
- improved: DeepSWE v1.1 rose from 74.2 to 77.0 [S1]
- improved: Automation-Bench 1.0.6 rose from 54.8 to 60.5 [S1]
- improved: DeepSeek reports shorter output and runtime alongside the capability gains [S1]
- unchanged: API calling method and price; the id is still deepseek-flash at the same rates [S1]
- changed: because the API alias did not change, applications that did not record checkpoint identity received a model change without changing their configured model string [S1]
## Open questions
- Exact provider-side API request and response retention default, and an enterprise zero-data-retention contract comparable to OpenAI, Anthropic, Google, or xAI: unknown.
- Reviewer-specific false-positive and false-negative calibration: unknown.
- This family was profiled only in the ChatGPT run; the Claude run did not cover DeepSeek. The ChatGPT run itself said Meta Muse displaces DeepSeek at the frontier when frontier means broad capability rather than open weights or price: Artificial Analysis-derived Intelligence Index scores (index version not stated) put Muse Wonder at 52.4 and Muse Wonder Full at 55.8 versus DeepSeek V4.1 Flash-1017 at 45.1, and LMArena Text places Muse Wonder second at 1509 while a current LMArena roundup places DeepSeek V4.1 Flash around #38/1475 [S8, S9]. The run kept DeepSeek only because its roster input was missing.
## Sources
- S1: DeepSeek Change Log: V4.1-Flash-1017 Update, DeepSeek, 2026-10-17, https://api-docs.deepseek.com/updates/, primary (chatgpt run)
- S2: List Models, DeepSeek API Docs, accessed 2026-10-20, https://api-docs.deepseek.com/api/list-models/, primary (chatgpt run)
- S3: Models & Pricing, DeepSeek, accessed 2026-10-20, https://api-docs.deepseek.com/quick_start/pricing/, primary (chatgpt run)
- S4: Integrate with Claude Code, DeepSeek, accessed 2026-10-20, https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/, primary (chatgpt run)
- S5: Chat Completions API, DeepSeek, accessed 2026-10-20, https://api-docs.deepseek.com/api/create-chat-completion/, primary (chatgpt run)
- S6: DeepSeek-V4.1-Flash: Smarter, Faster, More Efficient, DeepSeek, 2026-09-10, https://api-docs.deepseek.com/news/news260910/, primary (chatgpt run)
- S7: source not listed in ChatGPT report (cited as S44) (chatgpt run)
- S8: source not listed in ChatGPT report (cited as S45) (chatgpt run)
- S9: source not listed in ChatGPT report (cited as S46) (chatgpt run)
- S10: Lean LLM-written code and tests: what the evidence supports for specy-road, in-repo research reports (two runs), 2026-10-27, no measured code-shape or test data for this family, research (lean-code reports)
