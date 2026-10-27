---
profile_schema: 2
family: Meta Muse
track: Spark
model: Muse Spark 1.3
api_id: muse-spark-1.3
checkpoint: same-as-api_id
alias_moves: 'no'
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
  effort_controls: 'minimal, low, medium, high, xhigh, max (max not on contributor tier)'
  effort_map: { minimal: minimal, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 1.25, output: 4.25, cached_input: 0.15, fast_input: unknown, fast_output: unknown }
data_handling: 'Standard tier via Meta Model API and Muse Code; the muse-spark-1.3-contributor tier ($0.10/$0.20) lets Meta train on your data [S2, S3]. Also on Google Cloud''s Agent Platform as meta/muse-spark-1.3 (preview, global endpoint, release 2026-09-24) [S4]. Closed weights [S2].'
role_fit:
  coordinator: { score: 2, reason: 'Superseded by Wonder; lower AA index (48)', sources: [S6] }
  executor:    { score: 3, reason: 'Third on AA Agentic Index (55.7) at low cost', sources: [S7] }
  reviewer:    { score: 2, reason: 'No review data', sources: [S6] }
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
- S1: Models - Meta Model API, Meta, accessed 2026-10-26, https://dev.meta.ai/docs/models, primary (claude run)
- S2: Muse Spark 1.3 Tutorial, DataCamp, 2026-09, https://www.datacamp.com/tutorial/muse-spark-1-3-tutorial, independent (claude run)
- S3: Muse Spark 1.3: Specs, Price, and When to Switch, MyClaw, 2026-09, https://myclaw.ai/blog/muse-spark-1-3, independent (claude run)
- S4: Muse Spark 1.3, Google Cloud, 2026-09-24, https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/partner-models/meta/muse-spark-1-3, primary (claude run)
- S5: Muse Spark 1.3 pricing, providers, and specs, models.dev, accessed 2026-10-26, https://models.dev/models/meta/muse-spark-1.3/, independent (claude run)
- S6: Meta launches Muse Wonder and Wonder Full for AI agents, TestingCatalog, 2026-10, https://www.testingcatalog.com/meta-launches-muse-wonder-and-wonder-full-for-ai-agents/, community (claude run)
- S7: AA Agentic Index Leaderboard, BenchLM, 2026-10-10, https://benchlm.ai/benchmarks/aaagenticindex, independent (claude run)
