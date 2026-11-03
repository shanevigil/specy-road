# Harness facts: the 2026-11-02 triage (M11.60)

The second harness-capabilities research run (prompt `sr/research/prompts/harness-capabilities.md`
on the toolkit line) produced two reports on 2026-11-02. The **Claude** report cites a vendor
page or repository for each fact. The **OpenAI** report has an empty source column, so its
claims were used only to choose runtime checks (K1-K23 in the M11.60 planning sheet); no
fixture row rests on it. The triage compared both reports with
`specy_road/templates/project/model-profiles/harness-facts.yaml` and numbered the fixture
changes F1-F24. M11.60 applies F1-F22; F23 (a Copilot CLI record) and F24 (an Antigravity
`agy` record) are new harness records for M8.6 and are not in this leaf.

Before a row was written, its vendor URL was opened on 2026-11-02 and the quoted sentence
checked. Where the report's only source was secondary (a blog or a third-party repository),
the row cites the vendor page or a vendor issue that says the same thing, or drops the
claim (listed under [Left out](#left-out)).

## Rows

Labels are as written in the fixture: `documented` names the vendor URL, `runtime` names the
capture or the run below.

| Row | Harness | Fixture key | Change | Label | Source |
|---|---|---|---|---|---|
| F1 | claude-code | `instruction_files` | Adds `.claude/rules/*.md` (recursive); 4 MiB skip; on-demand subdirectory files and path-scoped rules; machine-level files; `AGENTS.override.md` never read; `--bare` skips all | documented | https://code.claude.com/docs/en/memory |
| F2 | claude-code | `git_actions` | New row: auto memory (200 lines / 25 KB of `MEMORY.md`, shared by every worktree); switch `--bare`, or `autoMemoryEnabled: false` / `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` for executors | documented | https://code.claude.com/docs/en/memory |
| F3 | claude-code | `skill_dirs` | Adds `.claude/commands`, `.claude/agents`; `--agents`; `parent_tool_use_id` | documented | https://code.claude.com/docs/en/headless |
| F4 | claude-code | `hooks` | Exit 1 does not block; a timed-out hook does not block unless `onFailure: "block"` (2.1.295+); `permissionDecision: "deny"` blocks; `-p` runs project hooks with no trust prompt. Label moves from runtime to documented: the new clauses come from the vendor page, the exit-2 clause keeps its sandbox-run source | documented | https://code.claude.com/docs/en/hooks; https://code.claude.com/docs/en/headless |
| F5 | claude-code | `permission_example` | A denial does not stop the run (`permission_denied`, `permission_denials`, exit 0); `--permission-prompts none`; `--disallowedTools` prefix rules | documented | https://code.claude.com/docs/en/headless; exit 0 from the M8.7 run |
| F6 | claude-code | `quota` | `system/api_retry` fields; the reset time only in text; the exit code on a limit is contradictory across vendor issues, so read the result line and transcript | documented | https://code.claude.com/docs/en/headless; anthropics/claude-code issues 79500, 103820, 103253 |
| F7 | claude-code | `git_actions` | `-p` rejects `--bg`; new rows: `-p` waits for background work (10-minute idle cap; switches `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, `--bare`, `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`); `--cloud <session>` under `-p` queues a message; native subagents (`--disallowedTools Agent`). The `--cloud` row's label moves from runtime to documented | documented | https://code.claude.com/docs/en/headless |
| F8 | claude-code | `session_flags` | Resume by id from any directory or worktree; transcript path; 30-day retention (`cleanupPeriodDays`) | documented | https://code.claude.com/docs/en/headless; https://code.claude.com/docs/en/sessions |
| F9 | claude-code | `relationships` | `--disallowedTools`, `--json-schema`, `--settings` use; `--max-budget-usd`, `--restricted`, `--include-hook-events` complement; `--no-session-persistence`, `--fallback-model`, `--teleport`, `--environment`, `--remote-control`, `respawn` avoid | runtime | `harness-captures/claude-code/help.txt` (2.1.312) |
| F10 | codex | `version` | codex-cli 0.166.0, with the capture refreshed (see [Codex capture](#codex-capture)) | runtime | `harness-captures/codex/version.txt` |
| F11 | codex | `session_flags` | A resume carries only the conversation; 0.166.0 keeps acknowledged approvals on resume and fork; resume from a sibling worktree undocumented | documented | https://github.com/openai/codex/pull/4583; https://learn.chatgpt.com/docs/changelog |
| F12 | codex | `quota` | A usage limit's failure text names the reset ("try again in ..."); exit code on a limit unknown; read the event stream | runtime | M8.7 run (turn.failed, exit 0); message text from https://github.com/openai/codex/issues/4764 |
| F13 | codex | `git_actions` | Memories row notes memory v2 (changelog) against the fresh-home capture (`memories stable false`); switch adds `--disable memories`. New rows: `multi_agent`, `goals` (switch `--disable`), `codex queue` / `queue --resume` | documented / runtime | https://learn.chatgpt.com/docs/changelog; `harness-captures/codex/inventory-features.txt` |
| F14 | codex | `hooks` | Hooks on by default (capture: `hooks stable true`); `--dangerously-bypass-hook-trust` for one invocation | documented | https://learn.chatgpt.com/docs/hooks; `harness-captures/codex/` |
| F15 | codex | `relationships` | `queue`, `--ephemeral`, `--ignore-rules`, `goals`, `multi_agent` avoid; `agents` neutral; `--output-schema`, `--enable`, `--disable`, `hooks` use; `--dangerously-bypass-hook-trust`, `--ignore-user-config` complement | runtime | `harness-captures/codex/help.txt`, `help-exec.txt`, `inventory-features.txt` |
| F16 | codex | `permission_example`, `instruction_files` | `--full-auto` removed (use `--sandbox workspace-write`); the 32 KiB truncation is silent | runtime / documented | https://learn.chatgpt.com/docs/non-interactive-mode; https://github.com/openai/codex/issues/7138 |
| F17 | cursor | `session_flags` | Resume from any directory; concurrent `cli-config.json` writes fixed (2026.07.06) | documented | https://cursor.com/docs/cli/changelog |
| F18 | cursor | `permission_example` | `permissions.deny` tokens and files; deny over allow; `--sandbox`; `--mode ask` read-only | documented | https://cursor.com/docs/cli/reference/permissions; https://cursor.com/docs/cli/reference/parameters; `harness-captures/cursor/help.txt` |
| F19 | cursor | `instruction_files` | Nested `AGENTS.md` applies once the agent edits a file there (2026.10.22) | documented | https://cursor.com/docs/cli/changelog |
| F20 | cursor | `git_actions`, `relationships` | New rows `agent persist`, `/goal`; `persist`, `--yolo` avoid; `--mode`, `--sandbox` complement; `--add-dir` use | documented / runtime | https://cursor.com/docs/cli/changelog; `harness-captures/cursor/help.txt` |
| F21 | cursor | `model_families`, `hooks` | Fresh installs default to Auto routing; Claude Code hook configs merged; `preToolUse`/`postToolUse` fire for subagents (2026.10.17) | documented | https://cursor.com/docs/cli/changelog |
| F22 | cursor | `executor_template` | The report proposed adding `--trust`. K13 below shows `--force` alone passes a fresh worktree's trust prompt, so the template is unchanged and its label is now runtime | runtime | K13 below; https://cursor.com/docs/cli/reference/parameters |

## Runtime checks run for this leaf

All on 2026-11-02, on this machine.

| Check | Setup | Result |
|---|---|---|
| Codex capture (F10) | codex-cli 0.166.0 installed with `npm install --prefix <scratch> @openai/codex@0.166.0` (the shared `/opt/homebrew` 0.165.0 binary was left alone, since other sessions use it), run with a fresh `CODEX_HOME`, then `specy-road refresh-profiles --capture codex --accept` | Accepted. `--help` and `exec --help` are byte-identical to 0.165.0's; `features list` adds eight features, of which only `plugin_discovery_prefetch` contains a workflow word (`pr`). Control: 0.165.0's `features list` with a fresh `CODEX_HOME` was byte-identical to the accepted 0.165.0 capture, so a fresh home changes nothing in the inventory |
| K7: are Codex hooks behind a flag (F14) | Same fresh `CODEX_HOME`, `codex features list` | `hooks stable true`: on by default, as the vendor page says |
| K8, partial: Codex memory default (F13) | Same | `memories stable false` on a fresh profile, against the 0.165.0 changelog's "memory v2 by default for fresh profiles". The `-c memories.* --strict-config` turn was not run, so the v2 key names stay unknown |
| K13: does Cursor headless need `--trust` when `--force` is given (F22) | Scratch git repository with fresh linked worktrees; `agent -p --output-format json 'reply OK'`, agent 2026.10.22-27dcf5f | No flag: exit 1, "Workspace Trust Required". `--force` alone: exit 0, result `OK`. `--trust` alone: exit 0. Then a new worktree with no flag: exit 1 again, so neither run saved trust |

K13 also showed that Cursor's final JSON carries `usage` (input, output and cache tokens), which answers K12. K3 is answered by the version captures (Claude Code 2.1.312). The other K checks either need an exhausted or throttled account (K1, K9), cost model turns on disputed facts no F row depends on (K2, K4-K6, K10, K11, K14, K17-K22), or concern harnesses this leaf does not record (K15, K16, K23).

## Workflow words

`WORKFLOW_WORDS` in `specy_road/harness_facts.py` also watches `goal`, `loop`, `queue`,
`persist`, `gist`, `fleet`, `teleport`, `remote` and `spawn`: the names the reports give for
the newer autonomy features (durable goals, scheduled loops, message queues, persistent
sessions, gist sharing, fleets, teleport and remote sessions, respawned background sessions).
With them, these identifiers in the accepted captures needed a relationship:

- claude-code: `--no-session-persistence`, `--remote-control`, `--teleport`, `respawn` (all avoid, F9)
- codex: `--remote`, `--remote-auth-token-env`, `remote-control`, `queue` (avoid); `goals` (avoid, F15); `remote_control` (avoid); `remote_compaction_v2`, `remote_models`, `remote_plugin`, `plugin_discovery_prefetch` (neutral)
- cursor: `persist` (avoid, F20)

## Left out

- **Claude subdirectory truncation sizes** (F1: 40,000 characters, or 150,000-200,000 on 1M-context models, from 2.1.309). The memory page says only "a smaller per-file limit", so the row says that.
- **Claude hook timeout from a blog** (F4). The vendor hooks page says the same thing, and the row cites that page.
- **Codex `exec --json` dropping rate-limit events** (F12). The only sources were third-party repositories, so the row says only that the reset is in the failure text.
- **Cursor deny rules winning over `--force`** (F18). The permissions page does not say this. The row instead quotes the parameters page, where `--force` is "Force allow commands unless explicitly denied". `--mode ask` being read-only comes from the captured `agent --help`, because the vendor page does not say it.
- **Codex resume being filtered by repository** (F11). Only the OpenAI report claims this, so it is not in the row.
