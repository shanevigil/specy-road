---
profile_schema: 2
family: Anthropic Claude
track: Opus
model: Claude Opus 5
api_id: claude-opus-5
checkpoint: same-as-api_id
alias_moves: 'no'
version_rank: previous
release_date: 2026-07-24
researched: 2026-10-20
researcher: merged
supersedes: none
access:
  context_tokens: 1000000
  output_tokens: 128000
  cli: claude -p "<prompt>"
  cli_verified_from: S4
  subagents: 'yes Runs inside Claude Code, which supports subagents and parallel delegation; model-specific subagent data not found [S4]'
  effort_controls: 'low, medium, high, xhigh, max (default high)'
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 5.00, output: 25.00, cached_input: 0.50, fast_input: 10.00, fast_output: 50.00 }
data_handling: 'Available on the Claude API, Amazon Bedrock, Google Cloud and Microsoft Foundry [S3]. Commercial and API inputs and outputs are not used for model training by default; standard API retention is generally up to 30 days; zero data retention is available by qualifying agreement; cloud and regional deployment options exist [S13]. A third-party guide reports US-only inference at 1.1x pricing [S5]; not verified on an Anthropic page. No local deployment.'
role_fit:
  coordinator: { score: 4, reason: 'Both runs rate it capable but superseded - it led the Artificial Analysis index in August 2026 (63) and remains a capable long-horizon Claude Code model, but Anthropic marks it legacy and it trails Opus 5.5 on multi-file coding benchmarks while costing more', sources: [S6, S1, S9] }
  executor:    { score: 4, reason: 'Both runs rate it 4 on conflicting CursorBench evidence - a third-party write-up of vendor data shows 70.0 percent at max effort and 62.8 percent at low, while CursorBench 4.0 shows 46.6 percent at Max, 11.2 points below Opus 5.5 at a higher token price', sources: [S2, S9, S1] }
  reviewer:    { score: 4, reason: 'Both runs find high standalone capability but no independent reviewer calibration data; same vendor and lineage as Opus 5.5, so no independent review value against it', sources: [S6, S1, S9] }
---
## Strengths
- CursorBench (version not stated): 62.8 percent at low effort ($2.55 per task) and 70.0 percent at max effort ($8.23 per task), per Caylent's reading of Anthropic's launch data [S2] (confidence: medium)
- CursorBench 4.0: 46.6 percent at Max, strong multi-file agent performance though below Opus 5.5 [S9] (confidence: high)
- 1M context and 128K output, the same nominal limits as Opus 5.5 [S1] (confidence: high)
- Supports all five Anthropic effort levels, including xhigh and max [S11] (confidence: high)
- Allows thinking disabled at high effort or below, useful for low-latency tool calls [S7] (confidence: high)
## Failure modes
- With thinking disabled, emits artifacts (speaking before tool calls, internal tags) that the vendor addresses with a combined instruction | trigger: thinking disabled | mitigation in prompt: give permission to speak before a tool call, say what to do when no tool fits, forbid internal tags [S7]
- Returns an error when thinking is disabled at xhigh or max | trigger: combining maximum effort with disabled thinking | mitigation in prompt: use adaptive thinking at those levels [S11]
- Over-verifies or does more testing and work than a narrow task requires | trigger: small, well-scoped fixes without explicit scope limits | mitigation in prompt: specify exactly what must be verified and prohibit unrelated refactors or cleanup [S15]
- Writes longer responses than needed | trigger: no output-size instruction | mitigation in prompt: request concise progress and output and a fixed final-report format [S15]
## Code and test tendencies
- Opus 4.5 and 4.6 tend to over-engineer: extra files, unnecessary abstractions, flexibility that was not requested; Anthropic's own prompting guidance, live page read 2026-10-27 (researched 2026-10-27 from the lean-code reports, not human-verified) [S16]
- Opus 5 verifies its own work unprompted; self-check instructions cause over-verification (Anthropic prompting best practices, read 2026-10-27; researched 2026-10-27 from the lean-code reports, not human-verified) [S16]
- Claude Code PRs measured largest and deepest in the field: median 495 changed lines vs 52 human, nesting depth 4 vs 3, highest branch density; n=459, task mix confounded (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S17]
- Strong test oracles: Claude Code is among the agents with the strongest assertion signals in field PRs (Banik et al., 2026-06; researched 2026-10-27 from the lean-code reports, not human-verified) [S18]
## Prompting rules
- Default effort is high; set effort explicitly per task type, and use xhigh or max for extended coding only when the extra cost is justified [S1, S2, S11]
- When thinking is disabled, include the vendor's combined instruction and remove rules telling the model not to think [S7]
- For narrow tasks, state the intended scope and amount of verification rather than saying "be thorough" [S15]
- Request concise output when verbosity is undesirable [S15]
- Put ordered workflows in numbered steps and role and context in clearly separated prompt regions [S12]
- Give subagents narrow, non-overlapping responsibilities rather than unbounded delegation [S15]
- Plan migration: Anthropic marks the model legacy and recommends Opus 5.5 [S1]
- Name the smallest behaviour-complete change and forbid extra files, abstractions, fallbacks and validation inside boundaries; this family's measured risk is diff size and depth, not weak tests; for this version also omit self-check instructions, which cause over-verification [S16, S17]
## Change from previous version
- unchanged: price $5/$25, same as Opus 4.8 [S3]
- improved: effort ladder extended to max (Opus 4.8 topped out at xhigh), per a third-party summary [S2]
- improved: Anthropic describes Opus 5 as a large improvement over Opus 4.8 in coding, agents and professional work [S10]
- improved: 1M context and 128K output support very large repository and context workflows [S1]
- regressed relative to Opus 5.5 (the newer version): higher $5/$25 token pricing and $0.50 cache reads versus $4/$20 and $0.20 [S14, S1]
- regressed relative to Opus 5.5 (the newer version): CursorBench 4.0 Max 46.6 percent versus 57.8 percent [S9]
## Open questions
- Watch out — reports differ: CursorBench score. Claude run: 70.0 percent at max effort and 62.8 percent at low effort, benchmark version not stated, from Caylent's reading of Anthropic launch data [S2]. ChatGPT run: 46.6 percent at Max on CursorBench 4.0 [S9]. The figures likely come from different CursorBench versions.
- Watch out — reports differ: headless CLI invocation. Claude run: claude -p "<prompt>" [S4]. ChatGPT run: claude -p --model claude-opus-5 --output-format json "<prompt>" (no source cited for the syntax).
- Fast-mode price $10/$50 comes from the Claude run, which names no source for it; the ChatGPT run lists fast pricing as unknown.
- Index scale: Opus 5 scored 63 in August 2026 [S6] while Opus 5.5 scores 57.6 in October [S8]; the index version changed between readings, so the numbers are not directly comparable. (claude run)
- Independent measurements separating Opus 5's review ability from its general implementation ability are insufficient. (chatgpt run)
## Sources
- S1: Claude Opus 5 overview, Anthropic, 2026-07-24, https://platform.claude.com/docs/en/models/opus-5/overview, primary (both runs)
- S2: Claude Opus 5: Changes, Improvements, and How It Compares to Fable 5, Caylent, 2026-07, https://caylent.com/blog/claude-opus-5-changes-improvements-and-how-it-compares-to-fable-5, independent (claude run)
- S3: Claude Platform release notes, Anthropic, 2026-07-24, https://platform.claude.com/docs/en/release-notes/overview, primary (claude run)
- S4: Run Claude Code programmatically, Anthropic, accessed 2026-10-26, https://code.claude.com/docs/en/headless, primary (claude run)
- S5: Claude Opus 5: Benchmarks, Pricing, and Full Guide, Coursiv, 2026-07-25, https://coursiv.io/blog/claude-opus-5, independent (claude run)
- S6: Top AI Models Ranked on LLM Leaderboards, Green Flag Digital, 2026-08-21, https://greenflagdigital.com/top-ai-models-ranked/, independent (claude run)
- S7: Prompting Claude Opus 5.5, Anthropic, 2026-09-22, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5, primary (claude run)
- S8: LLM leaderboard October 2026, modelgrep, 2026-10, https://modelgrep.com/leaderboard, independent (claude run)
- S9: CursorBench 4.0, Cursor, accessed 2026-10-20, https://cursor.com/cursorbench, independent (chatgpt run)
- S10: Claude Opus release history, Anthropic, accessed 2026-10-20, https://www.anthropic.com/claude/opus, primary (chatgpt run)
- S11: Effort, Anthropic Claude Platform Docs, accessed 2026-10-20, https://platform.claude.com/docs/en/build-with-claude/effort, primary (chatgpt run)
- S12: Claude prompting best practices, Anthropic, accessed 2026-10-20, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview, primary (chatgpt run)
- S13: Anthropic privacy documentation, Anthropic, accessed 2026-10-20, https://privacy.claude.com/, primary (chatgpt run)
- S14: Claude Opus 5.5 overview, Anthropic, 2026-09-22, https://platform.claude.com/docs/en/models/opus-5-5/overview, primary (chatgpt run)
- S15: Prompting Claude Opus 5, Anthropic Claude Platform Docs, accessed 2026-10-20, URL not given in ChatGPT report, primary (chatgpt run)
- S16: Claude prompting best practices (over-engineering and self-check notes), Anthropic, accessed 2026-10-27, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices, primary (lean-code reports)
- S17: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S18: All Smoke, No Alarm: Oracle Signals in Agent-Authored Test Code, Banik, Chowdhury and Shamim, arXiv 2606.18168, 2026-06, https://arxiv.org/html/2606.18168v1, independent (lean-code reports)
