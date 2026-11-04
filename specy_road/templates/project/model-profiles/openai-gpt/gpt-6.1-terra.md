---
profile_schema: 2
family: OpenAI GPT
track: Terra
model: GPT-6.1 Terra
api_id: gpt-6.1-terra
checkpoint: unknown
alias_moves: unknown
version_rank: latest
release_date: unknown
researched: 2026-11-03
researcher: field
supersedes: none
access:
  context_tokens: 500000
  output_tokens: unknown
  cli: codex exec --model gpt-6.1-terra --disable memories --disable multi_agent --disable goals -c sandbox_mode=workspace-write -c approval_policy=never "<prompt>"
  cli_verified_from: codex-cli 0.165.0, run 2026-11-03 (pilot ran codex exec -m gpt-6.1-terra --json; workspace-write could not commit in a linked worktree)
  subagents: 'yes Codex catalog lists multi_agent_version v2 and an ultra effort described as maximum reasoning with automatic task delegation [S2]'
  effort_controls: 'low, medium, high, xhigh, max, ultra (catalog default low; the pilot ran medium) [S2]'
  effort_map: { minimal: low, low: low, medium: medium, high: high, max: max }
data_handling: 'Served in Codex; the Codex catalog marks it supported_in_api [S2]. Retention, training use and residency were not researched for this model.'
role_fit:
  coordinator: { score: 3, reason: 'Not piloted as a coordinator; no evidence either way', sources: [] }
  executor:    { score: 4, reason: 'Two of two reviewed replays of small landed leaves were approved first round by Grok and an Anthropic reviewer, in less wall time and with smaller diffs than the landed Opus turns; reviewers rated its tests thinner, and n is two', sources: [S1] }
  reviewer:    { score: 3, reason: 'Not piloted as a reviewer; same openai family as the Sol reviewers, so it adds no family diversity to a review pair', sources: [] }
---
## Orchestration: harness features to avoid

When this model runs as a roster **executor** on `codex`, the executor template and `access.cli` below name the switches for `specy-road prompt --channel cli` and generic-harness workers. **`worker delegate` on codex will apply them when leaf M8.2 lands** (that leaf adds the `--disable` flags to the codex launch argv):

| Feature | Switch |
|---|---|
| memories | `--disable memories` |
| multi_agent | `--disable multi_agent` |
| goals | `--disable goals` |

Orchestration guard hooks deny executors `git push`, `gh pr`, worktree and cloud commands; reviewers also deny `git commit`.

In a linked worktree, `sandbox_mode=workspace-write` denies writes to the git metadata under the main checkout's `.git/worktrees/`, also when that directory is passed with `--add-dir`, so the executor cannot commit [S1]. Give a Terra executor a launch that can write it.

## Strengths
- Approved first round by both reviewers on two of two reviewed replays (M11.65, M11.77), where the landed Opus version of M11.65 needed a fix round [S1] (confidence: low, n = 2)
- Faster on the same prompts: 288 s and 211 s against 812 s and 328 s for the landed Opus first turns [S1] (confidence: low)
- Fewer output tokens on the same leaves: 5.2K and 3.7K against Opus's 14.9K and 9.7K [S1] (confidence: low)
- Reported its verifier exit codes accurately, including a test it fixed and reran [S1] (confidence: low)
## Failure modes
- Stops instead of finding an in-zone route when the obvious edit is outside the touch zones | trigger: tight zones on a file already at its file-limits cap | mitigation in prompt: "If the natural edit is outside the touch zones, first check whether a new module plus a change in a zoned file meets the acceptance; stop only if none does, and name the path." [S1]
- Collapses several acceptance cases into one test and can skip a case the acceptance wording names | trigger: an acceptance item with several conditions | mitigation in prompt: "Write one test per case the acceptance text names, including qualifiers such as 'for that commit'." [S1]
## Code and test tendencies
- Diffs were a third to a half the size of the landed Opus versions (+73/-1 and +43/-3 against +226/-5 and +130/-2), reusing existing helpers and adding none (M10.20 pilot 2026-11-03, outside the 2026-10-27 lean-code reports; not human-verified) [S1]
- Tests were leaner than the landed versions: one test per acceptance item, and once a missing case the landed tests covered; it updated no help text (M10.20 pilot 2026-11-03, outside the 2026-10-27 lean-code reports; not human-verified) [S1]
## Prompting rules
- Set effort explicitly; the Codex catalog default is low, and the pilot's approved results ran at medium [S1, S2]
- State the touch zones, the file-limits escape (a new module named in the summary) and the stop condition together, so a tight zone does not end the turn with no work [S1]
- Ask for one test per case the acceptance text names [S1]
- Set sandbox and approval policy in the harness, and in a linked worktree give it write access to the git metadata, or it cannot commit [S1]
## Open questions
- Price per token is not known here; the pilot priced it only against GPT-6.1 Sol's profile price as a ceiling [S1]
- Not offered in Cursor's agent inventory as of 2026.10.22-27dcf5f (only gpt-5.6-terra ids) [S1]
- On Codex it runs on the same ChatGPT login and usage limit as the Sol reviewers [S1]
- Behaviour on larger or multi-module leaves, as a reviewer, and through the API rather than Codex is untested
## Sources
- S1: M10.20 executor pilot (three replays of landed leaves, four reviewer runs), specy-road maintainers, 2026-11-03, findings note on the toolkit's maintainer line (not shipped), field run
- S2: Codex model catalog (`codex debug models`), codex-cli 0.165.0, captured 2026-11-03, runtime
