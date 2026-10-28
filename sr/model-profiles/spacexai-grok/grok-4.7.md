---
profile_schema: 2
family: SpaceXAI Grok
track: none
model: Grok 4.7
api_id: grok-4.7
checkpoint: same-as-api_id
alias_moves: unknown
version_rank: latest
release_date: 2026-09-21
researched: 2026-10-20
researcher: merged
supersedes: grok-4.6
access:
  context_tokens: 500000
  output_tokens: unknown
  cli: grok -p "<prompt>"
  cli_verified_from: S3
  subagents: 'yes Through Grok Build workflows; the grok-4.7 API itself has no documented native multi-agent endpoint; headless sessions support --worktree [S2, S3]'
  effort_controls: 'low, medium, high (default), xhigh; reasoning cannot be disabled'
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: xhigh }
cost_usd_per_mtok: { input: 2.00, output: 6.00, cached_input: 0.50, fast_input: 4.00, fast_output: 12.00 }
data_handling: 'API requests and responses are stored encrypted for about 30 days by default for abuse auditing and are not used for training without explicit permission [S4, S11]. Zero Data Retention is set team-wide for eligible teams, disables stateful Responses, Files, Collections and Batch, and each response carries an x-zero-data-retention header [S4]. Grok Build documents ZDR-oriented code handling [S11]. The US endpoint https://us.api.x.ai/v1 guarantees US handling for grok-4.7 and grok-4.6 at a 10 percent token-price premium; the global endpoint may route between regions [S5, S2]. Proprietary; not available locally.'
role_fit:
  coordinator: { score: 3, reason: 'Both runs note the 500K context, smaller than 1M peers; ChatGPT run adds multi-turn design and Grok Build agent workflows but independent coding results trail Opus, Argon and Sol; no published orchestration evaluation (claude 3, chatgpt 4)', sources: [S2, S9] }
  executor:    { score: 4, reason: 'Default model of the Grok Build coding agent at $2/$6; CursorBench 4.0 46.3 percent at xhigh, up from 40.4 percent for Grok 4.6, credible but not the strongest', sources: [S2, S1, S9, S10] }
  reviewer:    { score: 3, reason: 'Vendor reports better self-checking and verification; neither run found independent reviewer calibration data', sources: [S1, S10, S9] }
---
## Strengths
- Lowest output price among the frontier general models in the Claude run's roster: $2 input / $6 output per MTok below 200K prompt tokens [S1, S7] (confidence: high)
- 500,000-token context, low/medium/high/xhigh reasoning, function calling, web and X search, and code execution [S2] (confidence: high)
- xAI documents no text output limit, with a 128,000-token default max_output_tokens [S2, S6] (confidence: high)
- CursorBench 4.0: 46.3 percent at Extra High, vs 40.4 percent for Grok 4.6 High in Cursor's comparison [S9] (confidence: high)
- Vendor says it "works longer on difficult tasks, checks its own work more carefully"; release notes describe a longer reinforcement-learning run weighted toward many-hour tasks and improved verification and long-context management [S1, S10] (confidence: low)
- Fast mode is the same model on faster infrastructure at 2x standard rates for prompts under 200K tokens, available in Cursor and Grok Build but not on the public xAI API [S2] (confidence: high)
## Failure modes
- Multi-turn quality and context continuity degrade when encrypted reasoning items are not returned | trigger: stateless Responses clients discard reasoning.encrypted_content | mitigation in prompt: pass encrypted reasoning back unchanged, or use previous_response_id with stored state [S6]
- Prompt-cache hit rate collapses when earlier messages are edited, removed or reordered | trigger: the orchestrator rewrites history every turn | mitigation in prompt: use a stable prompt_cache_key and append-only history [S6]
- Long-context requests cost much more | trigger: prompt reaches 200K tokens or more | mitigation in prompt: compact or summarize stable context instead of sending the whole repository history every turn [S10, S7]
## Code and test tendencies
- No measured code-shape or test data for this family in either lean-code report (2026-10-27); the generic lean rules apply unmodified (researched 2026-10-27 from the lean-code reports, not human-verified) [S12]
## Prompting rules
- Use the Responses API; xAI's best-practices guide recommends it over Chat Completions, which the Claude run reports as deprecated [S6]
- Send encrypted reasoning content back unchanged on every turn [S6]
- Set reasoning effort explicitly on every request and log it with results [S6]
- Use low or medium for bounded subtasks and high or xhigh for difficult long-horizon work; the default is high [S2]
- Set a stable prompt_cache_key per conversation and only append to the history [S6, S2]
- Use temperature 0.7 and top_p 0.95 [S6]
- Prefer streaming and allow at least 900 seconds per request, longer for long-running evals [S6]
- Keep prompts under 200K tokens where possible; above that the whole request bills at $4/$12 [S7]
- No family-specific lean rule exists: keep the project's `## Lean changes and tests` block and require the `## Added` inventory in the summary [S12]
## Change from previous version
- improved: CursorBench 4.0 from about 40.4 percent (Grok 4.6 High) to 46.3 percent (Grok 4.7 xhigh) [S9]
- improved: Terminal-Bench 4.0 from 20.3 percent to 38.0 percent in the published comparison [S10]
- improved: longer-horizon training, better self-checking, and long-context management improvements (vendor claims) [S1, S10]
- unchanged: price, 500K context and the four-level reasoning control [S7, S2]
- changed: Grok 4.7 always returns encrypted reasoning content on Responses, so state propagation is a harness contract [S2, S6]
## Open questions
- Watch out — reports differ: headless CLI. Claude run: grok -p "Your prompt here", verified from the vendor headless docs [S3]. ChatGPT run: grok -m grok-4.7 -p "<prompt>" --output-format json (no source cited for that syntax). The verified form does not select a model; the -m and --output-format flags are unverified.
- Watch out — reports differ: coordinator score. Claude run: 3 [S2]. ChatGPT run: 4 [S2, S9].
- Watch out — reports differ: role ranking. Claude run: 6th of seven as coordinator and reviewer, 4th as executor, ahead of Gemini 4 Argon [S2, S1]. ChatGPT run: 4th of five in all three roles, behind Argon [S9]. The rosters differ.
- Watch out — reports differ: independent evidence of improvement over 4.6. Claude run: vendor claims only, no independent numbers found [S1]. ChatGPT run: CursorBench 4.0 40.4 to 46.3 percent and Terminal-Bench 4.0 20.3 to 38.0 percent [S9, S10].
- Watch out — reports differ: what the $4/$12 rate covers. Claude run: the whole request bills at $4/$12 once the prompt exceeds 200K tokens [S7]. ChatGPT run: $4/$12 is the Fast-mode rate (2x standard) for prompts under 200K tokens, only in Cursor and Grok Build, and long-context prompts are separately "materially more expensive" [S2, S10]. Both runs put $4/$12 in fast_input/fast_output.
- Output limit: xAI says "no text output limit" with a 128,000-token default max_output_tokens [S2, S6]; AWS lists 524,288 minus input. Both runs leave output_tokens unknown.
- Capacity in the last 90 days: status.x.ai shows a Grok model outage on 2026-10-23/24 (about 40 minutes), degraded performance on api.x.ai on 2026-10-24, and a "Grok is experiencing issues" item on 2026-09-03; none names grok-4.7, and the feed was read only in part [S8].
- Independent reviewer evidence is not enough to say whether better self-verification means better approve/block calibration.
## Sources
- S1: SpaceXSI API: Grok Models, API Keys and Pricing, SpaceXAI, accessed 2026-10-26, https://x.ai/api, primary (claude run)
- S2: Grok 4.7 Developer Guide, SpaceXAI, updated 2026-10-10, https://docs.x.ai/developers/grok-4-7, primary (both runs)
- S3: Headless and Scripting, SpaceXAI, 2026-06-10, https://docs.x.ai/build/cli/headless-scripting, primary (claude run)
- S4: FAQ - API Security, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/faq/security, primary (claude run)
- S5: Regional Endpoints, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/advanced-api-usage/regions, primary (claude run)
- S6: Best Practices Guide, SpaceXAI, 2026-10 (accessed 2026-10-26), https://docs.x.ai/developers/model-capabilities/text/best-practices, primary (both runs)
- S7: Grok API Pricing in 2026, mem0, 2026-09, https://mem0.ai/blog/xai-grok-api-pricing, independent (claude run)
- S8: SpaceXAI System Status feed, SpaceXAI, accessed 2026-10-27, https://status.x.ai/feed.xml, primary (claude run)
- S9: CursorBench 4.0, Cursor, accessed 2026-10-20, https://cursor.com/cursorbench, independent (chatgpt run)
- S10: xAI Release Notes / Grok 4.7 release, xAI/SpaceXAI, 2026-09-21, https://docs.x.ai/developers/release-notes, primary (chatgpt run)
- S11: xAI API privacy/data-handling documentation, xAI, accessed 2026-10-20, https://docs.x.ai/, primary (chatgpt run)
- S12: Lean LLM-written code and tests: what the evidence supports for specy-road, in-repo research reports (two runs), 2026-10-27, no measured code-shape or test data for this family, research (lean-code reports)
