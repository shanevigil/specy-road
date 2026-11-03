---
profile_schema: 2
family: Google Gemini
track: Argon (Gemini 4 frontier tier), run through Antigravity CLI (agy) on the generic harness
model: Gemini 4 Argon (High) on Antigravity CLI (candidate generic)
api_id: agy-gemini-4-argon-high
checkpoint: unknown
alias_moves: unknown
version_rank: latest
release_date: 2026-10-13
researched: 2026-11-03
researcher: claude (M8.6, vendor documentation only)
supersedes: none
access:
  context_tokens: unknown
  output_tokens: unknown
  cli: agy -p "<prompt>" --output-format json --print-timeout 60m --model gemini-4-argon-high
  cli_verified_from: unverified
  subagents: 'unknown agy runs subagents (stream-json steps carry subagent_info); whether a print-mode run spawns them on its own is not documented [S1]'
  effort_controls: 'agy --effort low, medium, high, or a model slug that carries the level (gemini-4-argon-high); this profile pins the slug [S1, S3]'
runtime_checks: 'not run: Antigravity CLI is not installed; the maintainer decided on 2026-11-02 to write this profile from vendor documentation only (see ## Runtime checks)'
cost_usd_per_mtok: { input: unknown, output: unknown, cached_input: unknown }
data_handling: 'Not researched for Antigravity CLI; see google-gemini/gemini-4-argon.md for the model itself.'
role_fit:
  coordinator: { score: 1, reason: 'A generic worker cannot resume, interrupt or hand off, although agy itself resumes with --conversation <id>; not run', sources: [S6, S1] }
  executor:    { score: 3, reason: 'The model is the Argon executor (5), lowered because shell commands, git commit included, are soft-denied in print mode unless permissions.allow grants them, and the run still exits 0; not run', sources: [S7, S1] }
  reviewer:    { score: 3, reason: 'The Gemini 4 Argon reviewer score (no published review evaluation); the verdict channel is the envelope, not the exit code; not run', sources: [S7, S1] }
---
## Orchestration: harness features to avoid

This profile is usually rostered on `generic` or another harness; see `model-profiles/README.md` harness facts for switches when the roster names `claude-code`, `codex`, or `cursor`.

## Strengths
- Print mode (-p, --print, --prompt) sends one prompt, returns the response and exits; the response goes to stdout and diagnostics to stderr [S1] (confidence: high)
- --output-format json prints one envelope on completion with conversation_id, status, response, error (on failure), duration_seconds, num_turns and usage; stream-json prints init, step_update and a final result event of the same shape [S1] (confidence: high)
- status names the terminal state: SUCCESS, ERROR, CANCELED, INTERRUPTED, INVALID, WAITING or RUNNING [S1] (confidence: high)
- A pinned --model that agy does not know exits non-zero with an ERROR envelope instead of falling back to another model [S1] (confidence: high)
- --json-schema puts a parsed object in structured_output, a candidate verdict channel for reviewers (M8.3) [S1] (confidence: high)
- Reads AGENTS.md (or GEMINI.md) and .agents/rules/ in the workspace folder and each parent up to the repository root, cumulatively [S4] (confidence: high)
## Failure modes
- Exit 0 is not success | trigger: a tool that needs approval is soft-denied in print mode, the run continues and exits 0 with a stderr notice (since 1.1.3); a --print-timeout expiry returns partial output and exits successfully with a warning (since 1.1.28) | mitigation in prompt: read status from the JSON envelope and accept only SUCCESS; a coordinator checks the worker log for it, since a generic worker records only exit status and output lines [S1, S3]
- No commit, no tests | trigger: shell commands default to Ask and are soft-denied in print mode; only reads and writes inside the workspace are auto-allowed | mitigation in prompt: grant the commands a leaf needs as command(...) rules under permissions.allow in ~/.gemini/antigravity-cli/settings.json, never --dangerously-skip-permissions [S1]
- The run is cut short | trigger: the two vendor pages give different --print-timeout defaults (5m on the headless page, 0s meaning no limit in the reference) | mitigation in prompt: the command passes an explicit --print-timeout 60m [S1, S2]
- Empty stdout from a subprocess | trigger: builds before 1.1.1 dropped print-mode stdout when it was not a TTY and hung reading stdin in a script | mitigation in prompt: use 1.1.1 or later (the issue was closed on that fix) [S5]
- An unauthenticated run fails | trigger: print mode uses cached credentials; with no terminal it exits with an authentication error | mitigation in prompt: sign in once with an interactive agy session on the worker's machine [S1]
## Code and test tendencies
- No measured code-shape or test data for this harness in either lean-code report (2026-10-27); the pinned model's measured tendencies are in google-gemini/gemini-4-argon.md (researched 2026-10-27 from the lean-code reports, not human-verified) [S7]
## Prompting rules
- Run this profile on the `generic` harness; the worker cannot resume it, so give each turn the whole brief or review packet [S6]
- Never add --dangerously-skip-permissions (it approves every tool call) or --continue (it resumes the most recent conversation, whoever started it) to this command [S1]
- Do not run /learn, /goal or /schedule on a leaf: /learn captures corrections as persistent rules or skills, and the triage lists all three as avoid [S2, S6]
- Judge the run by the envelope's status (SUCCESS) and, for a reviewer, by the REVIEW-<model>.md it filed, never by the exit code [S1]
- The api_id is this profile's roster id, not an agy model slug; the slug is the --model value in access.cli (agy models lists them) [S1]
## Runtime checks
- agy --version is captured and recorded here | not run: Antigravity CLI is not installed (maintainer decision 2026-11-02); the research reports disagree (1.4.3 vs 1.4.10), and the vendor changelog read 2026-11-03 dates entries up to 1.4.9 (2026-10-28) while its version list also names 1.4.10 [S3]
- agy --help of that version lists -p, --output-format, --print-timeout and --model | not run [S2]
- --model gemini-4-argon-high is accepted (the slug is from the vendor page's agy models example) | not run [S1]
- a soft-denied shell command and a benign tool error exit 0 with a non-SUCCESS or SUCCESS status, recorded as observed | not run
- a --print-timeout expiry exits 0 and the status it reports | not run [S3]
- commit when asked from a nested subdirectory, with permissions.allow granting command(git) | not run
- which instruction files load by sentinel lines | not run [S4]
## Open questions
- Watch out — reports differ: the agy version. One research report gives 1.4.3, the other 1.4.10; neither was captured from a binary [S6].
- Watch out — reports differ: the --print-timeout default. The headless page says 5m; the CLI reference says 0s, waiting until the turn completes [S1, S2].
- The acceptance for this leaf dates exit 0 on permission denials and benign tool errors from 1.3.4; the vendor changelog's 1.3.4 entry does not say so, while the 1.1.3 entry introduces the soft-deny [S3].
- --mode accept-edits and --new-project, named in the 2026-10-28 triage, are not on the headless flag reference read here [S1, S6].
## Sources
- S1: Headless mode - Antigravity CLI, Google Antigravity Docs, read 2026-11-03, https://antigravity.google/docs/cli/headless, primary
- S2: Antigravity CLI reference, Google Antigravity Docs, read 2026-11-03, https://antigravity.google/docs/cli/reference/, primary
- S3: Google Antigravity changelog, Google Antigravity Docs, read 2026-11-03, https://antigravity.google/docs/changelog/, primary
- S4: Rules, Google Antigravity Docs, read 2026-11-03, https://antigravity.google/docs/rules/, primary
- S5: agy --print / -p silently drops stdout when run with a non-TTY, google-antigravity/antigravity-cli issue 76 (closed 2026-07-12, fix in 1.1.1), read 2026-11-03, https://github.com/google-antigravity/antigravity-cli/issues/76, secondary
- S6: Harness compatibility triage (research of 2026-10-28), specy-road, docs/design-notes/harness-compatibility-triage.md, secondary
- S7: Gemini 4 Argon profile, specy-road, model-profiles/google-gemini/gemini-4-argon.md, secondary
