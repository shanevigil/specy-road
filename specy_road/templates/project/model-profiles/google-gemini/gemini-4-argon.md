---
profile_schema: 2
family: Google Gemini
track: Argon (Gemini 4 frontier tier)
model: Gemini 4 Argon
api_id: gemini-4-argon
checkpoint: same-as-api_id
alias_moves: unknown
version_rank: latest
release_date: 2026-10-13
researched: 2026-10-20
researcher: merged
supersedes: gemini-3.8-flash
access:
  context_tokens: 1048576
  output_tokens: 65536
  cli: gemini -m gemini-4-argon -p "<prompt>" --output-format json
  cli_verified_from: unverified
  subagents: 'yes Antigravity supports multi-agent orchestration with Argon for Google AI Ultra subscribers; Managed Agents in the Gemini API accept the model; Gemini CLI delegates to subagents whose model is configured separately [S2, S12]'
  effort_controls: 'thinking_level low, medium, high (default medium)'
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: high }
cost_usd_per_mtok: { input: 2.00, output: 10.00, cached_input: 0.10, fast_input: unknown, fast_output: unknown }
data_handling: 'Paid Gemini API tier only; also on Google Cloud (Gemini Enterprise Agent Platform, global location) [S1, S4]. Under the paid-service terms, API content is not used to improve Google products; eligible customers can use zero-retention controls such as non-stored interactions, but some grounding and tool features keep their own retention; data-residency controls exist in enterprise and Vertex configurations [S14]. Weights are not released and the model cannot be deployed locally [S3, S14]. A separate id, gemini-4-argon-cyber-permissive, serves vetted defenders in the Fairwind Program [S4]. Exact retention period: unknown.'
role_fit:
  coordinator: { score: 4, reason: 'Both runs cite the 1M window; ChatGPT run adds first place on LMArena Text and Multi-turn plus CursorBench 4.0 52.9 percent and Google agent tooling; Claude run cites AA index 53 below Opus 5.5 (claude 4, chatgpt 5)', sources: [S1, S5, S11, S15] }
  executor:    { score: 5, reason: 'Independent CursorBench 4.0 52.9 percent and Terminal-Bench 4.0 57.58 percent (chatgpt) are stronger evidence than the vendor-only DeepSWE v1.1 77.9 percent (claude); long decode allows outputs past 64K tokens (claude 4, chatgpt 5)', sources: [S11, S10, S7, S1] }
  reviewer:    { score: 3, reason: 'Neither run found a published review evaluation; strong instruction-following and coding scores and a vendor different from Anthropic and OpenAI favor it as a second reviewer (claude 3, chatgpt 4)', sources: [S1, S11, S15] }
---
## Strengths
- Unified 1,048,576-token input-output window; long decode up to 1M tokens minus input via background execution, while ordinary synchronous output is handled more conservatively [S1, S8] (confidence: high)
- CursorBench 4.0: 52.9 percent at High and 52.8 percent at Medium; the small gap suggests Medium is an efficient default for many coding tasks [S11] (confidence: high)
- Terminal-Bench 4.0: 57.58 percent in an independent Mini-SWE-agent evaluation [S10] (confidence: high)
- LMArena Text: first at 1524 (Argon High); LMArena Multi-turn: first at 1552, data as of 2026-10-19 [S15] (confidence: high)
- Artificial Analysis Intelligence Index 53 in one aggregator, below Opus 5.5 [S5] (confidence: medium)
- Google DeepMind's model card lists DeepSWE v1.1 at 77.9 percent and CWE-bench v1 at 68.0 percent, the same CWE-bench score as GPT-6 Astra (vendor-reported) [S7] (confidence: low)
- Coding and agent interfaces are built in, with tunable low, medium and high thinking [S8] (confidence: high)
## Failure modes
- Truncated answers when thinking consumes the budget | trigger: max_output_tokens set too low; thinking and output share the limit | mitigation in prompt: set max_output_tokens high enough for thinking plus answer [S1]
- Very long output exceeds ordinary synchronous generation | trigger: asking for tens or hundreds of thousands of output tokens in one ordinary request | mitigation in prompt: use the documented background or long-running mechanism with continuation or state ids instead of one synchronous response [S1]
- Legacy Gemini sampling controls are ignored or unsupported | trigger: carrying temperature, top_p, top_k, candidate_count or prefilled assistant turns into newer Gemini APIs | mitigation in prompt: remove deprecated controls and use thinking_level plus supported server-side interaction state [S1]
- Subagents may not inherit the coordinator's model | trigger: assuming every delegated Gemini CLI agent runs Argon | mitigation in prompt: set and verify each subagent's model explicitly when model identity matters to the evaluation [S12]
## Code and test tendencies
- Gemini 3 Pro was the most concise model in Sonar's December 2025 data (~289,752 LOC) but had the highest control-flow error rate (200 per MLOC); vendor benchmark, single-file Java, directional only (researched 2026-10-27 from the lean-code reports, not human-verified) [S16]
## Prompting rules
- Start at thinking_level medium for ordinary agentic coding; use high for hard math, science and coding, or when your own task evals show a gain [S1, S8, S11]
- Set max_output_tokens high enough to cover thinking plus the answer [S1]
- For outputs over 65,536 tokens use background execution and join all model_output steps [S1]
- Remove temperature, top_p, top_k, candidate_count and prefilled assistant turns carried over from older Gemini configurations [S1]
- Preserve conversation state with the documented interaction ids instead of reconstructing assistant history where the API disallows it [S1]
- Use one structural convention, XML tags or Markdown sections, to separate role, data, constraints, task and output format [S13]
- Put critical role, safety, scope and output constraints in the system instruction or at the start of the user request [S13]
- With very long context, place the source material first and the concrete question and instructions after it [S13]
- Pin pricing assumptions: introductory $2/$10 ends 2026-11-30; $4/$20 from 2026-12-01 [S1, S2]
- Conciseness is not the risk here: require a test that reaches every new branch and loop exit, and have the reviewer re-run the verifier rather than read the control flow [S16]
## Change from previous version
- changed: new tier above Flash; adds long decode and a unified 1M window, well beyond 3.8 Flash's 65,536 output-token limit [S1, S8, S9]
- improved: CursorBench 4.0 High 39.6 percent (Gemini 3.8 Flash) to 52.9 percent (Argon) [S11]
- improved: Argon leads LMArena Text and Multi-turn; 3.8 Flash is ninth on both [S15]
- regressed: price higher than 3.8 Flash: introductory $2/$10 vs $0.75/$3.75, rising to $4/$20 from 2026-12-01 [S1, S8, S9]
## Open questions
- Watch out — reports differ: output_tokens. Claude run: 65,536 for a synchronous response, with longer output only through background long decode [S1]. ChatGPT run: 1,048,576 (the unified window) [S8].
- Watch out — reports differ: headless CLI. Claude run: none; no Gemini CLI or Antigravity headless syntax was verified from Google docs, and community reports name an Antigravity CLI [S3]. ChatGPT run: gemini -m gemini-4-argon -p "<prompt>" --output-format json, citing the Gemini CLI headless and subagent docs but not a page showing that exact syntax [S12].
- Watch out — reports differ: role ranking. Claude run: 4th of seven as coordinator, 5th as executor (behind Grok 4.7), 4th as reviewer, citing AA index 53 below Opus 5.5 [S5]. ChatGPT run: 2nd of five as coordinator, executor and reviewer, and Opus 5.5 plus Argon as the best independent reviewer pair [S11, S15]. The rosters differ (the Claude run includes Fable 5.1, Muse Wonder and Composer 2.5).
- Watch out — reports differ: coordinator score. Claude run: 4 [S1, S5]. ChatGPT run: 5 [S11, S15].
- Watch out — reports differ: executor score. Claude run: 4, from vendor-reported DeepSWE v1.1 [S7]. ChatGPT run: 5, from independent CursorBench 4.0 and Terminal-Bench 4.0 [S11, S10].
- Watch out — reports differ: reviewer score. Claude run: 3 [S1]. ChatGPT run: 4 [S15, S11].
- Watch out — reports differ: standing on public indexes. Claude run: AA Intelligence Index 53, below Opus 5.5 [S5]. ChatGPT run: first on LMArena Text (1524) and Multi-turn (1552), second to Opus 5.5 on CursorBench 4.0 (52.9 percent) [S15, S11]. These are different indexes measuring different things.
- Cursor lists a 200K default context for its integration vs 1M on the API [S6].
- Long-output limits depend on invocation mode; do not equate the long-decode maximum with a reliable single synchronous response [S1].
- Public evidence for review false-positive and false-negative calibration: unknown.
## Sources
- S1: What's new in Gemini 4 Argon, Google, 2026-10-13, https://ai.google.dev/gemini-api/docs/latest-model (the ChatGPT run listed the same title and date without a URL), primary (both runs)
- S2: Gemini 4 Argon: Developer Guide, Google AI Studio, 2026-10, https://aistudio.google.com/learn/gemini-4-argon-developer-guide, primary (claude run)
- S3: What Is Gemini 4 Argon?, Kie.ai, 2026-10, https://kie.ai/blog/what-is-gemini-4-argon, independent (claude run)
- S4: Gemini 4 Argon: model ids, price and cutoff, postcutoff, 2026-10-14, https://postcutoff.com/m/gemini-4-argon/, independent (claude run)
- S5: Which AI is best right now? Daily AI Leaderboard, collectivebrain, 2026-10-23, https://collectivebrain.de/en/ai-leaderboard/, independent (claude run)
- S6: Gemini 4 Argon, Cursor, accessed 2026-10-26, https://cursor.com/docs/models/gemini-4-argon, primary (claude run)
- S7: Gemini 4 Argon model card, Google DeepMind, 2026-10, deepmind.google (exact page URL not verified), primary (claude run)
- S8: Gemini 4 Argon model documentation, Google, 2026-10-13, https://ai.google.dev/gemini-api/docs/models/gemini-4-argon, primary (chatgpt run)
- S9: Gemini 3.8 Flash model and migration guide, Google, 2026-09, https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash, primary (chatgpt run)
- S10: Terminal-Bench 4.0, Vals AI, updated 2026-10-18, https://www.vals.ai/benchmarks/terminal-bench-4, independent (chatgpt run)
- S11: CursorBench 4.0, Cursor, accessed 2026-10-20, https://cursor.com/cursorbench, independent (chatgpt run)
- S12: Gemini CLI headless/subagent documentation, Google, accessed 2026-10-20, https://google-gemini.github.io/gemini-cli/, primary (chatgpt run)
- S13: Gemini prompting strategies, Google, accessed 2026-10-20, https://ai.google.dev/gemini-api/docs/prompting-strategies, primary (chatgpt run)
- S14: Gemini API data-use/retention documentation, Google, accessed 2026-10-20, https://ai.google.dev/gemini-api/, primary (chatgpt run)
- S15: LMArena Text/Multi-turn dataset presentation, Arena data via BenchLeader, data 2026-10-19, https://www.benchleader.com/benchmarks/lmarena_text, independent (chatgpt run)
- S16: New data on code quality: GPT-5.2 high, Opus 4.5, Gemini 3, and more, Sonar, 2025-12, https://www.sonarsource.com/blog/new-data-on-code-quality-gpt-5-2-high-opus-4-5-gemini-3-and-more/, vendor benchmark on Java single-file tasks (lean-code reports)
