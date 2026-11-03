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
  cli: codex exec --model gpt-5.6-sol --disable memories --disable multi_agent --disable goals -c sandbox_mode=workspace-write -c approval_policy=never "<prompt>"
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
## Orchestration: harness features to avoid

When this model runs as a roster **executor** on `codex`, the worker command includes:

| Feature | Switch |
|---|---|
| memories | `--disable memories` |
| multi_agent | `--disable multi_agent` |
| goals | `--disable goals` |

Orchestration guard hooks deny executors `git push`, `gh pr`, worktree and cloud commands; reviewers also deny `git commit`.

## Strengths
- Cursor lists a 1M-context Sol variant with effort baked into the model id (high, xhigh, max, fast tiers) [S2] (confidence: high)
- List price reported as twice GPT-6 Sol ($4 / $20 per MTok), from the GPT-6 Sol profile's third-party source [S4] (confidence: low)
## Failure modes
- Effort is fixed by the roster id; changing effort mid-leaf needs a different roster entry or harness switch | trigger: coordinator assigns the wrong `-high` vs `-xhigh` id | mitigation in prompt: match the roster id to the intended review depth before dispatch [S2]
- Cursor-only routing; reproducibility outside Cursor is unknown | trigger: CI or headless worker not on Cursor | mitigation in prompt: do not assume Codex or API strings match these ids [S2]
## Code and test tendencies
- GPT-5.x High was the most verbose model in Sonar's December 2025 leaderboard data (974,379 LOC on the same Java task set vs Gemini 3 Pro ~289,752); vendor benchmark, single-file Java, directional only (researched 2026-10-27 from the lean-code reports, not human-verified) [S5]
- Codex PRs reverted least in the field: 6.1 percent vs 11.5 percent human (OR 0.50), median 63 changed lines (Kraishan, 2026-09-12; researched 2026-10-27 from the lean-code reports, not human-verified) [S6]
- OpenAI's Codex guidance says to search for prior art and reuse or extract a shared helper before adding new helpers or logic, and warns against speculative changes, broad catches and silent defaults (read 2026-10-27; researched 2026-10-27 from the lean-code reports, not human-verified) [S7]
## Prompting rules
- The roster id is the harness model string; do not strip the effort suffix [S2]
- State scope, touch zones and stop conditions explicitly; Sol-class models infer boundaries poorly under pressure [S1]
- Require each test to assert an output, error or state; forbid new mocks where a real boundary is practical [S1]
- Require a prior-art search before any new helper and a named reuse in the summary, and fix the output format; this family writes the most code per task but its merged work holds up [S5, S7]
## Change from previous version
- new: profile added for Cursor effort-suffixed Sol ids (2026-11-02)
## Open questions
- Watch out — reports differ: whether GPT-5.6 Sol in Cursor maps 1:1 to GPT-6.1 Sol on the API; treat them as related Sol-family lines, not identical checkpoints [S1, S3]
## Sources
- S1: Model profiles README roster table and benchmark note (two aggregators disagree on AA Intelligence Index), specy-road toolkit, 2026-10-26 (not human-verified)
- S2: Cursor `agent --list-models` capture, model-profiles/harness-captures/cursor/inventory-models.txt, 2026-10-22
- S3: GPT-6.1 Sol profile and OpenAI docs cited there; API id differs from Cursor gpt-5.6-sol-* slugs
- S4: GPT-6 Sol profile source S4 (GPT-6 Sol list price is half of GPT-5.6 Sol): GPT-6 Sol Release Date, EvoLink, 2026-09-23, https://evolink.ai/blog/gpt-6-sol-release-date, independent (claude run)
- S5: New data on code quality: GPT-5.2 high, Opus 4.5, Gemini 3, and more, Sonar, 2025-12, https://www.sonarsource.com/blog/new-data-on-code-quality-gpt-5-2-high-opus-4-5-gemini-3-and-more/, vendor benchmark on Java single-file tasks (lean-code reports)
- S6: Not All Agents Are Equal: Code Quality and Post-Merge Maintenance Across Five Autonomous Coding Agents in the Wild, Kraishan, arXiv 2609.17598, 2026-09-12, https://arxiv.org/html/2609.17598, independent (lean-code reports)
- S7: Codex best practices (search for prior art before adding helpers), OpenAI, accessed 2026-10-27, https://developers.openai.com/codex/learn/best-practices, primary (lean-code reports)
