---
profile_schema: 2
family: DeepSeek
track: Flash
model: DeepSeek-V4.1-Flash
api_id: deepseek-flash
checkpoint: V4.1-Flash-20260910
alias_moves: 'yes'
version_rank: previous
release_date: 2026-09-10
researched: 2026-10-20
researcher: chatgpt
supersedes: none
access:
  context_tokens: 1048576
  output_tokens: 393216
  cli: none
  cli_verified_from: unverified
  subagents: 'yes The historical checkpoint worked through the documented Claude Code integration, but the public alias now resolves to 1017 [S3]'
  effort_controls: 'none, low, high, max'
  effort_map: { minimal: low, low: low, medium: high, high: high, max: max }
cost_usd_per_mtok: { input: 0.30, output: 1.20, cached_input: 0.006, fast_input: unknown, fast_output: unknown }
data_handling: Open weights permit self-hosted or private deployment [S5]. Current provider-side API retention and zero-data-retention terms are unknown from the reviewed primary material. This checkpoint is no longer directly selectable through the unversioned deepseek-flash API alias [S1].
role_fit:
  coordinator: { score: 3, reason: 'Large context and inexpensive agent integration help, but the checkpoint is now operationally historical and weaker than 1017', sources: [S1, S5] }
  executor:    { score: 3, reason: 'Vendor-reported DeepSWE 74.2 was strong for the price, but 1017 improves on it and the old checkpoint cannot be reliably selected through the current alias', sources: [S1] }
  reviewer:    { score: 2, reason: 'No dedicated review calibration found and the checkpoint is weaker than the current one', sources: [S1] }
---
## Strengths
- At release it reported DeepSWE v1.1 74.2, Terminal-Bench 4.0 31.2, ProgramBench 20.3, and Automation-Bench 54.8 under the vendor's documented evaluation setups [S1] (confidence: high)
- Uses a 552B-parameter MoE architecture with only a fraction of parameters active per token, released with open weights [S5] (confidence: high)
- Peak and off-peak pricing made it much cheaper than the major proprietary frontier models [S2] (confidence: high)
## Failure modes
- This checkpoint cannot be requested reproducibly through today's deepseek-flash alias | trigger: regression testing against the September version | mitigation in prompt: use a self-hosted pinned open-weight checkpoint; do not use the mutable hosted alias for historical A/B tests [S1, S5]
- Generic effort-name mismatch can change the intended reasoning level | trigger: sending medium or xhigh from a vendor-neutral enum | mitigation in prompt: normalize to DeepSeek's none, low, high, or max levels [S4]
- Lower long-horizon coding results than 1017 | trigger: complex terminal or repository tasks | mitigation in prompt: use 1017 unless historical reproducibility requires this checkpoint [S1]
## Code and test tendencies
- No measured code-shape or test data for this family in either lean-code report (2026-10-27); the generic lean rules apply unmodified (researched 2026-10-27 from the lean-code reports, not human-verified) [S8]
## Prompting rules
- Select the reasoning level explicitly; do not rely on effort names meaning the same thing across vendors [S4]
- Put hard constraints in the system message and the concrete task in the user message [S4]
- Under Claude Code, set the DeepSeek base URL, model, and subagent variables explicitly [S3]
- For historical evaluation, pin the open-weight artifact, not the hosted deepseek-flash alias [S1, S5]
- No family-specific lean rule exists: keep the project's `## Lean changes and tests` block and require the `## Added` inventory in the summary [S8]
## Change from previous version
- improved: introduced the V4.1 architecture with native visual understanding and much lower KV-cache requirements than the prior generation [S5]
- improved: lower API pricing at launch [S5]
- changed: the retired V4 Flash and V4 Flash Vision Exp aliases were temporarily routed to the new V4.1 Flash service [S1]
- regressed: relative to the later 1017 checkpoint, materially lower Terminal-Bench 4.0, DeepSWE v1.1, ProgramBench, and Automation-Bench results [S1]
## Open questions
- A stable hosted identifier for this exact 2026-09-10 checkpoint: unknown; deepseek-flash resolved to the 2026-10-17 checkpoint on the research date [S1, S2].
- Current provider retention and zero-data-retention guarantees: unknown.
- This family was profiled only in the ChatGPT run; the Claude run did not cover DeepSeek. The ChatGPT run itself said Meta Muse displaces DeepSeek at the frontier when frontier means broad capability rather than open weights or price: Artificial Analysis-derived Intelligence Index scores (index version not stated) put Muse Wonder at 52.4 and Muse Wonder Full at 55.8 versus DeepSeek V4.1 Flash-1017 at 45.1, and LMArena Text places Muse Wonder second at 1509 while a current LMArena roundup places DeepSeek V4.1 Flash around #38/1475 [S6, S7]. The run kept DeepSeek only because its roster input was missing.
## Sources
- S1: DeepSeek Change Log, DeepSeek, 2026-09-10 and 2026-10-17, https://api-docs.deepseek.com/updates/, primary (chatgpt run)
- S2: Models & Pricing, DeepSeek, accessed 2026-10-20, https://api-docs.deepseek.com/quick_start/pricing/, primary (chatgpt run)
- S3: Claude Code integration, DeepSeek, accessed 2026-10-20, https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/, primary (chatgpt run)
- S4: Chat Completions API, DeepSeek, accessed 2026-10-20, https://api-docs.deepseek.com/api/create-chat-completion/, primary (chatgpt run)
- S5: DeepSeek-V4.1-Flash: Smarter, Faster, More Efficient, DeepSeek, 2026-09-10, https://api-docs.deepseek.com/news/news260910/, primary (chatgpt run)
- S6: source not listed in ChatGPT report (cited as S45) (chatgpt run)
- S7: source not listed in ChatGPT report (cited as S46) (chatgpt run)
- S8: Lean LLM-written code and tests: what the evidence supports for specy-road, in-repo research reports (two runs), 2026-10-27, no measured code-shape or test data for this family, research (lean-code reports)
