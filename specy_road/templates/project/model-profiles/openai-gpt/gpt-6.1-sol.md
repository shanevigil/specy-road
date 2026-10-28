---
profile_schema: 2
family: OpenAI GPT
track: Sol
model: GPT-6.1 Sol
api_id: gpt-6.1-sol
checkpoint: same-as-api_id
alias_moves: 'no'
version_rank: latest
release_date: 2026-09-29
researched: 2026-10-20
researcher: merged
supersedes: gpt-6-sol
access:
  context_tokens: 1050000
  output_tokens: 128000
  cli: codex exec --model gpt-6.1-sol --sandbox workspace-write --ask-for-approval never "<prompt>"
  cli_verified_from: unverified
  subagents: 'yes Native multi-agent orchestration in the Responses API is in beta, per OpenAI''s API changelog and a third-party report; Codex also supplies an agent harness [S9, S3, S10]'
  effort_controls: 'low, medium, high, xhigh, max (default medium; none and minimal rejected)'
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 2.00, output: 10.00, cached_input: 0.10, fast_input: 12.00, fast_output: 60.00 }
data_handling: 'Served by the OpenAI API (Responses, Chat Completions without tools, Batch) and in ChatGPT Work and Codex for Plus, Pro, Business, Enterprise and Edu [S1, S3]. API data is not used to train OpenAI models by default; standard abuse-monitoring logs may be retained for up to 30 days; approved customers can obtain zero data retention; eligible API usage supports US and EU data residency [S11]. No local deployment.'
role_fit:
  coordinator: { score: 4, reason: 'Both runs rate it 4 - vendor positions it near GPT-6 Astra on agentic coding at one-fifth of Astra''s price and it has native beta delegation, but independent standing trails Opus 5.5 (AA index 52 vs 58 in one aggregator; also behind Opus 5.5 and Gemini 4 Argon on independent coding results)', sources: [S1, S6, S9, S13] }
  executor:    { score: 5, reason: '(claude 4, chatgpt 5) Vendor builds it for complex refactors and long-running agents at a low price; the Claude run found no independent agentic numbers, while the ChatGPT run found Terminal-Bench 4.0 at 55.05 percent for $1.72 per test and a 6.4-point DeepSWE v1.1 gain over GPT-6 Sol, so the higher score rests on stronger evidence', sources: [S1, S3, S13] }
  reviewer:    { score: 4, reason: 'Both runs rate it 4 - different vendor and training data from Claude models, which is the main value in a cross-review pair, plus improved restriction-following and tool-failure disclosure; direct code-review calibration evidence is limited', sources: [S1] }
---
## Strengths
- Vendor claims near-Astra performance on agentic coding, computer use and professional work at one-fifth of Astra's token price [S1] (confidence: medium)
- Long-horizon coding improved over GPT-6 Sol: OpenAI reports a 6.4 percentage-point best-score gain on DeepSWE v1.1 at a lower reasoning setting and cost [S1] (confidence: high)
- Terminal-Bench 4.0 (Vals AI, updated 2026-10-18): 55.05 percent at $1.72 per test in a Mini-SWE-agent run; another current leaderboard run reported about 56 to 58 percent depending on harness and evaluation setup [S13] (confidence: high)
- OpenAI reports a seven-point improvement over GPT-6 Sol on the OSWorld 2.0 offline set at maximum effort [S1] (confidence: high)
- On OpenAI's adversarial broken-search evaluation, failure to disclose the broken tool fell from 4.9 percent (GPT-6 Sol) to 2.1 percent at maximum effort [S1] (confidence: high)
- Native multi-agent delegation in the Responses API is available in beta [S9, S3] (confidence: high)
- Cached input at $0.10, a 95 percent discount on standard input [S1] (confidence: high)
- Reasoning effort can change mid-conversation via configuration_update items without breaking the cache [S2] (confidence: high)
## Failure modes
- May continue after a failed information or tool path without disclosing the problem | trigger: broken or unavailable tool during an agentic task | mitigation in prompt: "If a required tool fails or its output cannot be verified, stop that branch, report the failure explicitly, and do not substitute guessed results." [S1]
- Native multi-agent operation can add unnecessary delegation cost and complexity | trigger: broad prompts that do not state when delegation is permitted | mitigation in prompt: "Delegate only when subtasks are independent and materially benefit from parallelism; otherwise work directly. Never delegate merely to re-check completed work." [S9]
- Harness state, compaction, retained reasoning and tool implementation affect agent scores; a long context window is not reliable working memory | trigger: long-lived sessions with repeated tool calls | mitigation in prompt: preserve relevant state and compact deliberately in the harness rather than relying on the raw context limit [S10]
## Code and test tendencies
- GPT-5.x High was the most verbose model in Sonar's December 2025 leaderboard data (974,379 LOC on the same Java task set vs Gemini 3 Pro ~289,752); vendor benchmark, single-file Java, directional only (researched 2026-10-27 from the lean-code reports, not human-verified) [S14]
- Codex PRs reverted least in the field: 6.1 percent vs 11.5 percent human (OR 0.50), median 63 changed lines (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S15]
- OpenAI's Codex guidance says to search for prior art and reuse or extract a shared helper before adding new helpers or logic, and warns against speculative changes, broad catches and silent defaults (read 2026-10-27; researched 2026-10-27 from the lean-code reports, not human-verified) [S16]
## Prompting rules
- Use the Responses API for any tool calling; Chat Completions does not support tools for this model [S2]
- Never send reasoning effort none or minimal; use low [S2]
- Keep request-level reasoning.effort fixed and change effort with configuration_update items to preserve the prompt prefix cache [S2]
- Start at the default medium effort; raise toward high, xhigh or max only when acceptance criteria or evals justify the extra cost [S2, S4, S8]
- State the requested edit, allowed scope, completion criteria, test policy and stop conditions explicitly; do not rely on the model to infer repository boundaries [S1]
- For reviewer and executor separation, state: "Do not modify tests merely to make existing behavior pass; change tests only when the requested behavior itself changes, and explain each such change." [S1]
- Bound multi-agent use: name which work may be delegated, the maximum useful fan-out, and which agent keeps responsibility for final integration [S9]
- Use codex exec for headless CI and background runs, and set sandbox and approval policy in the harness rather than only in natural-language prohibitions [S10]
- Treat prompt instructions as a complement to enforcement: keep sandboxing, action allowlists, execution limits and approval controls outside the model [S10]
- Require a prior-art search before any new helper and a named reuse in the summary, and fix the output format; this family writes the most code per task but its merged work holds up [S14, S16]
## Change from previous version
- improved: cached input $0.20 to $0.10; standard input and output stay $2/$10 [S1, S3, S8, S12]
- improved: DeepSWE v1.1 best score up 6.4 points versus GPT-6 Sol [S1]
- improved: OSWorld 2.0 offline score up seven points at maximum effort [S1]
- improved: broken-search disclosure and compliance on explicit-restriction and unauthorized-action evaluations [S1]
- improved: native Responses API multi-agent support added in beta [S9]
- improved: system card addendum published (GPT-6 Sol had none), per third-party report [S5]
- regressed: none and minimal effort removed; tool calling no longer allowed in Chat Completions [S2]
- unchanged: context and output ceilings remain about 1.05M and 128K [S8, S12]
## Open questions
- Watch out — reports differ: reasoning effort levels. Claude run: low, medium, high, xhigh, max; none and minimal are rejected [S2]. ChatGPT run: none, low, medium, high, xhigh, max, with all six exposed by the model [S8].
- Watch out — reports differ: headless CLI invocation. Claude run: codex exec -m gpt-6.1-sol "<prompt>", from third-party guides only; OpenAI's Codex docs were not read [S4]. ChatGPT run: codex exec --model gpt-6.1-sol --sandbox workspace-write --ask-for-approval never "<prompt>", alongside OpenAI's Codex execution documentation [S10]. Neither run states the syntax was copied from a vendor page.
- Watch out — reports differ: executor role_fit score. Claude run: 4, independent agentic numbers not found [S1, S3]. ChatGPT run: 5, DeepSWE v1.1 gain and Terminal-Bench 4.0 capability per dollar [S1, S13].
- Ultrafast tier: the OpenAI API changelog confirms "Ultrafast mode for GPT-6.1 Sol in the Responses API" via service_tier "ultrafast", "available to all API users, subject to rate limits", and OpenAI's DevDay community post prices it at $12 input and $60 output per million tokens [S7]; the fast prices above come from that post. (claude run)
- Independent evidence for approve/block calibration, scope-creep detection and deliberate test-weakening detection is insufficient; coding and agent benchmarks do not substitute for a review benchmark [S13]. (chatgpt run)
- Fixed per-model public rate limits and the vendor incident history for the preceding 90 days are unknown. (chatgpt run)
## Sources
- S1: Introducing GPT-6.1 Sol, OpenAI, 2026-09-29, https://openai.com/index/introducing-gpt-6-1-sol/, primary; Claude run saw a search snippet only, page blocked (both runs)
- S2: Using GPT-6, OpenAI, accessed 2026-10-26, https://developers.openai.com/api/docs/guides/latest-model, primary (claude run)
- S3: GPT-6.1 Sol: Specs, Benchmarks, Pricing and Task Costs, Kingy AI, 2026-10, https://kingy.ai/blog/gpt-6-1-sol-specs-benchmarks-pricing-task-costs/, independent (claude run)
- S4: GPT-6.1 Sol for Coding Agents, aq.dev, 2026-10, https://aq.dev/guides/gpt-6-1-sol-for-coding-agents/, independent (claude run)
- S5: Model Drop: GPT-6.1 Sol, Handy AI, 2026-09-29, https://handyai.substack.com/p/model-drop-gpt-61-sol, independent (claude run)
- S6: Which AI is best right now? Daily AI Leaderboard, collectivebrain, 2026-10-23, https://collectivebrain.de/en/ai-leaderboard/, independent (claude run)
- S7: OpenAI API changelog and DevDay community post, OpenAI, 2026-10, developers.openai.com (exact page URL not verified; quoted via enrichment pass), primary (claude run)
- S8: GPT-6.1 Sol model documentation, OpenAI, accessed 2026-10-20, https://developers.openai.com/api/docs/models/gpt-6-1-sol, primary (chatgpt run)
- S9: OpenAI API Changelog - GPT-6.1 Sol, OpenAI, 2026-09-29, https://developers.openai.com/api/docs/changelog, primary (chatgpt run)
- S10: Codex as a platform and Codex execution documentation, OpenAI, 2026-08-19 (accessed 2026-10-20), https://developers.openai.com/blog/codex-as-a-platform, primary (chatgpt run)
- S11: API data controls and Zero Data Retention documentation, OpenAI, accessed 2026-10-20, https://platform.openai.com/docs/guides/your-data, primary (chatgpt run)
- S12: GPT-6 Sol model documentation, OpenAI, accessed 2026-10-20, https://developers.openai.com/api/docs/models/gpt-6-sol, primary (chatgpt run)
- S13: Terminal-Bench 4.0, Vals AI, updated 2026-10-18, https://www.vals.ai/benchmarks/terminal-bench-4, independent (chatgpt run)
- S14: New data on code quality: GPT-5.2 high, Opus 4.5, Gemini 3, and more, Sonar, 2025-12, https://www.sonarsource.com/blog/new-data-on-code-quality-gpt-5-2-high-opus-4-5-gemini-3-and-more/, vendor benchmark on Java single-file tasks (lean-code reports)
- S15: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S16: Codex best practices (search for prior art before adding helpers), OpenAI, accessed 2026-10-27, https://developers.openai.com/codex/learn/best-practices, primary (lean-code reports)
