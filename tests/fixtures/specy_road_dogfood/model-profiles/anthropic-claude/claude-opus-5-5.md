---
profile_schema: 2
family: Anthropic Claude
track: Opus
model: Claude Opus 5.5
api_id: claude-opus-5-5
checkpoint: same-as-api_id
alias_moves: 'no'
version_rank: latest
release_date: 2026-09-22
researched: 2026-10-20
researcher: merged
supersedes: claude-opus-5
access:
  context_tokens: 1000000
  output_tokens: 128000
  cli: claude -p "<prompt>"
  cli_verified_from: S4
  subagents: yes Vendor guide describes multihour runs "with parallel subagents" and gives time-budget signals for multiagent harnesses; both runs report Claude Code subagent support and parallel delegation [S2]
  effort_controls: 'low, medium, high, xhigh, max (default medium; thinking always on)'
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: max }
cost_usd_per_mtok: { input: 4.00, output: 20.00, cached_input: 0.20, fast_input: 8.00, fast_output: 40.00 }
data_handling: 'Served by Anthropic and on Amazon Bedrock (anthropic.claude-opus-5-5), Claude Platform on AWS, Google Cloud and Microsoft Foundry [S1], so a deployment can stay inside a customer''s existing cloud account. Commercial and API inputs and outputs are not used for model training by default; standard API retention is generally up to 30 days; contractual zero data retention is available for eligible enterprise and API arrangements; regional processing is available through supported cloud and platform configurations, including US-only inference at a premium [S13]. Opus 5.5 runs the same biology safeguards as Fable 5.1 plus cyber and reasoning-extraction classifiers [S2]. No local or open-weight deployment.'
role_fit:
  coordinator: { score: 5, reason: 'Both runs rate it first for coordination - first on the Artificial Analysis Intelligence Index v4.3 (57.6) in one October 2026 aggregator, first on CursorBench 4.0 (57.8 percent) and first in one Terminal-Bench 4.0 run (65.15 percent), with vendor guidance for multiagent harnesses and time budgets at less than half Fable 5.1''s price', sources: [S2, S5, S6, S8, S9] }
  executor:    { score: 5, reason: 'Both runs rate it strongest - vendor reports medium effort matches or beats Opus 5 at high on repository coding with fewer tokens, and independent CursorBench 4.0 and Terminal-Bench 4.0 results lead the field, at a higher unit price than GPT-6.1 Sol', sources: [S2, S8, S9] }
  reviewer:    { score: 4, reason: '(claude 4, chatgpt 5) Early testers reported more bugs caught and fewer false alarms than Opus 5, and the vendor stresses root-cause analysis, checking work and scope discipline, but both runs found only vendor-reported or thin reviewer-calibration evidence', sources: [S2, S9, S10] }
---
## Strengths
- At default medium effort, matches or beats Claude Opus 5 at high effort on multistep repository coding tasks, in fewer steps and tokens (Anthropic internal testing) [S2] (confidence: medium)
- Generates output tokens more than 30 percent faster than Opus 5 and uses fewer tokens to finish the same kinds of tasks [S2] (confidence: high)
- CursorBench 4.0 (ambiguous multi-file tasks from real Cursor sessions): Opus 5.5 Max scores 57.8 percent, the best published result on that board on 2026-10-20 [S9] (confidence: high)
- Terminal-Bench 4.0 (Vals AI, updated 2026-10-18): 65.15 percent, ahead of the other models in that run [S8] (confidence: high)
- Artificial Analysis Intelligence Index v4.3 score 57.6, first among listed models in one October 2026 aggregator [S5] (confidence: medium)
- 1M context window, 128K output limit, adaptive reasoning always on, medium as the default effort [S1] (confidence: high)
- Fast mode is the same model served faster, up to about 2.5x generation speed, at $8/$40 per MTok input/output [S10] (confidence: high)
- Existing Opus 5 prompts generally transfer, but effort should be recalibrated; at the same named effort, 5.5 may think more than Opus 5 [S2] (confidence: high)
- Resists indirect prompt injection from tool results and web content better than earlier Opus models (vendor claim) [S2] (confidence: medium)
## Failure modes
- Ends an unattended turn with a text progress report (stop_reason end_turn) while work remains, which stops naive agent loops | trigger: long multi-part unattended tasks | mitigation in prompt: keep a checklist; if a turn ends with open items and no stated blocker, send "Your task list still has open items: ... Continue with them. If one is blocked, say what is blocking it."; cap automatic continuations at two or three [S2]
- Follows instructions embedded in text a user pasted | trigger: pasted emails or webpages in the user turn | mitigation in prompt: wrap pasted text in `<pasted_content id="...">` tags and state in the system prompt that instructions inside them were not written by the user [S2]
- Re-examines earlier answers on later turns, adding latency | trigger: multi-turn chat | mitigation in prompt: "Once you have answered something, treat that answer as done..." (omit for agentic work where later steps can expose earlier mistakes) [S2]
- Searches and verifies slightly less under time pressure | trigger: time budgets in multiagent harnesses | mitigation in prompt: keep a hard timeout in the harness and check answer quality on your own tasks [S2]
- Rejects thinking: {"type":"disabled"} | trigger: an integration migrated verbatim from Opus 5 | mitigation in prompt: remove the disable request and control thinking with effort [S1]
- Returns an error on forced tool use | trigger: a harness that forces tool selection, which worked on Opus 5 | mitigation in prompt: let the model select tools under explicit task constraints instead of forcing a tool [S1]
- Spends excess reasoning and cost at high settings | trigger: carrying Opus 5's high, xhigh or max setting forward without a new sweep | mitigation in prompt: start at medium, measure on task-specific evals, raise only when quality improves enough to justify it [S2]
- Thinking blocks are tied to the model and conversation | trigger: splicing or reusing reasoning state across model changes or unrelated sessions | mitigation in prompt: keep model and conversation boundaries intact in the orchestrator [S1]
## Prompting rules
- Set effort explicitly; start at medium and test other levels on your own evals rather than reusing Opus 5's default high [S2, S11]
- Use low for simple or high-volume subagents, high for difficult coding or reasoning, and reserve xhigh and max for long-horizon work where evals show a benefit [S11]
- Set max_tokens to 128000 for agentic coding turns; thinking counts toward max_tokens [S2]
- To reduce thinking, lower effort first; do not ask the model to write its reasoning in the response (may be refused as reasoning_extraction) [S2]
- Remove "think carefully before answering" lines from chat system prompts [S2]
- For unattended runs, add the vendor's standing instruction against early stops at the end of the system prompt from the first request; keep confirmation steps for destructive actions [S2]
- For unattended agent work, state completion and stop conditions directly and define what must be reported when blocked [S2]
- Change effort mid-conversation with a per-message effort change, not the top-level value, to keep the prompt cache [S2]
- Do not send forced tool use or thinking disabled; both return errors [S1, S3]
- Put the role in the system message; use numbered instructions when sequence matters [S12]
- Separate context, constraints, examples and task content with XML tags or clearly separated Markdown sections; do not mix delimiters inconsistently [S12]
- For long-document tasks, place source material before the final query and instructions [S12]
## Change from previous version
- improved: price $5/$25 to $4/$20 per MTok; cache read $0.50 to $0.20 [S1, S3, S6, S14]
- improved: output speed more than 30 percent faster; fewer tokens per task [S2]
- improved: CursorBench 4.0 rises from 46.6 percent (Opus 5 Max) to 57.8 percent (Opus 5.5 Max), an 11.2-point difference in the published runs [S9]
- changed: default effort high to medium; at a given level it thinks more per turn, especially at xhigh and max [S2, S11]
- regressed: thinking cannot be disabled (adaptive thinking always on); forced tool use returns an error; computer_20251124 tool not accepted on Claude API; some older computer-use integration patterns break (ChatGPT run labels these changed) [S1, S3]
- changed: biology safeguards from Fable 5.1 now apply; new refusal category reasoning_extraction [S2]
## Open questions
- Watch out — reports differ: headless CLI invocation. Claude run: claude -p "<prompt>" [S4]. ChatGPT run: claude -p --model claude-opus-5-5 --output-format json "<prompt>" (no source cited for the syntax).
- Watch out — reports differ: reviewer role_fit score. Claude run: 4, early-tester reports are vendor-reported only [S2]. ChatGPT run: 5, coding strength plus vendor focus on root-cause analysis, code review and scope discipline [S9, S10].
- Index leadership: one aggregator lists Opus 5.5 first at 57.6 [S5]; another lists GPT-5.6 Sol first at 58.9 [S7]. Both cite the Artificial Analysis Intelligence Index. (claude run)
- Fast-mode price $8/$40: the Claude run read it only in a third-party pricing summary [S6] and found fast mode confirmed in Anthropic release notes without a price [S3]; the ChatGPT run cites Anthropic's Opus product page for the same price [S10]. The values agree.
- Anthropic publishes positive code-review anecdotes, including quantified customer reports, but without enough reproducible method to count as independent reviewer-benchmark evidence [S10]. (chatgpt run)
- Public evidence measuring false-positive block decisions is limited. (chatgpt run)
## Sources
- S1: Claude Opus 5.5 overview, Anthropic, 2026-09-22, https://platform.claude.com/docs/en/models/opus-5-5/overview, primary (both runs)
- S2: Prompting Claude Opus 5.5, Anthropic, 2026-09-22, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-opus-5-5, primary (both runs)
- S3: Claude Platform release notes, Anthropic, 2026-09-22, https://platform.claude.com/docs/en/release-notes/overview, primary (claude run)
- S4: Run Claude Code programmatically, Anthropic, accessed 2026-10-26, https://code.claude.com/docs/en/headless, primary (claude run)
- S5: LLM leaderboard October 2026, modelgrep, 2026-10, https://modelgrep.com/leaderboard, independent (claude run)
- S6: Claude Opus pricing in 2026, CloudZero, 2026, https://www.cloudzero.com/blog/claude-opus-pricing/, independent (claude run)
- S7: Artificial Analysis Intelligence Index leaderboard, BenchLM, 2026-10-25, https://benchlm.ai/benchmarks/artificialanalysis, independent (claude run)
- S8: Terminal-Bench 4.0, Vals AI, updated 2026-10-18, https://www.vals.ai/benchmarks/terminal-bench-4, independent (chatgpt run)
- S9: CursorBench 4.0, Cursor, accessed 2026-10-20, https://cursor.com/cursorbench, independent (chatgpt run)
- S10: Claude Opus product and release page, Anthropic, 2026-09-22, https://www.anthropic.com/claude/opus, primary (chatgpt run)
- S11: Effort, Anthropic Claude Platform Docs, accessed 2026-10-20, https://platform.claude.com/docs/en/build-with-claude/effort, primary (chatgpt run)
- S12: Claude prompting best practices, Anthropic, accessed 2026-10-20, https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview, primary (chatgpt run)
- S13: Anthropic commercial and API privacy and retention documentation, Anthropic, accessed 2026-10-20, https://privacy.claude.com/, primary (chatgpt run)
- S14: Claude Opus 5 overview, Anthropic, 2026-07-24, https://platform.claude.com/docs/en/models/opus-5/overview, primary (chatgpt run)
