---
profile_schema: 2
family: OpenAI GPT
track: Sol
model: GPT-5.6 Sol
api_id: gpt-5.6-sol
aliases:
  - gpt-5.6-sol-none
  - gpt-5.6-sol-none-fast
  - gpt-5.6-sol-low
  - gpt-5.6-sol-low-fast
  - gpt-5.6-sol-medium
  - gpt-5.6-sol-medium-fast
  - gpt-5.6-sol-high
  - gpt-5.6-sol-high-fast
  - gpt-5.6-sol-xhigh
  - gpt-5.6-sol-xhigh-fast
  - gpt-5.6-sol-max
  - gpt-5.6-sol-max-fast
checkpoint: unknown
alias_moves: unknown
version_rank: latest
release_date: unknown
researched: 2026-10-20
researcher: merged
supersedes: none
access:
  context_tokens: 1050000
  output_tokens: 128000
  cli: agent -p --force "<prompt>"
  cli_verified_from: S2
  subagents: 'yes Cursor agent harness; native OpenAI multi-agent is documented for GPT-6.1 Sol on the API, not verified for this Cursor id [S3]'
  effort_controls: none documented; Cursor model ids carry the effort (gpt-5.6-sol-high, -xhigh, …)
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: unknown, max: unknown }
cost_usd_per_mtok: { input: 2.00, output: 10.00, cached_input: unknown, fast_input: unknown, fast_output: unknown }
data_handling: 'Runs in Cursor under OpenAI-backed ids listed by `agent --list-models`; no separate public API id for gpt-5.6-sol-high. Treat data handling as OpenAI API / ChatGPT terms when routed through Cursor; not researched here.'
role_fit:
  coordinator: { score: 4, reason: 'Same Sol family positioning as GPT-6.1 Sol in merged research, but Cursor-only ids and no independent orchestration eval', sources: [S1] }
  executor:    { score: 5, reason: 'Cursor Sol line used for agentic coding; one leaderboard run ranked GPT-5.6 Sol first at 58.9 vs Opus 5.5 at 57.6 (directional, not human-verified)', sources: [S1] }
  reviewer:    { score: 4, reason: 'Different vendor stack from Claude; same cross-review value as GPT-6.1 Sol with limited review calibration data', sources: [S1] }
---
## Strengths
- Cursor lists a 1M-context Sol variant with effort baked into the model id (high, xhigh, max, fast tiers) [S2] (confidence: high)
- Standard Sol-class pricing in the merged roster ($2 / $10 input/output per MTok on API-facing profiles) [S1] (confidence: medium)
## Failure modes
- Effort is fixed by the roster id; changing effort mid-leaf needs a different roster entry or harness switch | trigger: coordinator assigns the wrong `-high` vs `-xhigh` id | mitigation in prompt: match the roster id to the intended review depth before dispatch [S2]
- Cursor-only routing; reproducibility outside Cursor is unknown | trigger: CI or headless worker not on Cursor | mitigation in prompt: do not assume Codex or API strings match these ids [S2]
## Code and test tendencies
- Same family tendencies as GPT-6 Sol / 6.1 Sol in the merged profiles: verbose output and strong Codex-style agent habits when run on OpenAI harnesses; on Cursor, mock-heavy weak-oracle tests are a measured risk (lean-code reports, not human-verified) [S1]
## Prompting rules
- The roster id is the harness model string; do not strip the effort suffix [S2]
- State scope, touch zones and stop conditions explicitly; Sol-class models infer boundaries poorly under pressure [S1]
- Require each test to assert an output, error or state; forbid new mocks where a real boundary is practical [S1]
## Change from previous version
- new: profile added for Cursor effort-suffixed Sol ids (2026-11-02)
## Open questions
- Watch out — reports differ: whether GPT-5.6 Sol in Cursor maps 1:1 to GPT-6.1 Sol on the API; treat them as related Sol-family lines, not identical checkpoints [S1, S3]
## Sources
- S1: Model profiles README roster table and benchmark note, specy-road toolkit, 2026-10-26 (merged research, not human-verified)
- S2: Cursor `agent --list-models` capture, model-profiles/harness-captures/cursor/inventory-models.txt, 2026-10-22
- S3: GPT-6.1 Sol profile and OpenAI docs cited there; API id differs from Cursor gpt-5.6-sol-* slugs
