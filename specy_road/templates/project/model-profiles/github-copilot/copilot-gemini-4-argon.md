---
profile_schema: 2
family: Google Gemini
track: Argon (Gemini 4 frontier tier), run through GitHub Copilot CLI as a one-shot reviewer
model: Gemini 4 Argon on GitHub Copilot CLI (candidate reviewer)
api_id: copilot-gemini-4-argon
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
  cli: copilot -p "<prompt>" -s --no-ask-user --no-auto-update --model=gemini-4-argon --allow-tool='shell,write' --deny-tool='shell(git push),shell(git push:*),shell(git commit),shell(git commit:*),shell(gh),shell(gh:*),memory'
  cli_verified_from: unverified
  subagents: 'unknown --fleet runs parallel subagents and is never passed here; whether a -p run without it spawns subagents is not documented [S1]'
  effort_controls: 'copilot --effort low, medium, high, xhigh, max; not passed, so the model default applies [S1]'
runtime_checks: 'not run: Copilot CLI is not installed; the maintainer decided on 2026-11-02 to write this profile from vendor documentation only (see ## Runtime checks)'
cost_usd_per_mtok: { input: unknown, output: unknown, cached_input: unknown }
data_handling: 'Prompts and completions pass through GitHub Copilot content filters [S3]. Retention and training terms for Copilot CLI sessions were not researched; see google-gemini/gemini-4-argon.md for the model itself.'
role_fit:
  coordinator: { score: 1, reason: 'One-shot only: Copilot -p with --resume is undocumented, so a coordinator turn cannot continue a session; not run', sources: [S5] }
  executor:    { score: 1, reason: 'Not an executor until -p with --resume and commit-when-asked are verified at runtime; this profile denies git commit; not run', sources: [S5] }
  reviewer:    { score: 3, reason: 'The Gemini 4 Argon reviewer score (no published review evaluation; a vendor outside Anthropic and OpenAI); Copilot adds deny rules that win over allow rules; not run', sources: [S6, S1] }
---
## Strengths
- One harness reaches models from several vendors by name with --model, so a roster can add a `google` reviewer without a Google harness [S2, S3, S5] (confidence: high)
- Deny rules always take precedence over allow rules, even when --allow-all is set, so the git push, git commit and gh denials hold whatever else is granted [S1] (confidence: high)
- -p runs the prompt and exits; -s prints only the agent's response, without usage statistics [S1, S2] (confidence: high)
- --no-ask-user disables the ask_user tool, so the run never pauses for input [S1] (confidence: high)
- Malformed --allow-tool and --deny-tool patterns are rejected with an error (changelog), so a typo in the deny list fails the launch instead of allowing everything [S4] (confidence: medium)
- Gemini 4 Argon support was added in Copilot CLI 1.0.98 (2026-10-14) [S4] (confidence: high)
## Failure modes
- A denied shell pattern can miss a command with arguments | trigger: shell(git push) names the exact command; the vendor table shows shell(npm test) allowing only the exact command | mitigation in prompt: the command passes both shell(X) and shell(X:*), since :* matches the command stem followed by a space [S1, S2]
- The exit code is not a verdict | trigger: Copilot documents no exit codes for -p (only for copilot workflow run); a prompt blocked before responding exits non-zero (changelog), and prompt mode exits successfully when a child task fails but the parent recovers | mitigation in prompt: judge the run by the REVIEW-<model>.md it filed through specy-road review record, never by the exit status [S2, S4, S5]
- A request that needs approval is denied in a non-interactive run | trigger: a tool outside --allow-tool, or a path outside the working directory | mitigation in prompt: shell and write are allowed for the review re-run and the notes file; filing into the main checkout's work/reviews from a linked worktree is not verified (see Runtime checks) [S2]
- A silent model change | trigger: an id Copilot does not list, or a plan or organization policy without the model | mitigation in prompt: the model is pinned with --model=gemini-4-argon; what Copilot does with an id it does not offer is not documented, and auto is never passed [S1, S3]
- An automatic CLI update changes flags between a verified run and the next | trigger: Copilot downloads updates by default | mitigation in prompt: --no-auto-update keeps the version the runtime checks are run against [S1, S2]
## Code and test tendencies
- No measured code-shape or test data for this harness in either lean-code report (2026-10-27); the pinned model's measured tendencies are in google-gemini/gemini-4-argon.md (researched 2026-10-27 from the lean-code reports, not human-verified) [S6]
## Prompting rules
- Run this profile on the `generic` harness with roster role reviewer only; it is a one-shot run that cannot resume [S5]
- Never add --autopilot, --share-gist, --share, --fleet, --plan, --allow-all, --allow-all-tools or --yolo to this command: autopilot keeps working until task_complete, --share-gist publishes the session to a gist, and the allow-all forms grant every tool [S1]
- Keep `memory` in the deny list: it stops the reviewer storing facts in Copilot Memory, which is shared state outside the repository [S2, S5]
- The api_id is this profile's roster id, not a Copilot model id; the Copilot id is the --model value in access.cli [S1]
- Ask for the verdict through specy-road review record, as every reviewer prompt does; Copilot's own /review output is advisory and is never gate evidence [S5]
## Runtime checks
- copilot --version reports 1.0.105 or later | not run: Copilot CLI is not installed (maintainer decision 2026-11-02); 1.0.105 (2026-10-27) is the newest changelog entry [S4]
- copilot --help of that version lists -p, -s, --no-ask-user, --no-auto-update, --model, --allow-tool and --deny-tool, and the command above parses | not run: no binary; this profile is checked against the vendor command reference only [S1]
- --model=gemini-4-argon is the id Copilot accepts | not run: the id follows the changelog's form (claude-opus-5.5, gemini-3.6-flash); no vendor page prints the Argon id [S4]
- git push, git commit, git commit -m x, gh pr create and gh pr list are refused, with the report and exit code recorded | not run
- the run exits after one reply and never prompts | not run
- specy-road review record files REVIEW-<model>.md into the main checkout from a linked worktree | not run
- which instruction files load (AGENTS.md, .github/copilot-instructions.md, others) by sentinel lines | not run [S5]
## Open questions
- Watch out — exit codes: Copilot documents exit codes only for copilot workflow run (0, 1, 2, 130); for -p the changelog says a prompt blocked before responding exits non-zero and a parent that recovers from a failed child task exits successfully [S2, S4].
- Whether shell(git push) alone denies git push origin main, or only the bare command, is not stated; both forms are passed [S1, S2].
- Whether -p with --resume continues a session is undocumented; until it is verified this profile is a reviewer only [S5].
## Sources
- S1: GitHub Copilot CLI command reference, GitHub Docs, read 2026-11-03, https://docs.github.com/en/copilot/reference/cli-command-reference, primary
- S2: GitHub Copilot CLI programmatic reference, GitHub Docs, read 2026-11-03, https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-programmatic-reference, primary
- S3: Supported AI models in GitHub Copilot, GitHub Docs, read 2026-11-03, https://docs.github.com/en/copilot/reference/ai-models/supported-models, primary
- S4: GitHub Copilot CLI changelog, github/copilot-cli, read 2026-11-03 (newest entry 1.0.105, 2026-10-27), https://github.com/github/copilot-cli/blob/main/changelog.md, primary
- S5: Harness compatibility triage (research of 2026-10-28), specy-road, docs/design-notes/harness-compatibility-triage.md, secondary
- S6: Gemini 4 Argon profile, specy-road, model-profiles/google-gemini/gemini-4-argon.md, secondary
