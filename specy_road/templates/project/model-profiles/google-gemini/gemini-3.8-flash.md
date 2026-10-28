---
profile_schema: 2
family: Google Gemini
track: Flash
model: Gemini 3.8 Flash
api_id: gemini-3.8-flash
checkpoint: same-as-api_id
alias_moves: unknown
version_rank: previous
release_date: 2026-09-02
researched: 2026-10-20
researcher: merged
supersedes: none
access:
  context_tokens: 1048576
  output_tokens: 65536
  cli: gemini -m gemini-3.8-flash -p "<prompt>" --output-format json
  cli_verified_from: unverified
  subagents: yes Default model for Google's Managed Agents and Antigravity generation and usable through Gemini agent tooling [S3]
  effort_controls: 'thinking_level low, medium, high; minimal is unsupported and returns an error'
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: high }
cost_usd_per_mtok: { input: 0.75, output: 3.75, cached_input: unknown, fast_input: unknown, fast_output: unknown }
data_handling: 'Google-hosted under the same paid Gemini API controls as Argon: paid-service content is not used for product improvement or training, eligible customers can use zero-retention or non-storage controls, some features keep their own retention, enterprise configurations offer residency options, and the proprietary weights cannot be deployed locally [S7]. Exact retention period: unknown.'
role_fit:
  coordinator: { score: 2, reason: 'Claude run found only fast-tier positioning; ChatGPT run cites the 1M window, Managed Agents integration and ninth place on LMArena Multi-turn but rates Argon materially stronger; neither run has coordination evidence (claude 2, chatgpt 4)', sources: [S1, S3, S9] }
  executor:    { score: 3, reason: 'Both runs describe it as aimed at long-running engineering and agent work; CursorBench 4.0 High 39.6 percent is below current frontier models, and the $0.75/$3.75 introductory price suits cheaper well-scoped passes (claude 3, chatgpt 4)', sources: [S1, S5, S3] }
  reviewer:    { score: 2, reason: 'Neither run found review data; ChatGPT run notes a lower coding score and advises putting a stronger independent model behind it (claude 2, chatgpt 3)', sources: [S1, S5, S9] }
---
## Strengths
- Documented features: 1,048,576 input-token context, 65,536 output tokens, low/medium/high thinking, tool calling, code execution, computer use (preview), file search and structured outputs [S3] (confidence: high)
- Introductory pricing through 2026-12-31 is $0.75 per MTok input and $3.75 per MTok output, which makes it a low-cost candidate for first-pass execution [S3] (confidence: high)
- Positioned for long-running engineering, long-horizon software engineering and autonomous agent tasks; the latest stable GA model before Argon [S1, S3] (confidence: low)
- LMArena Text: ninth at 1496; LMArena Multi-turn: ninth at 1503, data as of 2026-10-19 [S9] (confidence: medium)
- CursorBench 4.0: 39.6 percent at High [S5] (confidence: high)
## Failure modes
- minimal thinking is unsupported and returns an error | trigger: a generic orchestrator maps a "minimal" effort level to every vendor | mitigation in prompt: map the lowest neutral effort to low [S3]
- Deprecated Gemini sampling and prefill patterns cause invalid or ineffective requests | trigger: old Gemini configuration copied forward | mitigation in prompt: remove deprecated sampling parameters and prefilled model turns [S3]
- Peak-load 503 UNAVAILABLE errors and slowdowns on the Gemini 3.8 Flash High serving pool, acknowledged by Google, during reported 16:00 to 22:00 UTC periods in September 2026 | trigger: high concurrent demand | mitigation in prompt: in the orchestrator, retry idempotent operations with bounded exponential backoff and support model fallback [S8]
## Code and test tendencies
- Gemini 3 Pro was the most concise model in Sonar's December 2025 data (~289,752 LOC) but had the highest control-flow error rate (200 per MLOC); vendor benchmark, single-file Java, directional only (researched 2026-10-27 from the lean-code reports, not human-verified) [S11]
## Prompting rules
- Map effort only to low, medium or high; never send minimal [S3]
- Remove temperature, top_p, top_k, candidate_count and prefilled model-turn assumptions when migrating old Gemini prompts and integrations [S3]
- Use consistent XML or Markdown structure and state hard constraints explicitly [S6]
- Put large repository or context material before the final instruction in long-context prompts [S6]
- For cheap execution start at medium; raise to high only where the task's own evaluation shows improvement [S3]
- Conciseness is not the risk here: require a test that reaches every new branch and loop exit, and have the reviewer re-run the verifier rather than read the control flow [S11]
## Change from previous version
- changed: Google replaced Gemini 3.7 Flash with 3.8 Flash and routes the deprecated 3.7 stable endpoint to 3.8; a community report says 3.6 Flash is also being retired [S4, S2]
- improved: Google targets long-horizon software engineering and autonomous agent workflows with this version [S3]
- changed: relative to the successor gemini-4-argon, CursorBench 4.0 High is 39.6 percent vs 52.9 percent [S5]
- changed: relative to the successor gemini-4-argon, the introductory price is much lower ($0.75/$3.75 vs $2/$10) [S10, S3]
## Open questions
- Watch out — reports differ: headless CLI. Claude run: none, no syntax verified (no source cited). ChatGPT run: gemini -m gemini-3.8-flash -p "<prompt>" --output-format json (no source cited for that syntax; the Gemini CLI headless docs appear only in its Argon profile).
- Watch out — reports differ: coordinator score. Claude run: 2, from thin evidence and fast-tier positioning [S1]. ChatGPT run: 4, from the 1M window, Managed Agents integration and multi-turn preference results [S3, S9].
- Watch out — reports differ: executor score. Claude run: 3 [S1]. ChatGPT run: 4, from CursorBench 4.0 High 39.6 percent plus the introductory price [S5, S3].
- Watch out — reports differ: reviewer score. Claude run: 2 [S1]. ChatGPT run: 3 [S5, S9].
- Roster choice: the newest Pro-class id is gemini-3.1-pro-preview (2026-02-19), still preview and not GA, so the Claude run profiled Gemini 3.8 Flash as the most recent earlier GA release [S1]. The ChatGPT run also treats 3.8 Flash as the previous Gemini version. The Claude run did not read primary Google documentation for 3.8 Flash; the ChatGPT run did [S3].
- Cached-input price was not established from primary material: unknown.
- Google forum reports of specific tool-calling regressions were left out because the research rule requires two independent community reports before a failure mode counts as established.
## Sources
- S1: Google Gemini Model Lineage 2026, Presenc, 2026-10, https://presenc.ai/research/google-gemini-model-lineage-2026, independent (claude run)
- S2: Google Overhauls Gemini Lineup, NPowerUser, 2026-10, https://nokiapoweruser.com/google-gemini-model-deprecation-36-37-flash-fast-mode-gemini-4-argon/, community (claude run)
- S3: Gemini 3.8 Flash model and migration guide, Google, 2026-09, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, primary (chatgpt run)
- S4: Gemini API Release Notes, Google, 2026-09-02 to 2026-10-08, https://ai.google.dev/gemini-api/docs/changelog, primary (chatgpt run)
- S5: CursorBench 4.0, Cursor, accessed 2026-10-20, https://cursor.com/cursorbench, independent (chatgpt run)
- S6: Gemini prompting strategies, Google, accessed 2026-10-20, https://ai.google.dev/gemini-api/docs/prompting-strategies, primary (chatgpt run)
- S7: Gemini API data-use documentation, Google, accessed 2026-10-20, https://ai.google.dev/gemini-api/, primary (chatgpt run)
- S8: Gemini 3.8 Flash capacity incident discussion with Google response, Google AI Developers Forum, 2026-09-29, https://discuss.ai.google.dev/t/issue-report-severe-slowdowns-and-frequent-503-errors-on-gemini-flash-3-8-during-specific-hours-are-server-resources-being-intentionally-throttled/184984, community (chatgpt run)
- S9: LMArena Text/Multi-turn dataset, Arena data via BenchLeader, data 2026-10-19, https://www.benchleader.com/benchmarks/lmarena_text, independent (chatgpt run)
- S10: Gemini 4 Argon model documentation, Google, 2026-10-13, https://ai.google.dev/gemini-api/docs/models/gemini-4-argon, primary (chatgpt run)
- S11: New data on code quality: GPT-5.2 high, Opus 4.5, Gemini 3, and more, Sonar, 2025-12, https://www.sonarsource.com/blog/new-data-on-code-quality-gpt-5-2-high-opus-4-5-gemini-3-and-more/, vendor benchmark on Java single-file tasks (lean-code reports)
