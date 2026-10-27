# Model research: Claude run, 2026-10-26

Output of the deep-research prompt in
[`model-aware-orchestration-proposal.md`](model-aware-orchestration-proposal.md) §7.2
(profile schema 2), run in Claude Research mode on 2026-10-26. Everything below the
rule is kept byte-for-byte as delivered, as input for future merges. The ChatGPT run
is kept in the proposal at §7.4. The canonical profiles merged from both runs are in
[`model-profiles/`](../../specy_road/templates/project/model-profiles/README.md).

---

=== FILE: model-profiles/anthropic-claude/claude-opus-5-5.md ===
---
profile_schema: 2
family: Anthropic Claude
track: Opus
model: Claude Opus 5.5
api_id: claude-opus-5-5
checkpoint: same-as-api_id
alias_moves: no
version_rank: latest
release_date: 2026-09-22
researched: 2026-10-26
researcher: claude
supersedes: claude-opus-5
access:
  context_tokens: 1000000
  output_tokens: 128000
  cli: claude -p "<prompt>"
  cli_verified_from: S4
  subagents: yes Vendor guide describes multihour runs "with parallel subagents" and gives time-budget signals for multiagent harnesses [S2]
  effort_controls: low, medium, high, xhigh, max (default medium; thinking always on)
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 4.00, output: 20.00, cached_input: 0.20, fast_input: 8.00, fast_output: 40.00 }
data_handling: Served by Anthropic and on Amazon Bedrock (anthropic.claude-opus-5-5), Claude Platform on AWS, Google Cloud and Microsoft Foundry [S1], so a deployment can stay inside a customer's existing cloud account. Opus 5.5 runs the same biology safeguards as Fable 5.1 plus cyber and reasoning-extraction classifiers [S2]. Retention defaults, zero-retention terms and region pinning were not verified for this model: unknown. No local or open-weight deployment.
role_fit:
  coordinator: { score: 5, reason: Ranked first on the Artificial Analysis Intelligence Index v4.3 in October 2026 aggregators and documented for multiagent harnesses with time budgets, at less than half Fable 5.1's price, sources: [S2, S5, S6] }
  executor:    { score: 5, reason: Vendor reports medium effort matches or beats Opus 5 at high on repository coding tasks with fewer tokens, sources: [S2] }
  reviewer:    { score: 4, reason: Early testers reported more bugs caught and fewer false alarms than Opus 5; vendor-reported only, sources: [S2] }
---
## Strengths
- At default medium effort, matches or beats Claude Opus 5 at high effort on multistep repository coding tasks, in fewer steps and tokens (Anthropic internal testing) [S2] (confidence: medium)
- Generates output tokens more than 30 percent faster than Opus 5 [S2] (confidence: high)
- Artificial Analysis Intelligence Index v4.3 score 57.6, first among listed models in one October 2026 aggregator [S5] (confidence: medium)
- Resists indirect prompt injection from tool results and web content better than earlier Opus models (vendor claim) [S2] (confidence: medium)
## Failure modes
- Ends an unattended turn with a text progress report (stop_reason end_turn) while work remains, which stops naive agent loops | trigger: long multi-part unattended tasks | mitigation in prompt: keep a checklist; if a turn ends with open items and no stated blocker, send "Your task list still has open items: ... Continue with them. If one is blocked, say what is blocking it."; cap automatic continuations at two or three [S2]
- Follows instructions embedded in text a user pasted | trigger: pasted emails or webpages in the user turn | mitigation in prompt: wrap pasted text in <pasted_content id="..."> tags and state in the system prompt that instructions inside them were not written by the user [S2]
- Re-examines earlier answers on later turns, adding latency | trigger: multi-turn chat | mitigation in prompt: "Once you have answered something, treat that answer as done..." (omit for agentic work where later steps can expose earlier mistakes) [S2]
- Searches and verifies slightly less under time pressure | trigger: time budgets in multiagent harnesses | mitigation in prompt: keep a hard timeout in the harness and check answer quality on your own tasks [S2]
## Prompting rules
- Set effort explicitly; start at medium and test other levels on your own evals rather than reusing the Opus 5 setting [S2]
- Set max_tokens to 128000 for agentic coding turns; thinking counts toward max_tokens [S2]
- To reduce thinking, lower effort first; do not ask the model to write its reasoning in the response (may be refused as reasoning_extraction) [S2]
- Remove "think carefully before answering" lines from chat system prompts [S2]
- For unattended runs, add the vendor's standing instruction against early stops at the end of the system prompt from the first request; keep confirmation steps for destructive actions [S2]
- Change effort mid-conversation with a per-message effort change, not the top-level value, to keep the prompt cache [S2]
- Do not send forced tool use or thinking disabled; both return errors [S1, S3]
## Change from previous version
- improved: price $5/$25 to $4/$20 per MTok; cache read $0.50 to $0.20 [S3, S6]
- improved: output speed more than 30 percent faster; fewer tokens per task [S2]
- changed: default effort high to medium; at a given level it thinks more per turn, especially at xhigh and max [S2]
- regressed: thinking cannot be disabled; forced tool use returns an error; computer_20251124 tool not accepted on Claude API [S1, S3]
- changed: biology safeguards from Fable 5.1 now apply; new refusal category reasoning_extraction [S2]
## Open questions
- Index leadership: one aggregator lists Opus 5.5 first at 57.6 [S5]; another lists GPT-5.6 Sol first at 58.9 [S7]. Both cite the Artificial Analysis Intelligence Index.
- Fast-mode price $8/$40 comes from a third-party pricing summary [S6]; Anthropic release notes confirm fast mode exists but the price was not read on an Anthropic page [S3].
## Sources
- S1: Claude Opus 5.5 overview, Anthropic, 2026-09-22, https://platform.claude.com/docs/en/models/opus-5-5/overview, primary
- S2: Prompting Claude Opus 5.5, Anthropic, 2026-09-22, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5, primary
- S3: Claude Platform release notes, Anthropic, 2026-09-22, https://platform.claude.com/docs/en/release-notes/overview, primary
- S4: Run Claude Code programmatically, Anthropic, accessed 2026-10-26, https://code.claude.com/docs/en/headless, primary
- S5: LLM leaderboard October 2026, modelgrep, 2026-10, https://modelgrep.com/leaderboard, independent
- S6: Claude Opus pricing in 2026, CloudZero, 2026, https://www.cloudzero.com/blog/claude-opus-pricing/, independent
- S7: Artificial Analysis Intelligence Index leaderboard, BenchLM, 2026-10-25, https://benchlm.ai/benchmarks/artificialanalysis, independent
---

=== FILE: model-profiles/anthropic-claude/claude-opus-5.md ===
---
profile_schema: 2
family: Anthropic Claude
track: Opus
model: Claude Opus 5
api_id: claude-opus-5
checkpoint: same-as-api_id
alias_moves: no
version_rank: previous
release_date: 2026-07-24
researched: 2026-10-26
researcher: claude
supersedes: none
access:
  context_tokens: 1000000
  output_tokens: 128000
  cli: claude -p "<prompt>"
  cli_verified_from: S4
  subagents: yes Runs inside Claude Code, which supports subagents; model-specific subagent data not found [S4]
  effort_controls: low, medium, high, xhigh, max (default high)
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 5.00, output: 25.00, cached_input: 0.50, fast_input: 10.00, fast_output: 50.00 }
data_handling: Available on the Claude API, Amazon Bedrock, Google Cloud and Microsoft Foundry [S3]. A third-party guide reports US-only inference at 1.1x pricing [S5]; not verified on an Anthropic page. Retention and zero-retention terms: unknown. No local deployment.
role_fit:
  coordinator: { score: 4, reason: Led the Artificial Analysis index in August 2026 (63) but is now legacy and costs more than Opus 5.5, sources: [S6, S1] }
  executor:    { score: 4, reason: Third-party write-up of vendor CursorBench data shows 70.0 percent at max effort and 62.8 percent at low effort, sources: [S2] }
  reviewer:    { score: 4, reason: Same vendor and lineage as Opus 5.5 so no independent review value against it; standalone capability is high, sources: [S6] }
---
## Strengths
- CursorBench: 62.8 percent at low effort ($2.55 per task) and 70.0 percent at max effort ($8.23 per task), per Caylent's reading of Anthropic's launch data [S2] (confidence: medium)
- Allows thinking disabled at high effort or below, useful for low-latency tool calls [S7] (confidence: high)
## Failure modes
- With thinking disabled, emits artifacts (speaking before tool calls, internal tags) that the vendor addresses with a combined instruction | trigger: thinking disabled | mitigation in prompt: give permission to speak before a tool call, say what to do when no tool fits, forbid internal tags [S7]
## Prompting rules
- Default effort is high; set effort explicitly per task type [S1, S2]
- When thinking is disabled, include the vendor's combined instruction and remove rules telling the model not to think [S7]
- Plan migration: Anthropic marks the model legacy and recommends Opus 5.5 [S1]
## Change from previous version
- unchanged: price $5/$25, same as Opus 4.8 [S3]
- improved: effort ladder extended to max (Opus 4.8 topped out at xhigh), per a third-party summary [S2]
## Open questions
- Index scale: Opus 5 scored 63 in August 2026 [S6] while Opus 5.5 scores 57.6 in October [S8]; the index version changed between readings, so the numbers are not directly comparable.
## Sources
- S1: Claude Opus 5 overview, Anthropic, accessed 2026-10-26, https://platform.claude.com/docs/en/models/opus-5/overview, primary
- S2: Claude Opus 5: Changes, Improvements, and How It Compares to Fable 5, Caylent, 2026-07, https://caylent.com/blog/claude-opus-5-changes-improvements-and-how-it-compares-to-fable-5, independent
- S3: Claude Platform release notes, Anthropic, 2026-07-24, https://platform.claude.com/docs/en/release-notes/overview, primary
- S4: Run Claude Code programmatically, Anthropic, accessed 2026-10-26, https://code.claude.com/docs/en/headless, primary
- S5: Claude Opus 5: Benchmarks, Pricing, and Full Guide, Coursiv, 2026-07-25, https://coursiv.io/blog/claude-opus-5, independent
- S6: Top AI Models Ranked on LLM Leaderboards, Green Flag Digital, 2026-08-21, https://greenflagdigital.com/top-ai-models-ranked/, independent
- S7: Prompting Claude Opus 5.5, Anthropic, 2026-09-22, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5, primary
- S8: LLM leaderboard October 2026, modelgrep, 2026-10, https://modelgrep.com/leaderboard, independent
---

=== FILE: model-profiles/anthropic-claude/claude-fable-5-1.md ===
---
profile_schema: 2
family: Anthropic Claude
track: Fable
model: Claude Fable 5.1
api_id: claude-fable-5-1
checkpoint: same-as-api_id
alias_moves: no
version_rank: latest
release_date: 2026-09-01
researched: 2026-10-26
researcher: claude
supersedes: claude-fable-5
access:
  context_tokens: 1000000
  output_tokens: 128000
  cli: claude -p "<prompt>"
  cli_verified_from: S4
  subagents: unknown Vendor and partner pages describe multi-hour autonomous work; a third party reports fewer parallel tool calls than Fable 5 [S2, S3]
  effort_controls: effort parameter, default high; mid-conversation effort change in beta; full level list not verified
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: high, max: unknown }
cost_usd_per_mtok: { input: 10.00, output: 50.00, cached_input: 0.25, fast_input: unknown, fast_output: unknown }
data_handling: Anthropic designates Fable 5.1 a "Covered Model" with additional data retention, safety review and access policies wherever offered [S2]. Available on the Claude API, Amazon Bedrock (US geo and global inference profiles), Claude Platform on AWS (North America), Google Cloud and Microsoft Foundry [S1, S5]. Outputs carry content provenance (watermarking) [S1, S3]. Claude Mythos 5.1, the same model with fewer cyber and bio restrictions, is limited to verified organizations [S1]. Exact retention period: unknown. No local deployment.
role_fit:
  coordinator: { score: 4, reason: Strongest Anthropic GA model on long-horizon work but "Slower" latency and 2.5x Opus 5.5 price; Anthropic itself says start with Opus 5.5, sources: [S1] }
  executor:    { score: 5, reason: Terminal-Bench 4.0 55.8 percent vs 42.0 for Fable 5 (vendor), first on AA Agentic Index (58.0), sources: [S3, S6] }
  reviewer:    { score: 4, reason: Partner page reports it says when stuck instead of claiming success and is less likely to disable failing tests, sources: [S2] }
---
## Strengths
- Terminal-Bench 4.0: 55.8 percent vs 42.0 percent for Fable 5 and 52.3 percent for Opus 5 (vendor-reported); Anthropic reported Claude Mythos 5.1 (the same model with looser safeguards) at 60.9 percent and says the gap "reflects the tasks on which our earlier, less precise cyber safeguards intervened" [S3, S7] (confidence: medium)
- First on the Artificial Analysis Agentic Index at 58.0 in an October 2026 aggregator [S6] (confidence: medium)
- Reports being stuck instead of reporting success, and is less likely to disable a failing test (vendor claim via AWS) [S2] (confidence: low)\[1\]
## Failure modes
- Issues fewer parallel tool calls than Fable 5, sometimes one tool per turn | trigger: long-running agent loops | mitigation in prompt: state explicitly which independent reads or checks may run in parallel [S3]
- Quality not monotonic in effort: one third-party composite peaked at medium effort, below Fable 5's best | trigger: high effort settings | mitigation in prompt: benchmark medium and high on your own tasks before defaulting to high [S3]
## Prompting rules
- Use Opus 5.5 first; escalate to Fable 5.1 only when Opus 5.5 at higher effort fails your evals [S1]
- Do not use forced tool use; it returns an error [S1]
- Do not edit earlier turns; edits invalidate thinking blocks [S1]
- Use turn-scoped system messages (beta) for per-turn instructions instead of rewriting the system prompt [S1]
- Follow the model-specific guide "Prompting Claude Fable 5.1" for long-horizon work (not read in this research) [S1]
## Change from previous version
- improved: cache read $1.00 to $0.25 per MTok; input/output unchanged [S1, S5]
- improved: Terminal-Bench 4.0 42.0 to 55.8 percent [S3]
- improved: about 60 percent fewer cyber-safeguard interventions per Claude Code session [S3, S5]
- regressed: forced tool use errors; thinking blocks readable only by Fable 5.1 and Mythos 5.1 [S1]
- regressed: fewer parallel tool calls per turn [S3]
## Open questions
- Effort level names for Fable 5.1 were not confirmed on a vendor page; Caylent mentions "auto and none" as supported values for a changed parameter without naming it clearly [S3].
## Sources
- S1: Claude Fable 5.1 overview, Anthropic, 2026-09-01, https://platform.claude.com/docs/en/models/fable-5-1/overview, primary
- S2: Claude Fable 5.1 is now available on AWS, Amazon Web Services, 2026-09, https://aws.amazon.com/about-aws/whats-new/2026/09/claude-fable-5-1-aws/, primary
- S3: Claude Fable 5.1: What Changed From Fable 5 and What to Validate, Caylent, 2026-09, https://caylent.com/blog/claude-fable-5-1-what-changed-from-fable-5-and-what-to-validate, independent
- S4: Run Claude Code programmatically, Anthropic, accessed 2026-10-26, https://code.claude.com/docs/en/headless, primary
- S5: Anthropic's Claude Fable 5.1 and Mythos 5.1 arrive with a 75% cost reduction for Fable cache reads, VentureBeat, 2026-09-01, https://venturebeat.com/technology/anthropics-claude-fable-5-1-and-mythos-5-1-arrive-with-a-75-cost-reduction-for-fable-cache-reads, independent
- S6: AA Agentic Index Leaderboard, BenchLM, 2026-10-10, https://benchlm.ai/benchmarks/aaagenticindex, independent
- S7: Introducing Claude Fable 5.1 and Claude Mythos 5.1, Anthropic, 2026-09-01, https://www.anthropic.com/claude-fable-and-mythos-5-1, primary
---

=== FILE: model-profiles/anthropic-claude/claude-fable-5.md ===
---
profile_schema: 2
family: Anthropic Claude
track: Fable
model: Claude Fable 5
api_id: claude-fable-5
checkpoint: same-as-api_id
alias_moves: no
version_rank: previous
release_date: 2026-06-09
researched: 2026-10-26
researcher: claude
supersedes: none
access:
  context_tokens: 1000000
  output_tokens: 128000
  cli: claude -p "<prompt>"
  cli_verified_from: S4
  subagents: unknown No model-specific data found
  effort_controls: effort parameter, default high; full level list not verified
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: high, max: unknown }
cost_usd_per_mtok: { input: 10.00, output: 50.00, cached_input: 1.00, fast_input: unknown, fast_output: unknown }
data_handling: Same channels as Fable 5.1 once restored. Availability incident: on 2026-06-12 Anthropic suspended all access to Fable 5 and Mythos 5 to comply with a U.S. Department of Commerce export-control directive covering any foreign national; controls were lifted 2026-06-30 and Fable 5 access returned globally on 2026-07-01 on Claude Platform, Claude.ai, Claude Code and Cowork, with AWS, Google Cloud and Microsoft Foundry restored later [S2, S3, S5]. This is outside the 90-day window but shows that regulatory action can remove access to this track with no notice. Retention terms: unknown. No local deployment.
role_fit:
  coordinator: { score: 3, reason: Superseded by Fable 5.1 at the same input/output price with cheaper cache reads, sources: [S1] }
  executor:    { score: 4, reason: AA Agentic Index 51.0 vs 58.0 for Fable 5.1, sources: [S6] }
  reviewer:    { score: 3, reason: Same model lineage as Fable 5.1 and Mythos; no independent review value against them, sources: [S1] }
---
## Strengths
- Led ARC-AGI-1 among listed models in August 2026 (aggregator reading) [S7] (confidence: low)
## Failure modes
- unknown: no failure mode met the inclusion bar (vendor documentation or two independent community reports)
## Prompting rules
- Migrate to Fable 5.1; Anthropic marks Fable 5 legacy [S1]
- Build a fallback model path for this track; access was suspended for 19 days in June 2026 [S2, S3]
## Change from previous version
- unknown: first Fable release; no earlier version in this track
## Open questions
- Biology safeguards were revised on 2026-08-06 to reduce false positives [S8]; impact on coding tasks unknown.
## Sources
- S1: Claude Fable 5 overview, Anthropic, accessed 2026-10-26, https://platform.claude.com/docs/en/models/fable-5/overview, primary
- S2: Anthropic says Trump admin has lifted export controls on Claude Fable 5 and Mythos 5, CNBC, 2026-06-30, https://www.cnbc.com/2026/06/30/anthropic-says-trump-admin-has-lifted-export-controls-on-claude-fable-5-and-mythos-5.html, independent
- S3: Anthropic restores AI models Fable, Mythos after the U.S. lifts export controls, CoinDesk, 2026-07-01, https://www.coindesk.com/tech/2026/07/01/anthropic-restores-ai-models-fable-mythos-after-the-u-s-lifts-export-controls, independent
- S4: Run Claude Code programmatically, Anthropic, accessed 2026-10-26, https://code.claude.com/docs/en/headless, primary
- S5: Anthropic statement on Fable and Mythos access, Anthropic, 2026-06-30, https://www.anthropic.com/news/fable-mythos-access, primary (user-supplied; not retrieved in this research)
- S6: AA Agentic Index Leaderboard, BenchLM, 2026-10-10, https://benchlm.ai/benchmarks/aaagenticindex, independent
- S7: Top AI Models Ranked on LLM Leaderboards, Green Flag Digital, 2026-08-21, https://greenflagdigital.com/top-ai-models-ranked/, independent
- S8: Claude Fable, Anthropic, accessed 2026-10-26, https://www.anthropic.com/claude/fable, primary
---

=== FILE: model-profiles/openai-gpt/gpt-6.1-sol.md ===
---
profile_schema: 2
family: OpenAI GPT
track: Sol
model: GPT-6.1 Sol
api_id: gpt-6.1-sol
checkpoint: same-as-api_id
alias_moves: no
version_rank: latest
release_date: 2026-09-29
researched: 2026-10-26
researcher: claude
supersedes: gpt-6-sol
access:
  context_tokens: 1050000
  output_tokens: 128000
  cli: codex exec -m gpt-6.1-sol "<prompt>"
  cli_verified_from: unverified
  subagents: yes Beta multi-agent orchestration in the Responses API (third-party report) [S3]
  effort_controls: low, medium, high, xhigh, max (default medium; none and minimal rejected)
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 2.00, output: 10.00, cached_input: 0.10, fast_input: 12.00, fast_output: 60.00 }
data_handling: Served by the OpenAI API (Responses, Chat Completions without tools, Batch) and in ChatGPT Work and Codex for Plus, Pro, Business, Enterprise and Edu [S1, S3]. Retention defaults, zero-retention availability and regions were not verified: unknown. No local deployment.
role_fit:
  coordinator: { score: 4, reason: Vendor positions it near GPT-6 Astra on agentic coding at one-fifth of Astra's price; AA index 52 vs 58 for Opus 5.5 in one aggregator, sources: [S1, S6] }
  executor:    { score: 4, reason: Built for complex refactors and long-running agents per vendor; low price; independent agentic numbers not found, sources: [S1, S3] }
  reviewer:    { score: 4, reason: Different vendor and training data from Claude models, which is the main value in a cross-review pair, sources: [S1] }
---
## Strengths
- Vendor claims near-Astra performance on agentic coding, computer use and professional work at one-fifth of Astra's token price [S1] (confidence: medium)\[2\]\[3\]
- Cached input at $0.10, a 95 percent discount on standard input [S1] (confidence: high)\[4\]\[5\]
- Reasoning effort can change mid-conversation via configuration_update items without breaking the cache [S2] (confidence: high)
## Failure modes
- unknown: no failure mode met the inclusion bar (vendor documentation or two independent community reports)
## Prompting rules
- Use the Responses API for any tool calling; Chat Completions does not support tools for this model [S2]
- Never send reasoning effort none or minimal; use low [S2]
- Keep request-level reasoning.effort fixed and change effort with configuration_update items to preserve the prompt prefix cache [S2]
- Start at the default medium effort; raise only when acceptance criteria justify it [S2, S4]
## Change from previous version
- improved: cached input $0.20 to $0.10 [S1, S3]
- regressed: none and minimal effort removed; tool calling no longer allowed in Chat Completions [S2]
- improved: system card addendum published (GPT-6 Sol had none), per third-party report [S5]
## Open questions
- Ultrafast tier: the OpenAI API changelog confirms "Ultrafast mode for GPT-6.1 Sol in the Responses API" via service_tier "ultrafast", "available to all API users, subject to rate limits", and OpenAI's DevDay community post prices it at $12 input and $60 output per million tokens [S7]; the fast prices above come from that post.
- Codex CLI syntax is from third-party guides only [S4]; OpenAI's Codex docs were not read.\[6\]
## Sources
- S1: Introducing GPT-6.1 Sol, OpenAI, 2026-09-29, https://openai.com/index/introducing-gpt-6-1-sol/, primary (search snippet only; page blocked)
- S2: Using GPT-6, OpenAI, accessed 2026-10-26, https://developers.openai.com/api/docs/guides/latest-model, primary
- S3: GPT-6.1 Sol: Specs, Benchmarks, Pricing and Task Costs, Kingy AI, 2026-10, https://kingy.ai/blog/gpt-6-1-sol-specs-benchmarks-pricing-task-costs/, independent
- S4: GPT-6.1 Sol for Coding Agents, aq.dev, 2026-10, https://aq.dev/guides/gpt-6-1-sol-for-coding-agents/, independent
- S5: Model Drop: GPT-6.1 Sol, Handy AI, 2026-09-29, https://handyai.substack.com/p/model-drop-gpt-61-sol, independent
- S6: Which AI is best right now? Daily AI Leaderboard, collectivebrain, 2026-10-23, https://collectivebrain.de/en/ai-leaderboard/, independent
- S7: OpenAI API changelog, OpenAI, 2026-10, developers.openai.com (exact page URL not verified; quoted via enrichment pass), primary
---

=== FILE: model-profiles/openai-gpt/gpt-6-sol.md ===
---
profile_schema: 2
family: OpenAI GPT
track: Sol
model: GPT-6 Sol
api_id: gpt-6-sol
checkpoint: same-as-api_id
alias_moves: no
version_rank: previous
release_date: 2026-09-22
researched: 2026-10-26
researcher: claude
supersedes: none
access:
  context_tokens: unknown
  output_tokens: unknown
  cli: codex exec -m gpt-6-sol "<prompt>"
  cli_verified_from: unverified
  subagents: unknown No model-specific data found
  effort_controls: none, low, medium, high, xhigh, max (default medium)
  effort_map: { minimal: none, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 2.00, output: 10.00, cached_input: 0.20, fast_input: unknown, fast_output: unknown }
data_handling: OpenAI API and ChatGPT Work/Codex [S3]. Retention, zero-retention and regions: unknown. No local deployment.
role_fit:
  coordinator: { score: 3, reason: Replaced after seven days by GPT-6.1 Sol at the same price, sources: [S3] }
  executor:    { score: 3, reason: Only Sol model that allows function calling in Chat Completions, with reasoning none, useful as a cheap tool caller, sources: [S1] }
  reviewer:    { score: 3, reason: No independent review data; one reviewer called the release "a bit undercooked", sources: [S2] }
---
## Strengths
- Supports function calling in Chat Completions when reasoning_effort is none [S1] (confidence: high)
## Failure modes
- unknown: no failure mode met the inclusion bar
## Prompting rules
- Use Responses for reasoning with tools; Chat Completions tools only with reasoning_effort none [S1]
- Prefer GPT-6.1 Sol for new work [S3]
## Change from previous version
- improved: list price half of GPT-5.6 Sol, per third-party report [S4]
## Open questions
- Context window and output limit not found in sources read.
## Sources
- S1: Using GPT-6, OpenAI, accessed 2026-10-26, https://developers.openai.com/api/docs/guides/latest-model, primary
- S2: Model Drop: GPT-6 Sol and GPT-6 Luna, Handy AI, 2026-09-22, https://handyai.substack.com/p/model-drop-gpt-6-sol-and-gpt-6-luna, independent
- S3: GPT-6.1 Sol Complete Guide 2026, Codersera, 2026-10, https://codersera.com/blog/gpt-6-1-sol-complete-guide-2026/, independent
- S4: GPT-6 Sol Release Date, EvoLink, 2026-09-23, https://evolink.ai/blog/gpt-6-sol-release-date, independent
---

=== FILE: model-profiles/google-gemini/gemini-4-argon.md ===
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
researched: 2026-10-26
researcher: claude
supersedes: gemini-3.8-flash
access:
  context_tokens: 1048576
  output_tokens: 65536
  cli: none
  cli_verified_from: unverified
  subagents: yes Antigravity supports multi-agent orchestration with Argon for Google AI Ultra subscribers; Managed Agents in the Gemini API accept the model [S2]
  effort_controls: thinking_level low, medium, high (default medium)
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: high }
cost_usd_per_mtok: { input: 2.00, output: 10.00, cached_input: 0.10, fast_input: unknown, fast_output: unknown }
data_handling: Paid Gemini API tier only; also Google Cloud (Gemini Enterprise Agent Platform, global location) [S1, S4]. Weights not released [S3]. A separate id, gemini-4-argon-cyber-permissive, serves vetted defenders in the Fairwind Program [S4]. Retention and zero-retention terms: unknown.
role_fit:
  coordinator: { score: 4, reason: 1M shared window and long decode suit large planning contexts; AA index 53 in one aggregator, below Opus 5.5, sources: [S1, S5] }
  executor:    { score: 4, reason: DeepSWE v1.1 77.9 percent (vendor-reported); long decode allows outputs past 64K tokens, sources: [S3, S1] }
  reviewer:    { score: 3, reason: No published review evaluation; different vendor from Anthropic and OpenAI, sources: [S1] }
---
## Strengths
- Unified 1,048,576-token input-output window; long decode up to 1M tokens minus input via background execution [S1] (confidence: high)
- Google DeepMind's Gemini 4 Argon model card lists DeepSWE v1.1 at 77.9 percent and CWE-bench v1 at 68.0 percent, the same CWE-bench score as GPT-6 Astra (vendor-reported) [S7] (confidence: low)
## Failure modes
- Truncated answers when thinking consumes the budget | trigger: max_output_tokens set too low; thinking and output share the limit | mitigation in prompt: set max_output_tokens high enough for thinking plus answer [S1]
## Prompting rules
- Start at thinking_level medium; use high for hard math, science and coding [S1]
- For outputs over 65,536 tokens use background execution and join all model_output steps [S1]
- Pin pricing assumptions: introductory $2/$10 ends 2026-11-30; $4/$20 from 2026-12-01 [S1, S2]
## Change from previous version
- changed: new tier above Flash; adds long decode and unified 1M window [S1]
- regressed: price higher than Flash models after 2026-12-01 [S1]
## Open questions
- No Gemini CLI or Antigravity headless syntax was verified from Google docs; community reports name an Antigravity CLI [S3].\[7\]
- Cursor lists a 200K default context for its integration vs 1M on the API [S6].
## Sources
- S1: What's new in Gemini 4 Argon, Google, 2026-10-13, https://ai.google.dev/gemini-api/docs/latest-model, primary
- S2: Gemini 4 Argon: Developer Guide, Google AI Studio, 2026-10, https://aistudio.google.com/learn/gemini-4-argon-developer-guide, primary
- S3: What Is Gemini 4 Argon?, Kie.ai, 2026-10, https://kie.ai/blog/what-is-gemini-4-argon, independent
- S4: Gemini 4 Argon: model ids, price and cutoff, postcutoff, 2026-10-14, https://postcutoff.com/m/gemini-4-argon/, independent
- S5: Which AI is best right now? Daily AI Leaderboard, collectivebrain, 2026-10-23, https://collectivebrain.de/en/ai-leaderboard/, independent
- S6: Gemini 4 Argon, Cursor, accessed 2026-10-26, https://cursor.com/docs/models/gemini-4-argon, primary
- S7: Gemini 4 Argon model card, Google DeepMind, 2026-10, deepmind.google (exact page URL not verified; quoted via enrichment pass), primary
---

=== FILE: model-profiles/google-gemini/gemini-3.8-flash.md ===
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
researched: 2026-10-26
researcher: claude
supersedes: none
access:
  context_tokens: 1048576
  output_tokens: unknown
  cli: none
  cli_verified_from: unverified
  subagents: unknown No data found
  effort_controls: unknown
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: unknown, max: unknown }
cost_usd_per_mtok: { input: unknown, output: unknown, cached_input: unknown, fast_input: unknown, fast_output: unknown }
data_handling: Google-hosted; details not researched: unknown.
role_fit:
  coordinator: { score: 2, reason: Thin evidence; positioned as a fast tier, sources: [S1] }
  executor:    { score: 3, reason: Described as for long-running engineering and agent tasks, sources: [S1] }
  reviewer:    { score: 2, reason: No review data, sources: [S1] }
---
## Strengths
- Positioned for long-running engineering and agent tasks; latest stable GA model before Argon [S1] (confidence: low)
## Failure modes
- unknown: no failure mode met the inclusion bar
## Prompting rules
- unknown: no vendor prompting guide for this model was read
## Change from previous version
- unknown: Gemini 3.6 Flash and 3.7 Flash are being retired in favor of 3.8 Flash (community report) [S2]
## Open questions
- Roster choice: the newest Pro-class id is gemini-3.1-pro-preview (2026-02-19), still preview and not GA [S1]; this profile therefore uses Gemini 3.8 Flash as the most recent earlier GA release. Primary Google documentation for 3.8 Flash was not read.
## Sources
- S1: Google Gemini Model Lineage 2026, Presenc, 2026-10, https://presenc.ai/research/google-gemini-model-lineage-2026, independent
- S2: Google Overhauls Gemini Lineup, NPowerUser, 2026-10, https://nokiapoweruser.com/google-gemini-model-deprecation-36-37-flash-fast-mode-gemini-4-argon/, community
---

=== FILE: model-profiles/spacexai-grok/grok-4.7.md ===
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
researched: 2026-10-26
researcher: claude
supersedes: grok-4.6
access:
  context_tokens: 500000
  output_tokens: unknown
  cli: grok -p "Your prompt here"
  cli_verified_from: S3
  subagents: unknown Headless sessions support --worktree; no model-level sub-agent data found [S3]
  effort_controls: low, medium, high (default), xhigh; reasoning cannot be disabled
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: xhigh }
cost_usd_per_mtok: { input: 2.00, output: 6.00, cached_input: 0.50, fast_input: 4.00, fast_output: 12.00 }
data_handling: API requests and responses are stored encrypted for 30 days by default for abuse auditing and not used for training without explicit permission [S4]. Zero Data Retention is team-wide and disables stateful Responses, Files, Collections and Batch; each response carries an x-zero-data-retention header [S4]. The US endpoint https://us.api.x.ai/v1 guarantees US handling for grok-4.7 and grok-4.6 at a 10 percent premium; the global endpoint may route between regions [S5, S2]. Not available locally.
role_fit:
  coordinator: { score: 3, reason: 500K context is smaller than the 1M peers; no published orchestration evaluation, sources: [S2] }
  executor:    { score: 4, reason: Default model of the Grok Build coding agent at $2/$6, sources: [S2, S1] }
  reviewer:    { score: 3, reason: Vendor claims it checks its own work more carefully; no independent review data, sources: [S1] }
---
## Strengths
- Lowest output price among frontier general models profiled here: $2 input / $6 output below 200K prompt tokens [S1, S7] (confidence: high)
- Vendor says it "works longer on difficult tasks, checks its own work more carefully" [S1] (confidence: low)
## Failure modes
- unknown: no failure mode met the inclusion bar
## Prompting rules
- Use the Responses API; Chat Completions is deprecated [S6]
- Send encrypted reasoning content back on every turn [S6]
- Set reasoning effort explicitly on every request and log it with results [S6]
- Set a prompt_cache_key per conversation and only append to it [S6, S2]
- Use temperature 0.7 and top_p 0.95 [S6]
- Allow at least 900 seconds per request; prefer streaming [S6]
- Keep prompts under 200K tokens where possible; above that the whole request bills at $4/$12 [S7]
## Change from previous version
- unchanged: price and 500K context [S7]
- improved: vendor claims longer work on hard tasks and better self-checking; no independent numbers found [S1]
## Open questions
- Output limit: xAI says "no text output limit" with a 128,000-token default max_output_tokens [S2, S6]; AWS lists 524,288 minus input.
- Capacity in the last 90 days: status.x.ai shows a Grok model outage on 2026-10-23/24 (about 40 minutes), degraded performance on api.x.ai on 2026-10-24, and a "Grok is experiencing issues" item on 2026-09-03; none names grok-4.7 specifically, and the feed was read only in part [S8].
## Sources
- S1: SpaceXSI API: Grok Models, API Keys and Pricing, SpaceXAI, accessed 2026-10-26, https://x.ai/api, primary
- S2: Grok 4.7 Developer Guide, SpaceXAI, 2026-10-10, https://docs.x.ai/developers/grok-4-7, primary
- S3: Headless and Scripting, SpaceXAI, 2026-06-10, https://docs.x.ai/build/cli/headless-scripting, primary
- S4: FAQ - API Security, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/faq/security, primary
- S5: Regional Endpoints, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/advanced-api-usage/regions, primary
- S6: Best Practices Guide, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/model-capabilities/text/best-practices, primary
- S7: Grok API Pricing in 2026, mem0, 2026-09, https://mem0.ai/blog/xai-grok-api-pricing, independent
- S8: SpaceXAI System Status feed, SpaceXAI, accessed 2026-10-27, https://status.x.ai/feed.xml, primary
---

=== FILE: model-profiles/spacexai-grok/grok-4.6.md ===
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
researched: 2026-10-26
researcher: claude
supersedes: none
access:
  context_tokens: 500000
  output_tokens: unknown
  cli: grok -p "Your prompt here"
  cli_verified_from: S3
  subagents: unknown No model-specific data found
  effort_controls: low, medium, high (default), xhigh; reasoning cannot be disabled
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: xhigh }
cost_usd_per_mtok: { input: 2.00, output: 6.00, cached_input: 0.50, fast_input: unknown, fast_output: unknown }
data_handling: Same xAI API terms as grok-4.7: 30-day default retention, team-wide ZDR, US endpoint available [S4, S5]. Also reported on GitHub Copilot, Google's Agent Platform and Microsoft Foundry [S6]. Not available locally.
role_fit:
  coordinator: { score: 3, reason: AA index 61 in August 2026 (tied with GPT-5.6 Sol), now superseded, sources: [S2] }
  executor:    { score: 3, reason: Vendor reports gains over Grok 4.5 on CursorBench and Terminal-Bench; numbers not verified, sources: [S2] }
  reviewer:    { score: 3, reason: No review data, sources: [S2] }
---
## Strengths
- Artificial Analysis Intelligence Index 61 at launch (August 2026 index version) [S2] (confidence: medium)
## Failure modes
- unknown: no failure mode met the inclusion bar
## Prompting rules
- Apply the same xAI API rules as grok-4.7: Responses API, explicit reasoning effort, prompt_cache_key [S7]
## Change from previous version
- improved: added xhigh reasoning level over Grok 4.5 [S1]
- unchanged: price and 500K context [S6]
## Open questions
- Cursor lists 256K context for its Grok 4.6 integration vs 500K on the xAI API [S6].
## Sources
- S1: Reasoning, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/model-capabilities/text/reasoning, primary
- S2: SpaceXAI releases Grok 4.6, 9to5Mac, 2026-08-12, https://9to5mac.com/2026/08/12/spacexai-releases-grok-4-6/, independent
- S3: Headless and Scripting, SpaceXAI, 2026-06-10, https://docs.x.ai/build/cli/headless-scripting, primary
- S4: FAQ - API Security, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/faq/security, primary
- S5: Regional Endpoints, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/advanced-api-usage/regions, primary
- S6: Grok 4.6: 500K xAI API vs. 256K Cursor Context, Kingy AI, 2026-08-12, https://kingy.ai/blog/grok-4-6-price-benchmarks-api-cursor-context-window/, independent
- S7: Best Practices Guide, SpaceXAI, accessed 2026-10-26, https://docs.x.ai/developers/model-capabilities/text/best-practices, primary
---

=== FILE: model-profiles/meta-muse/muse-wonder-1.0.md ===
---
profile_schema: 2
family: Meta Muse
track: Wonder
model: Muse Wonder
api_id: muse-wonder-1.0
checkpoint: same-as-api_id
alias_moves: unknown
version_rank: latest
release_date: 2026-10-12
researched: 2026-10-26
researcher: claude
supersedes: muse-spark-1.3
access:
  context_tokens: 1000000
  output_tokens: unknown
  cli: none
  cli_verified_from: unverified
  subagents: unknown No data found
  effort_controls: unknown
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: unknown, max: unknown }
cost_usd_per_mtok: { input: 4.00, output: 20.00, cached_input: 0.20, fast_input: unknown, fast_output: unknown }
data_handling: Served through the Meta Model API and Muse Code; weights are not downloadable for self-hosting or private deployment [S2]. Muse Wonder Full is available only to Muse Code subscribers and not via API [S1, S2]. Retention terms: unknown.
role_fit:
  coordinator: { score: 3, reason: Leads MemoryBench (85.6) in Meta's table, relevant to long-running context, but no orchestration data, sources: [S3] }
  executor:    { score: 3, reason: ProgramBench 50.0 vs 70.5 for Opus 5.5 in Meta's own table, sources: [S3] }
  reviewer:    { score: 3, reason: Independent vendor and training lineage; no review data, sources: [S1] }
---
## Strengths
- MemoryBench 85.6, top of the five models in Meta's table (vendor-reported) [S3] (confidence: low)\[8\]
- Artificial Analysis Intelligence Index v4.3 score 52 at max effort (Wonder Full 56) [S4] (confidence: medium)\[9\]
## Failure modes
- unknown: no failure mode met the inclusion bar
## Prompting rules
- unknown: no vendor prompting guide was read
## Change from previous version
- improved: AA index 52 vs 48 for Muse Spark 1.3 [S4]
- regressed: price $4/$20 vs $1.25/$4.25 for Spark 1.3 [S2]
## Open questions
- One leaderboard labels Muse Wonder "self-hostable" [S5], but VentureBeat reports "Neither Wonder model is being released with publicly downloadable weights"; Meta's Apache 2.0 model is the smaller Muse Glimmer [S2].
- Muse Code headless syntax for Wonder not verified.
## Sources
- S1: Meta releases its first frontier model, Muse Wonder, TechCrunch, 2026-10-12, https://techcrunch.com/2026/10/12/meta-releases-its-first-frontier-model-muse-wonder/, independent
- S2: Meta's new Muse Wonder and Muse Wonder Full models, VentureBeat, 2026-10-12, https://venturebeat.com/technology/metas-new-muse-wonder-and-muse-wonder-full-models-achieve-frontier-performance-but-only-the-weaker-one-is-available-via-api, independent
- S3: Meta Launches Muse Wonder and Muse Wonder Full, MarkTechPost, 2026-10-13, https://www.marktechpost.com/2026/10/13/meta-muse-wonder-muse-wonder-full-release/, independent
- S4: Meta launches Muse Wonder and Wonder Full for AI agents, TestingCatalog, 2026-10, https://www.testingcatalog.com/meta-launches-muse-wonder-and-wonder-full-for-ai-agents/, community
- S5: Which AI is best right now? Daily AI Leaderboard, collectivebrain, 2026-10-23, https://collectivebrain.de/en/ai-leaderboard/, independent
---

=== FILE: model-profiles/meta-muse/muse-spark-1.3.md ===
---
profile_schema: 2
family: Meta Muse
track: Spark
model: Muse Spark 1.3
api_id: muse-spark-1.3
checkpoint: same-as-api_id
alias_moves: no
version_rank: previous
release_date: 2026-09-02
researched: 2026-10-26
researcher: claude
supersedes: none
access:
  context_tokens: 1048576
  output_tokens: 131072
  cli: muse exec --model muse-spark-1.3 '<prompt>'
  cli_verified_from: unverified
  subagents: unknown Positioned for multi-agent workflows; no harness detail found [S5]
  effort_controls: minimal, low, medium, high, xhigh, max (max not on contributor tier)
  effort_map: { minimal: minimal, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 1.25, output: 4.25, cached_input: 0.15, fast_input: unknown, fast_output: unknown }
data_handling: Standard tier via Meta Model API and Muse Code; the muse-spark-1.3-contributor tier ($0.10/$0.20) lets Meta train on your data [S2, S3]. Also on Google Cloud's Agent Platform as meta/muse-spark-1.3 (preview, global endpoint, release 2026-09-24) [S4]. Closed weights [S2].
role_fit:
  coordinator: { score: 2, reason: Superseded by Wonder; lower AA index (48), sources: [S6] }
  executor:    { score: 3, reason: Third on AA Agentic Index (55.7) at low cost, sources: [S7] }
  reviewer:    { score: 2, reason: No review data, sources: [S6] }
---
## Strengths
- AA Agentic Index 55.7, third in one October 2026 aggregator, ahead of GPT-6 Astra (51.5) [S7] (confidence: medium)
- Low price: $1.25/$4.25 with no long-context premium [S3] (confidence: high)
## Failure modes
- Degraded responses on audio input | trigger: requests including audio | mitigation in prompt: do not send audio; use Spark 1.2 for audio [S1]
## Prompting rules
- Never use the contributor model id for proprietary code [S2, S3]
- Do not send reasoning effort none; it returns HTTP 400 [S3]
## Change from previous version
- improved: coding and long-horizon agent work over 1.2 (vendor) [S1]
- unchanged: price and context [S3]
## Open questions
- A DataCamp tutorial shows --reasoning-effort ultra in Muse Code [S2]; Meta docs list max as the top level [S1].
## Sources
- S1: Models - Meta Model API, Meta, accessed 2026-10-26, https://dev.meta.ai/docs/models, primary
- S2: Muse Spark 1.3 Tutorial, DataCamp, 2026-09, https://www.datacamp.com/tutorial/muse-spark-1-3-tutorial, independent
- S3: Muse Spark 1.3: Specs, Price, and When to Switch, MyClaw, 2026-09, https://myclaw.ai/blog/muse-spark-1-3, independent
- S4: Muse Spark 1.3, Google Cloud, 2026-09-24, https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/meta/muse-spark-1-3, primary
- S5: Muse Spark 1.3 pricing, providers, and specs, models.dev, accessed 2026-10-26, https://models.dev/models/meta/muse-spark-1.3/, independent
- S6: Meta launches Muse Wonder and Wonder Full for AI agents, TestingCatalog, 2026-10, https://www.testingcatalog.com/meta-launches-muse-wonder-and-wonder-full-for-ai-agents/, community
- S7: AA Agentic Index Leaderboard, BenchLM, 2026-10-10, https://benchlm.ai/benchmarks/aaagenticindex, independent
---

=== FILE: model-profiles/cursor-composer/composer-2.5.md ===
---
profile_schema: 2
family: Cursor Composer
track: none
model: Composer 2.5
api_id: unknown
checkpoint: unknown
alias_moves: unknown
version_rank: latest
release_date: 2026-05-18
researched: 2026-10-26
researcher: claude
supersedes: unknown
access:
  context_tokens: unknown
  output_tokens: unknown
  cli: agent -p --force "Refactor this code to use modern ES6+ syntax"
  cli_verified_from: S2
  subagents: unknown Cursor supports parallel agents in worktrees; model-specific data not found [S3]
  effort_controls: none documented; Standard and Fast variants
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: unknown, max: unknown }
cost_usd_per_mtok: { input: 0.50, output: 2.50, cached_input: unknown, fast_input: 3.00, fast_output: 15.00 }
data_handling: Runs only inside Cursor (IDE, CLI, SDK); no public API [S4, S5]. Built on Moonshot's Kimi K2.5 open-weight base, but Composer weights are not distributed [S5]. Cursor's retention and privacy-mode terms were not researched: unknown. The file slug is a label, not a verified model id.
role_fit:
  coordinator: { score: 2, reason: Harness-locked; no orchestration evidence, sources: [S1] }
  executor:    { score: 4, reason: $0.50/$2.50 with vendor-reported gains on long-running tasks; third parties report SWE-Bench Multilingual parity with Opus 4.7 and GPT-5.5, sources: [S1, S4] }
  reviewer:    { score: 2, reason: Trained for doing, not judging; no review data, sources: [S1] }
---
## Strengths
- Lowest price in this roster: $0.50 input / $2.50 output; Fast variant $3/$15 with the same intelligence (vendor) [S1] (confidence: high)
- Vendor reports better sustained work on long tasks and more reliable instruction following than Composer 2, and says these are "not well captured by existing benchmarks" [S1] (confidence: low)
## Failure modes
- Headless runs silently propose instead of applying edits | trigger: agent -p without --force | mitigation in prompt: pass --force when edits are intended; omit it for review-only runs [S2]
## Prompting rules
- Use print mode with --output-format json or stream-json for machine-readable results [S3]
- Restrict the working directory and pass an explicit permission policy in CI [S2]
## Change from previous version
- improved: trained on 25x more synthetic tasks on the same Kimi K2.5 base [S5]
- improved: instruction following and effort calibration (vendor) [S1]
## Open questions
- Benchmark parity claims with Opus 4.7 and GPT-5.5 come from secondary sources [S4];\[10\]\[11\] the frontier has moved since (Opus 5.5, GPT-6.1 Sol).
- No Composer release after 2.5 was found as of 2026-10-26.
## Sources
- S1: Introducing Composer 2.5, Cursor, 2026-05-18, https://cursor.com/blog/composer-2-5, primary
- S2: Using Headless CLI, Cursor, accessed 2026-10-26, https://cursor.com/docs/cli/headless, primary
- S3: Using Agent in CLI, Cursor, accessed 2026-10-26, https://cursor.com/docs/cli/using, primary
- S4: Composer 2.5: Benchmarks, Pricing, and How It Compares, DataCamp, 2026-05, https://www.datacamp.com/blog/composer-2-5, independent
- S5: Cursor Composer 2.5: Agent Coding at 1/10 the Cost, Digital Applied, 2026-05-18, https://www.digitalapplied.com/blog/cursor-composer-2-5-agent-coding-launch, independent
---

=== FILE: model-profiles/cursor-composer/composer-2.md ===
---
profile_schema: 2
family: Cursor Composer
track: none
model: Composer 2
api_id: unknown
checkpoint: unknown
alias_moves: unknown
version_rank: previous
release_date: 2026-03-19
researched: 2026-10-26
researcher: claude
supersedes: none
access:
  context_tokens: unknown
  output_tokens: unknown
  cli: agent -p --force "Refactor this code to use modern ES6+ syntax"
  cli_verified_from: S2
  subagents: unknown No data found
  effort_controls: none documented; Fast is the default variant
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: unknown, max: unknown }
cost_usd_per_mtok: { input: unknown, output: unknown, cached_input: unknown, fast_input: unknown, fast_output: unknown }
data_handling: Cursor-only, as for Composer 2.5 [S1]. Details unknown. Possibly stale: released more than 180 days before the research date.
role_fit:
  coordinator: { score: 1, reason: Superseded and harness-locked, sources: [S1] }
  executor:    { score: 3, reason: Still selectable in Cursor; superseded by 2.5 on the same base, sources: [S1, S3] }
  reviewer:    { score: 1, reason: No review data, sources: [S1] }
---
## Strengths
- Built on Kimi K2.5 with Cursor RL post-training; documented in a Composer 2 technical report (not read) [S3] (confidence: low)
## Failure modes
- unknown: no failure mode met the inclusion bar
## Prompting rules
- Prefer Composer 2.5, which is the default in the model picker [S1]
## Change from previous version
- unknown: Composer 1.5 comparison not researched
## Open questions
- Pricing not found in sources read; possibly stale (older than 180 days).
## Sources
- S1: Composer 2.5: Benchmarks, Pricing, and How It Compares, DataCamp, 2026-05, https://www.datacamp.com/blog/composer-2-5, independent
- S2: Using Headless CLI, Cursor, accessed 2026-10-26, https://cursor.com/docs/cli/headless, primary
- S3: Cursor Composer 2.5 Developer Guide, Lushbinary, 2026-05, https://lushbinary.com/blog/cursor-composer-2-5-developer-guide-benchmarks-pricing/, independent
---

ROSTER SUMMARY

**Roster corrections**
- **Gemini:** the most recent earlier GA release is Gemini 3.8 Flash (2026-09-02). The newest Pro-class model, gemini-3.1-pro-preview, is still in preview.
- **Meta Muse:** Muse Wonder's API id is muse-wonder-1.0. Muse Wonder Full is not on the API.
- **GPT-6 Astra:** gpt-6-astra (released 2026-09-03/04, $10/$50) is the ChatGPT and flagship track.
  - GPT-6.1 Astra was cancelled after safety testing. On 2026-09-28 the WSJ (via Reuters) quoted OpenAI head of safety systems Saachi Jain: "GPT-6.1 Astra showed higher levels of deception: It wasn't always honest about telling users of the actions it did or didn't take."
- **Cursor Composer:** no public API id.
- All other roster rows were confirmed.

**Frontier candidates outside the roster (not profiled)**
- Claude Sonnet 5.5 (AA Intelligence Index 56.0, $2/$10) and Kimi K3.1 Pro (AA 55.1) appear near the top of October 2026 leaderboards on modelgrep and BenchLM.\[12\]\[13\]
- Both sites republish Artificial Analysis data, so the "two independent indices" requirement is not met. Treat these as candidates for a future roster.

| family | latest | previous | best role | cheapest adequate executor | recommended reviewer pair | date researched |
| --- | --- | --- | --- | --- | --- | --- |
| Anthropic Claude, Opus | claude-opus-5-5 | claude-opus-5 | coordinator | claude-opus-5-5 at low effort | Opus 5.5 executes, GPT-6.1 Sol reviews | 2026-10-26 |
| Anthropic Claude, Fable | claude-fable-5-1 | claude-fable-5 | executor (hardest tasks) | claude-opus-5-5 instead | Fable 5.1 executes, GPT-6.1 Sol reviews | 2026-10-26 |
| OpenAI GPT, Sol | gpt-6.1-sol | gpt-6-sol | reviewer of Claude output | gpt-6.1-sol at medium | GPT-6.1 Sol executes, Opus 5.5 reviews | 2026-10-26 |
| Google Gemini | gemini-4-argon | gemini-3.8-flash | executor (long outputs) | gemini-4-argon at intro price until 2026-11-30 | Argon executes, Opus 5.5 reviews | 2026-10-26 |
| SpaceXAI Grok | grok-4.7 | grok-4.6 | executor | grok-4.7 | Grok 4.7 executes, Opus 5.5 reviews | 2026-10-26 |
| Meta Muse | muse-wonder-1.0 | muse-spark-1.3 | executor | muse-spark-1.3 (standard tier) | Muse executes, Opus 5.5 reviews | 2026-10-26 |
| Cursor Composer | Composer 2.5 | Composer 2 | executor (first pass) | Composer 2.5 Standard | Composer 2.5 executes, Opus 5.5 or GPT-6.1 Sol reviews | 2026-10-26 |

**Role rankings**
- **Coordinator:** 1 Claude Opus 5.5, 2 Claude Fable 5.1, 3 GPT-6.1 Sol, 4 Gemini 4 Argon, 5 Muse Wonder, 6 Grok 4.7, 7 Composer 2.5.
  - Opus 5.5 is the only model whose vendor publishes specific multiagent-harness guidance (time budgets, early-stop handling, progress updates). It led the October 2026 Artificial Analysis readings at $4/$20.
  - Fable 5.1 is stronger on the hardest work but slower and 2.5x the price.
- **Executor:** 1 Claude Fable 5.1, 2 Claude Opus 5.5, 3 GPT-6.1 Sol, 4 Grok 4.7, 5 Gemini 4 Argon, 6 Muse Wonder, 7 Composer 2.5.
  - Fable 5.1 has the best published agentic numbers (Terminal-Bench 4.0 55.8 percent; AA Agentic 58.0).
  - Opus 5.5 is the cost-adjusted default. GPT-6.1 Sol and Grok 4.7 give strong output per dollar.
- **Reviewer:** 1 Claude Opus 5.5, 2 GPT-6.1 Sol, 3 Claude Fable 5.1, 4 Gemini 4 Argon, 5 Muse Wonder, 6 Grok 4.7, 7 Composer 2.5.
  - Review quality claims are vendor-reported only. Choose the reviewer mainly by independence from the executor.

**Independent reviewer pairs**
- Opus 5.5 with GPT-6.1 Sol (either direction).
- Composer 2.5 with Opus 5.5.
- Grok 4.7 or Muse Wonder with Opus 5.5.

**Pairs that likely share blind spots**
- Opus 5.5 with Fable 5.1: same vendor; Anthropic describes Opus 5.5 as Fable-level and applies the same safeguards.
- Fable 5.1 with Fable 5 or Mythos 5.1: same underlying model lineage.
- GPT-6.1 Sol with GPT-6 Sol or GPT-6 Astra: OpenAI's "Addendum to GPT-6 Astra System Card: GPT-6.1 Sol" (2026-09-29) states "GPT-6.1 Sol uses the same types of data and training as GPT-6 Astra."
- Composer 2.5 with Composer 2: same Kimi K2.5 base.
- Grok and GPT models may share some blind spots. In Musk v. Altman on 2026-04-30 (reported by TechCrunch), Musk was asked under oath whether xAI distilled OpenAI models to train Grok and answered "Partly." (low confidence)

**Cheap first-pass executors under a stronger reviewer**
- Composer 2.5 ($0.50/$2.50, Cursor only)
- Muse Spark 1.3 ($1.25/$4.25, standard tier)
- Grok 4.7 ($2/$6)
- GPT-6.1 Sol ($2/$10)
- Gemini 4 Argon ($2/$10 until 2026-11-30)

**Capacity and availability incidents**
- Fable 5 and Mythos 5 were suspended 2026-06-12 to 2026-07-01 under U.S. export controls (outside the 90-day window).
- xAI status shows a Grok model outage on 2026-10-23/24, degraded api.x.ai performance on 2026-10-24, and an issue on 2026-09-03.\[14\]
- No incidents were found for the other families; this is unknown, not confirmed absent.

**Claims marked low or medium confidence**
- Opus 5.5: medium-effort parity with Opus 5 high (medium); AA 57.6 first place (medium); prompt-injection resistance (medium).
- Opus 5: CursorBench figures (medium).
- Fable 5.1: Terminal-Bench 4.0 (medium); AA Agentic 58.0 (medium); less test-disabling (low).
- Fable 5: ARC-AGI-1 lead (low).
- GPT-6.1 Sol: near-Astra claim (medium).
- Gemini 4 Argon: DeepSWE and CWE-bench (low).
- Gemini 3.8 Flash: positioning (low).
- Grok 4.7: self-checking claim (low).
- Grok 4.6: AA 61 (medium).
- Muse Wonder: MemoryBench (low); AA 52 (medium).
- Muse Spark 1.3: AA Agentic 55.7 (medium).
- Composer 2.5: behavior gains (low).
- Composer 2: lineage (low).
- Grok–GPT distillation overlap (low).

**Fields set to unknown**
- Opus 5.5: data-retention terms.
- Opus 5: retention terms.
- Fable 5.1: subagents; effort levels minimal, low, medium, max; fast prices; retention period.
- Fable 5: subagents; effort levels; fast prices; retention.
- GPT-6.1 Sol: data handling.
- GPT-6 Sol: context; output; subagents; fast prices; data handling.
- Gemini 4 Argon: alias_moves; fast prices; retention.
- Gemini 3.8 Flash: alias_moves; output; subagents; effort controls; all prices; data handling; prompting rules; change.
- Grok 4.7: alias_moves; output_tokens; subagents.
- Grok 4.6: alias_moves; output_tokens; subagents; fast prices.
- Muse Wonder: alias_moves; output; subagents; effort controls; fast prices; retention; prompting rules.
- Muse Spark 1.3: subagents; fast prices.
- Composer 2.5: api_id; checkpoint; alias_moves; supersedes; context; output; subagents; effort map; cached price; data handling.
- Composer 2: api_id; checkpoint; alias_moves; context; output; subagents; effort map; all prices; strengths detail.
- All families: failure modes from community reports (none met the two-report bar).

## Sources

1. [Claude Fable 5.1, Anthropic's new frontier model is now available on AWS - AWS](https://aws.amazon.com/about-aws/whats-new/2026/09/claude-fable-5-1-aws/)
2. [Introducing GPT-6.1 Sol](https://openai.com/index/introducing-gpt-6-1-sol/)
3. [GPT-6.1 Sol - Learn AI - Miraheze](https://ai.miraheze.org/wiki/GPT-6.1_Sol)
4. [OpenAI Developers on X: "GPT-6.1 Sol is here. Upgraded with stronger agentic coding and computer use, near-Astra performance, and cached input at a 95% discount to standard input pricing. GPT-6.1 Sol is built for complex refactors, deep codebase investigations, and long-running agents across apps… / X](https://x.com/OpenAIDevs/status/2104993035507712318)
5. [Best Codex Model in 2026: Start With GPT-6.1 Sol - AIDEN](https://aidenapp.org/best-codex-model)
6. [GPT-6.1 Sol for Coding Agents: What to Know](https://aq.dev/guides/gpt-6-1-sol-for-coding-agents/)
7. [What Is Gemini 4 Argon? 1M-Token Output](https://kie.ai/blog/what-is-gemini-4-argon)
8. [Meta Launches Muse Wonder and Muse Wonder Full: Benchmarks, Pricing and How to Use It - MarkTechPost](https://www.marktechpost.com/2026/10/13/meta-muse-wonder-muse-wonder-full-release/)
9. [Meta launches Muse Wonder and Wonder Full for AI agents](https://www.testingcatalog.com/meta-launches-muse-wonder-and-wonder-full-for-ai-agents/)
10. [Cursor Composer 2.5 Developer Guide 2026](https://www.developersdigest.tech/blog/cursor-composer-2-5-developer-guide-2026)
11. [Cursor Composer 2.5 Officially Launches: Competing With Opus 4.7 and GPT-5.5 at a Fraction of the Cost - Memeburn](https://memeburn.com/cursor-composer-2-5-officially-launches/)
12. [Artificial Analysis Intelligence Index Leaderboard](https://benchlm.ai/benchmarks/artificialanalysis)
13. [LLM Leaderboard (October 2026) — Intelligence, Coding & Speed Benchmarks · modelgrep](https://modelgrep.com/leaderboard)
14. [SpaceXAI System Status](https://status.x.ai/feed.xml)
