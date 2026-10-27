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
data_handling: 'Served through the Meta Model API and Muse Code; weights are not downloadable for self-hosting or private deployment [S2]. Muse Wonder Full is available only to Muse Code subscribers and not via API [S1, S2]. Retention terms: unknown.'
role_fit:
  coordinator: { score: 3, reason: 'Leads MemoryBench (85.6) in Meta''s table, relevant to long-running context, but no orchestration data', sources: [S3] }
  executor:    { score: 3, reason: 'ProgramBench 50.0 vs 70.5 for Opus 5.5 in Meta''s own table', sources: [S3] }
  reviewer:    { score: 3, reason: 'Independent vendor and training lineage; no review data', sources: [S1] }
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
- S1: Meta releases its first frontier model, Muse Wonder, TechCrunch, 2026-10-12, https://techcrunch.com/2026/10/12/meta-releases-its-first-frontier-model-muse-wonder/, independent (claude run)
- S2: Meta's new Muse Wonder and Muse Wonder Full models, VentureBeat, 2026-10-12, https://venturebeat.com/technology/metas-new-muse-wonder-and-muse-wonder-full-models-achieve-frontier-performance-but-only-the-weaker-one-is-available-via-api, independent (claude run)
- S3: Meta Launches Muse Wonder and Muse Wonder Full, MarkTechPost, 2026-10-13, https://www.marktechpost.com/2026/10/13/meta-muse-wonder-muse-wonder-full-release/, independent (claude run)
- S4: Meta launches Muse Wonder and Wonder Full for AI agents, TestingCatalog, 2026-10, https://www.testingcatalog.com/meta-launches-muse-wonder-and-wonder-full-for-ai-agents/, community (claude run)
- S5: Which AI is best right now? Daily AI Leaderboard, collectivebrain, 2026-10-23, https://collectivebrain.de/en/ai-leaderboard/, independent (claude run)
