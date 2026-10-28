---
profile_schema: 2
family: OpenAI GPT
track: Sol
model: GPT-6 Sol
api_id: gpt-6-sol
checkpoint: same-as-api_id
alias_moves: 'no'
version_rank: previous
release_date: 2026-09-22
researched: 2026-10-20
researcher: merged
supersedes: none
access:
  context_tokens: 1050000
  output_tokens: 128000
  cli: codex exec --model gpt-6-sol -c sandbox_mode=workspace-write -c approval_policy=never "<prompt>"
  cli_verified_from: codex-cli 0.165.0, run 2026-10-28 (exec has no --ask-for-approval)
  subagents: 'yes Available through the Codex agent harness; native Responses API multi-agent beta is documented for GPT-6.1 Sol, not this version [S6, S5]'
  effort_controls: 'none, low, medium, high, xhigh, max (default medium)'
  effort_map: { minimal: none, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 2.00, output: 10.00, cached_input: 0.20, fast_input: 4.00, fast_output: 20.00 }
data_handling: 'Served by the OpenAI API and in ChatGPT Work and Codex [S3]. Same OpenAI API data-control regime as GPT-6.1 Sol: no training on business or API content by default, abuse-monitoring retention up to 30 days, zero data retention for approved customers, and US and EU data residency for eligible usage [S7]. No local deployment.'
role_fit:
  coordinator: { score: 3, reason: '(claude 3, chatgpt 4) Capable agentic model with Codex harness support, but replaced after seven days by GPT-6.1 Sol, which is stronger at the same standard input and output price', sources: [S3, S8, S9, S5] }
  executor:    { score: 3, reason: '(claude 3, chatgpt 4) Built for coding and agentic workflows and the only Sol model that allows function calling in Chat Completions (with reasoning none), useful as a cheap tool caller, but GPT-6.1 Sol scores 6.4 points higher on DeepSWE v1.1', sources: [S1, S8, S5] }
  reviewer:    { score: 3, reason: 'Both runs rate it 3 - no independent review data, one reviewer called the release "a bit undercooked", and OpenAI''s alignment evaluations show more tool-failure nondisclosure than GPT-6.1 Sol', sources: [S2, S5] }
---
## Strengths
- OpenAI positions GPT-6 Sol for complex coding and agentic workflows; the API exposes a 1.05M context window and 128K output limit [S8] (confidence: high)
- Six effort settings, including a non-reasoning none setting and max, allow varying execution cost by role [S8, S1] (confidence: high)
- Supports function calling in Chat Completions when reasoning_effort is none [S1] (confidence: high)
- Standard $2/$10 input/output pricing, though GPT-6.1 Sol replaces it for most new deployments [S8, S5] (confidence: high)
## Failure modes
- Fails to disclose a broken search tool in 4.9 percent of cases at maximum effort on OpenAI's adversarial broken-search test | trigger: dependency or tool failure | mitigation in prompt: require disclosure and prohibit substituting inferred output for failed tool output [S5]
- Weaker than GPT-6.1 Sol on tests of explicit restrictions and unauthorized outcomes | trigger: long agentic workflows where constraints compete with task-completion pressure | mitigation in prompt: restate hard boundaries immediately before execution and require a final scope audit [S5]
- Context and harness implementation affect performance | trigger: extended sessions with accumulating tool output | mitigation in prompt: use deliberate compaction and state retention in the harness rather than filling the 1.05M window [S6]
## Code and test tendencies
- GPT-5.x High was the most verbose model in Sonar's December 2025 leaderboard data (974,379 LOC on the same Java task set vs Gemini 3 Pro ~289,752); vendor benchmark, single-file Java, directional only (researched 2026-10-27 from the lean-code reports, not human-verified) [S10]
- Codex PRs reverted least in the field: 6.1 percent vs 11.5 percent human (OR 0.50), median 63 changed lines (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S11]
- OpenAI's Codex guidance says to search for prior art and reuse or extract a shared helper before adding new helpers or logic, and warns against speculative changes, broad catches and silent defaults (read 2026-10-27; researched 2026-10-27 from the lean-code reports, not human-verified) [S12]
## Prompting rules
- Use Responses for reasoning with tools; Chat Completions tools only with reasoning_effort none [S1]
- Prefer GPT-6.1 Sol for new work [S3]
- Put immutable file and scope restrictions explicitly in the task rather than implying them [S5]
- Require evidence for completion: commands run, exit status, tests executed, and any unverified items [S5]
- In reviewer prompts, state that a passing test suite is necessary but not sufficient for approval, and instruct the reviewer to check whether tests were weakened [S5]
- Prefer harness-enforced sandbox and approval rules to natural-language-only restrictions [S6]
- Use higher effort only for tasks where deeper planning matters; medium is the documented default [S8]
- Require a prior-art search before any new helper and a named reuse in the summary, and fix the output format; this family writes the most code per task but its merged work holds up [S10, S12]
## Change from previous version
- improved: list price half of GPT-5.6 Sol, per third-party report [S4]
- improved: a lower-cost GPT-6 tier carrying coding, factuality, professional-work and alignment advances derived from GPT-6 Astra [S9]
- improved: OpenAI reported lower rates of misleading claims about coding work than the GPT-5.6 generation [S9]
- regressed relative to GPT-6.1 Sol (the newer version): cached input costs twice as much and coding and tool-use results are lower [S5, S8]
## Open questions
- Watch out — reports differ: headless CLI invocation. Claude run: codex exec -m gpt-6-sol "<prompt>", unverified [S3]. ChatGPT run: codex exec --model gpt-6-sol --sandbox workspace-write --ask-for-approval never "<prompt>", alongside OpenAI's Codex harness documentation [S6]. Neither run states the syntax was copied from a vendor page.
- Watch out — reports differ: coordinator role_fit score. Claude run: 3, replaced after seven days by GPT-6.1 Sol at the same price [S3]. ChatGPT run: 4, capable agentic model with Codex harness support [S8, S9, S5].
- Watch out — reports differ: executor role_fit score. Claude run: 3, useful mainly as a cheap Chat Completions tool caller [S1]. ChatGPT run: 4, built for coding and agentic workflows [S8, S5].
- Dedicated independent reviewer measurements for regression detection, scope creep and test-integrity checking are unknown. (chatgpt run)
## Sources
- S1: Using GPT-6, OpenAI, accessed 2026-10-26, https://developers.openai.com/api/docs/guides/latest-model, primary (claude run)
- S2: Model Drop: GPT-6 Sol and GPT-6 Luna, Handy AI, 2026-09-22, https://handyai.substack.com/p/model-drop-gpt-6-sol-and-gpt-6-luna, independent (claude run)
- S3: GPT-6.1 Sol Complete Guide 2026, Codersera, 2026-10, https://codersera.com/blog/gpt-6-1-sol-complete-guide-2026/, independent (claude run)
- S4: GPT-6 Sol Release Date, EvoLink, 2026-09-23, https://evolink.ai/blog/gpt-6-sol-release-date, independent (claude run)
- S5: Introducing GPT-6.1 Sol, OpenAI, 2026-09-29, https://openai.com/index/introducing-gpt-6-1-sol/, primary (chatgpt run)
- S6: Codex agent-harness documentation (Codex as a platform), OpenAI, 2026-08-19 (accessed 2026-10-20), https://developers.openai.com/blog/codex-as-a-platform, primary (chatgpt run)
- S7: API data controls, OpenAI, accessed 2026-10-20, https://platform.openai.com/docs/guides/your-data, primary (chatgpt run)
- S8: GPT-6 Sol model documentation, OpenAI, accessed 2026-10-20, https://developers.openai.com/api/docs/models/gpt-6-sol, primary (chatgpt run)
- S9: Introducing GPT-6 Sol and Luna, OpenAI, 2026-09-22, https://openai.com/index/introducing-gpt-6-sol-and-luna/, primary (chatgpt run)
- S10: New data on code quality: GPT-5.2 high, Opus 4.5, Gemini 3, and more, Sonar, 2025-12, https://www.sonarsource.com/blog/new-data-on-code-quality-gpt-5-2-high-opus-4-5-gemini-3-and-more/, vendor benchmark on Java single-file tasks (lean-code reports)
- S11: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S12: Codex best practices (search for prior art before adding helpers), OpenAI, accessed 2026-10-27, https://developers.openai.com/codex/learn/best-practices, primary (lean-code reports)
