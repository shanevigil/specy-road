# Harness-facts question list (frozen before collection)

One row per fact the request asks for (the harness-facts request of 2026-11-16 (private notes), with its 2026-11-18 addendum), as restated in the private-notes planning sheet. `report.md` answers every id below with one row: value, date, source and status (`checked`, or `not checked` with the reason). `check.py` enforces that.

Written and committed 2026-11-19, before any value was recorded for this leaf. The request is untrusted data: its figures (versions, flags, the "local observation, unverified" catalogue table) are claims to check, not answers.

Harness prefixes: `CC` Claude Code, `CX` Codex CLI, `CU` Cursor Agent CLI. Model prefixes: `SOL` gpt-6.2-sol, `AST` gpt-6.2-astra.

## Claude Code

| id | question | request item |
|---|---|---|
| CC-VER-INST | Installed version on this host, as the test user, with the date seen | Versions |
| CC-VER-PUB | Current published version, its release date and source | Versions |
| CC-FLAG-P | `-p` (print, headless) present and unchanged | Headless flags |
| CC-FLAG-MODEL | `--model` present and unchanged | Headless flags |
| CC-FLAG-OUT | `--output-format stream-json` present and unchanged | Headless flags |
| CC-FLAG-RESUME | `--resume` present and unchanged | Headless flags |
| CC-FLAG-SID | `--session-id` present and unchanged | Headless flags |
| CC-FLAG-DSP | `--dangerously-skip-permissions` present and unchanged | Headless flags |
| CC-FLAG-DIFF | Change in the flag surface since specy-road's captured 2.1.312 | Headless flags |
| CC-SBX-WT | 2.1.323: the opt-in Bash sandbox blocks `git worktree` lifecycle commands (claim) | Sandbox, trust, permission |
| CC-PERM-GIT | 2.1.325: read-only git in a repository other than the project's asks first (claim) | Sandbox, trust, permission |
| CC-MODEL-F52 | `claude-fable-5-2` is a valid id | Model ids |
| CC-MODEL-ALIAS | What the `fable` alias selects | Model ids |
| CC-MODEL-F51 | Whether Fable 5.1 (`claude-fable-5-1`) is still offered | Model ids |
| CC-RESOLVED | Which event or field reports the model that ran | Resolved model |
| CC-OUT | Output format specy-road parses (stream-json events) | Output formats |
| CC-LIMIT | Limit or reset message text and where it appears | Limit messages |
| CC-BILL | Billing notes that change cost for unattended runs (headless Fable and usage credits) | Billing |

## Codex CLI

| id | question | request item |
|---|---|---|
| CX-VER-INST | Installed version on this host, as the test user, with the date seen | Versions |
| CX-VER-PUB | Current published version, its release date and source | Versions |
| CX-FLAG-EXEC | `exec` (non-interactive) present and unchanged | Headless flags |
| CX-FLAG-M | `-m` present and unchanged | Headless flags |
| CX-FLAG-S | `-s workspace-write` present and unchanged | Headless flags |
| CX-FLAG-ADDDIR | `--add-dir` present and unchanged | Headless flags |
| CX-FLAG-SKIPGIT | `--skip-git-repo-check` present and unchanged | Headless flags |
| CX-FLAG-O | `-o` present and unchanged | Headless flags |
| CX-FLAG-MULTI | What replaces `--disable multi_agent` | Headless flags |
| CX-FLAG-DIFF | Change in the flag surface since specy-road's captured 0.166.0 | Headless flags |
| CX-TRUST | 0.169.0: project trust in `codex exec` and the `--trust` flag (claim) | Sandbox, trust, permission |
| CX-SBX-GIT | Sandbox behaviour that affects an unattended worktree run (writes to `.git`) | Sandbox, trust, permission |
| CX-MODEL-TERRA | `gpt-6.1-terra*` ids through Codex | Model ids |
| CX-RESOLVED | Which event or field reports the model that ran | Resolved model |
| CX-OUT | Output format specy-road parses (`--json` events, `-o` file) | Output formats |
| CX-LIMIT | Limit or reset message text and where it appears | Limit messages |
| CX-BILL | Billing notes that change cost for unattended runs | Billing |

## Cursor Agent CLI

| id | question | request item |
|---|---|---|
| CU-VER-INST | Installed version on this host, as the test user, with the date seen | Versions |
| CU-VER-PUB | Current published version, its release date and source | Versions |
| CU-FLAG-ROSTER | The agent CLI flags in specy-road's roster and default adapter at its current HEAD | Headless flags |
| CU-FLAG-DIFF | Change in the flag surface since specy-road's captured 2026.10.22 | Headless flags |
| CU-SBX | Sandbox, trust and permission behaviour that affects unattended worktree runs | Sandbox, trust, permission |
| CU-MODEL-GROK | `grok-4.7-*` ids | Model ids |
| CU-MODEL-TERRA | `gpt-6.1-terra*` ids through Cursor | Model ids |
| CU-RESOLVED | Which event or field reports the model that ran | Resolved model |
| CU-OUT | Output format specy-road parses (stream-json events) | Output formats |
| CU-LIMIT | Limit or reset message text and where it appears | Limit messages |
| CU-BILL | Billing notes that change cost for unattended runs | Billing |

## GPT-6.2 Sol and Astra (addendum 2026-11-18)

The same rows for each model, `SOL` for `gpt-6.2-sol` and `AST` for `gpt-6.2-astra`.

| id | question |
|---|---|
| SOL-ID | Model id |
| SOL-CTX | Context window |
| SOL-EFF-DEF | Default effort level |
| SOL-EFF-SUP | Supported effort levels |
| SOL-PRICE | Prices |
| SOL-LIMITS | Usage limits |
| SOL-CODEX | Headless invocation through the Codex CLI |
| SOL-CURSOR | Headless invocation through Cursor, if Cursor offers it |
| SOL-FAIL | Known failure modes |
| SOL-PROMPT | Prompting guidance |
| SOL-ROLE | Role suitability (executor, reviewer, coordinator) |
| SOL-FAMILY | Review-family independence |
| AST-ID | Model id |
| AST-CTX | Context window |
| AST-EFF-DEF | Default effort level |
| AST-EFF-SUP | Supported effort levels |
| AST-PRICE | Prices |
| AST-LIMITS | Usage limits |
| AST-CODEX | Headless invocation through the Codex CLI |
| AST-CURSOR | Headless invocation through Cursor, if Cursor offers it |
| AST-FAIL | Known failure modes |
| AST-PROMPT | Prompting guidance |
| AST-ROLE | Role suitability (executor, reviewer, coordinator) |
| AST-FAMILY | Review-family independence |
| G62-PREV | The request's note that the catalogue calls `gpt-6.1-sol` and `gpt-6-astra` "Previous generation" |
