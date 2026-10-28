---
profile_schema: 2
family: SpaceXAI Grok
track: none
model: Grok 4.6
api_id: grok-4.6
checkpoint: same-as-api_id
alias_moves: unknown
version_rank: previous
release_date: 2026-08-12
researched: 2026-10-20
researcher: merged
supersedes: none
access:
  context_tokens: 500000
  output_tokens: unknown
  cli: grok -p "<prompt>"
  cli_verified_from: S3
  subagents: 'yes Through Grok Build workflow orchestration (ChatGPT run, no source given); native model-level API fan-out unknown'
  effort_controls: 'low, medium, high (default), xhigh; reasoning cannot be disabled'
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: xhigh }
cost_usd_per_mtok: { input: 2.00, output: 6.00, cached_input: 0.50, fast_input: unknown, fast_output: unknown }
data_handling: 'Same xAI API terms as grok-4.7: about 30-day default retention, no training without permission, team-wide Zero Data Retention for eligible teams, and a US regional endpoint [S4, S5, S10]. Also reported on GitHub Copilot, Google''s Agent Platform and Microsoft Foundry [S6]. Proprietary; not available locally.'
role_fit:
  coordinator: { score: 3, reason: 'Usable agent model, AA index 61 at its August 2026 launch (tied with GPT-5.6 Sol), now substantially superseded by 4.7 in coding and long-horizon behavior', sources: [S2, S9, S8] }
  executor:    { score: 3, reason: 'CursorBench 4.0 High 40.4 percent, behind 4.7 and the leading models; vendor-reported gains over Grok 4.5 not independently verified', sources: [S8, S2] }
  reviewer:    { score: 3, reason: 'Neither run found reviewer-specific evidence; 4.7 improves verification', sources: [S2, S9] }
---
## Strengths
- 500K context and low/medium/high/xhigh reasoning effort [S11, S1] (confidence: high)
- Standard short-context API pricing: $2 input, $0.50 cached input and $6 output per MTok [S11] (confidence: high)
- Artificial Analysis Intelligence Index 61 at launch (August 2026 index version) [S2] (confidence: medium)
- CursorBench 4.0: 40.4 percent at High, respectable but no longer a frontier coding result [S8] (confidence: high)
## Failure modes
- Multi-turn state loss, as in the rest of the current xAI reasoning API family | trigger: dropping prior reasoning state between turns | mitigation in prompt: preserve the required reasoning and context records between turns [S7]
- Less reliable than 4.7 on long-horizon coding | trigger: extended autonomous tasks | mitigation in prompt: prefer 4.7 where available, or put 4.6 under a stronger independent reviewer [S9]
- Cache savings drop when history is rewritten | trigger: the context manager repeatedly edits earlier messages | mitigation in prompt: keep append-only stable prefixes [S7]
## Code and test tendencies
- No measured code-shape or test data for this family in either lean-code report (2026-10-27); the generic lean rules apply unmodified (researched 2026-10-27 from the lean-code reports, not human-verified) [S12]
## Prompting rules
- Use the Responses API [S7]
- Set reasoning effort explicitly on every request rather than relying on the high default [S7]
- Preserve reasoning state between turns [S7]
- Set a prompt_cache_key and keep cacheable prompt prefixes immutable [S7]
- For high-consequence long-horizon coding, require explicit verification of changed files and tests before declaring completion; 4.7's documented verification improvement suggests this guardrail matters more for 4.6 [S9]
- No family-specific lean rule exists: keep the project's `## Lean changes and tests` block and require the `## Added` inventory in the summary [S12]
## Change from previous version
- improved: added the xhigh reasoning level over Grok 4.5 [S1]
- improved: introduced for stronger long-running agent and interactive workflows than its predecessor [S11]
- improved: vendor reports gains over Grok 4.5 on CursorBench and Terminal-Bench; numbers not verified [S2]
- unchanged: price and 500K context [S6]
- changed: relative to the successor grok-4.7, CursorBench 4.0 is 40.4 percent vs 46.3 percent [S8]
- changed: relative to the successor grok-4.7, Terminal-Bench 4.0 is 20.3 percent vs 38.0 percent in the published comparison [S9]
## Open questions
- Watch out — reports differ: headless CLI. Claude run: grok -p "Your prompt here", verified from the vendor headless docs [S3]. ChatGPT run: grok -m grok-4.6 -p "<prompt>" --output-format json (no source cited for that syntax). The verified form does not select a model; the -m and --output-format flags are unverified.
- Watch out — reports differ: benchmark standing. Claude run: AA Intelligence Index 61 at launch (August 2026 index version), tied with GPT-5.6 Sol, with vendor-reported CursorBench and Terminal-Bench gains over 4.5 left unverified [S2]. ChatGPT run: CursorBench 4.0 High 40.4 percent, "no longer frontier", and Terminal-Bench 4.0 20.3 percent [S8, S9]. These are different indexes measured at different times.
- Cursor lists 256K context for its Grok 4.6 integration vs 500K on the xAI API [S6].
- Finite text-output ceiling: unknown.
- Dedicated independent code-review calibration: unknown.
## Sources
- S1: Reasoning, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/model-capabilities/text/reasoning, primary (claude run)
- S2: SpaceXAI releases Grok 4.6, 9to5Mac, 2026-08-12, https://9to5mac.com/2026/08/12/spacexai-releases-grok-4-6/, independent (claude run)
- S3: Headless and Scripting, SpaceXAI, 2026-06-10, https://docs.x.ai/build/cli/headless-scripting, primary (claude run)
- S4: FAQ - API Security, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/faq/security, primary (claude run)
- S5: Regional Endpoints, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/advanced-api-usage/regions, primary (claude run)
- S6: Grok 4.6: 500K xAI API vs. 256K Cursor Context, Kingy AI, 2026-08-12, https://kingy.ai/blog/grok-4-6-price-benchmarks-api-cursor-context-window/, independent (claude run)
- S7: Best Practices Guide, SpaceXAI, 2026-10 (accessed 2026-10-26), https://docs.x.ai/developers/model-capabilities/text/best-practices, primary (both runs)
- S8: CursorBench 4.0, Cursor, accessed 2026-10-20, https://cursor.com/cursorbench, independent (chatgpt run)
- S9: Grok 4.7 release comparison, xAI/Cursor, 2026-09-21, URL not listed, primary (chatgpt run)
- S10: xAI data-handling documentation, xAI, accessed 2026-10-20, https://docs.x.ai/, primary (chatgpt run)
- S11: Grok 4.6 release/model documentation, xAI, 2026-08-12, https://docs.x.ai/developers/release-notes, primary (chatgpt run)
- S12: Lean LLM-written code and tests: what the evidence supports for specy-road, in-repo research reports (two runs), 2026-10-27, no measured code-shape or test data for this family, research (lean-code reports)
