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
version_rank: previous
release_date: unknown
researched: 2026-11-02
researcher: field
supersedes: none
access:
  context_tokens: 1000000
  output_tokens: unknown
  cli: codex exec --model gpt-5.6-sol -c sandbox_mode=workspace-write -c approval_policy=never "<prompt>"
  cli_verified_from: codex-cli 0.165.0, run 2026-10-28 (exec has no --ask-for-approval)
  subagents: 'yes Cursor agent harness; native OpenAI multi-agent is documented for GPT-6.1 Sol on the API, not verified for this Cursor id [S3]'
  effort_controls: none documented; Cursor model ids carry the effort (gpt-5.6-sol-high, -xhigh, …)
  effort_map: { minimal: unknown, low: unknown, medium: unknown, high: unknown, max: unknown }
cost_usd_per_mtok: { input: 4.00, output: 20.00, cached_input: unknown, fast_input: unknown, fast_output: unknown }
data_handling: 'Runs in Cursor under OpenAI-backed ids listed by `agent --list-models`; no separate public API id for gpt-5.6-sol-high. Treat data handling as OpenAI API / ChatGPT terms when routed through Cursor; not researched here.'
role_fit:
  coordinator: { score: 4, reason: 'Capable Cursor Sol variant; no independent orchestration eval for this Cursor id', sources: [S1] }
  executor:    { score: 4, reason: 'Two aggregators citing the same AA Intelligence Index disagree: one ranks Opus 5.5 first at 57.6, the other ranks GPT-5.6 Sol first at 58.9; the dispute is not a single run and does not justify 5', sources: [S1] }
  reviewer:    { score: 4, reason: 'Different vendor stack from Claude; limited review calibration data for this Cursor id', sources: [S1] }
---
## Strengths
- Cursor lists a 1M-context Sol variant with effort baked into the model id (high, xhigh, max, fast tiers) [S2] (confidence: high)
- List price reported as twice GPT-6 Sol ($4 / $20 per MTok), from the GPT-6 Sol profile's third-party source [S4] (confidence: low)
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
- S1: Model profiles README roster table and benchmark note (two aggregators disagree on AA Intelligence Index), specy-road toolkit, 2026-10-26 (not human-verified)
- S2: Cursor `agent --list-models` capture, model-profiles/harness-captures/cursor/inventory-models.txt, 2026-10-22
- S3: GPT-6.1 Sol profile and OpenAI docs cited there; API id differs from Cursor gpt-5.6-sol-* slugs
- S4: GPT-6 Sol profile source S4 (GPT-6 Sol list price is half of GPT-5.6 Sol): GPT-6 Sol Release Date, EvoLink, 2026-09-23, https://evolink.ai/blog/gpt-6-sol-release-date, independent (claude run)
