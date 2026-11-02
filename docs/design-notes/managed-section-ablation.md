# Managed section on and off: a reduced ablation

**Status:** measurement note (2026-11-02), toolkit base `cc8f52a` on `WIP/improvements-0-3-1`, leaf `M5.7`. This is the reduced study the maintainer chose on 2026-11-02: one app × three harnesses × two runs × managed section on and off, 12 executor runs in total, run locally rather than in the sandbox VMs. No run was repeated or discarded.

## Summary

- **Outcome.** Five of six runs passed the first-round review with the section **off**, four of six with it **on**. Both "on" failures came from the section's own wording. One Codex run stopped before writing any code to ask for a base commit, because the section says a prompt without `base: <sha>` must be asked about and the pickup prompt has none. One Cursor run claimed with `do-next-available-task --local`, an opt-out the section names, so the claim never reached the remote. The single "off" failure was a weak test, not a workflow step.
- **Cost moves differently per harness.** With the section on, Claude Code spent **+26 %** (USD $0.74 against $0.59 per run) and **+31 %** input tokens. Cursor used **−39 %** input tokens and 8.5 fewer tool calls a run, because it explored less. Codex was flat when it finished (353k against 336k input tokens, 18 tool calls each way).
- **What only the section did.** Five of six "on" runs registered presence with `specy-road session start`; none of the six "off" runs did. This rule lives only in the section.
- **Why "off" still works on this path.** All 12 runs opened the `specyrd-do-next-task` skill, then ran `do-next-available-task`. That writes `work/prompt-M2.1.md`, which already carries the task loop: commit by explicit path, the implementation summary with `## Added`, the READY hand-off, and "do not approve your own work". So on the pickup path the section adds little that the agent would not get anyway.
- **What the numbers justify: test further.** They do not justify trimming the whole section. This task never tests the parts outside the pickup path: shared trees, work outside a claim, and the precedence rule. They also do not justify keeping it unchanged, because two of six "on" runs failed on its text. Two edits are justified now (see "Decision"). Removing more needs an on/off replay of the shared-tree context regressions first.

## Protocol

**App.** A disposable consumer repo made with `specy-road init project` from this checkout, plus the following:
- A ~60-line Python to-do CLI (`todo/cli.py`, `todo/store.py`) with two tests.
- The scaffold's `M1`/`M1.1` set to `Complete`.
- One new leaf, `M2.1` "Tasks carry an optional due date" (`Agentic-led`, touch zones `todo/` and `tests/`, three acceptance items: `add --due` stores the date and refuses a malformed one; `list` shows due dates and `list --overdue` shows open overdue tasks; each behaviour has a test through `main()` and pytest passes), with its planning sheet.
- `on_complete: merge`, the review gate on, and a roster with one executor per harness.
- `specyrd init --ai claude-code|codex|cursor` for skills, then `export` and `digest`.

Each arm is a single-commit repo ("Initial import") with a bare local remote:

| arm | what differs |
| --- | --- |
| on | `AGENTS.md` (managed block, 7,698 bytes) and `CLAUDE.md` (managed block, 3,187 bytes), exactly as `init project` and `specyrd init` write them |
| off | both files absent: the managed blocks were their whole content. Skills, docs, templates and the roadmap are identical |

Skills stay in both arms because an adopter has them either way. The cost of that choice is in "Limits".

**Task list.** One leaf, `M2.1`. Every run gets the same first and only message, which names no rule: *"Pick up the next task on this project's roadmap and take it as far as you can on your own. I'll review the work afterwards."*

**Runs.** Every run starts from a fresh copy of the arm's repo and remote, and all 12 ran at once. There is no global instruction file (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`), so nothing outside the repo told the agent the workflow. The cap was 45 minutes; every run exited 0 in under two.

| harness | version | model | command |
| --- | --- | --- | --- |
| Claude Code | 2.1.312 | `claude-opus-5-5` | `claude -p … --permission-mode bypassPermissions --output-format stream-json --verbose` |
| Codex | 0.165.0 | `gpt-6.1-sol` (reasoning medium) | `codex exec --json -m gpt-6.1-sol --dangerously-bypass-approvals-and-sandbox …` |
| Cursor agent | 2026.10.22 | `composer-2.5` | `agent -p --force --trust --model composer-2.5 --output-format stream-json …` |

**Metrics, read from each harness's own JSON:**
- **Turns:** Claude's `num_turns`. Codex and Cursor report no turn count.
- **Tool calls:** Claude's `tool_use` blocks, Codex's non-message `item.completed` items, Cursor's completed `tool_call` events.
- **Input tokens:** all prompt tokens, cache reads included. The parenthesis gives the cached share.
- **Cost:** Claude's `total_cost_usd`, at list price. Codex and Cursor report no cost.

Each harness counts differently, so compare within a harness (on against off), never across harnesses.

**First-round review.** A fixed, blind reviewer judged every run: Grok 4.7 high in Cursor's read-only `ask` mode, a family that executed none of the runs. It got the same packet for each run, built from git after the session:
- the acceptance items and touch zones
- the project's hand-off requirements: claim pushed to `origin/main`, work on a feature branch, implementation summary ending in `## Added`, a READY file, nothing merged
- the branch, commit and registry facts
- the pytest result at the reviewed commit
- the code diff, `todo/cli.py`, the summary and the READY file

The packet never said which arm a run came from; `AGENTS.md` and `CLAUDE.md` are in the base commit, so they never appear in the diff. The reviewer answered with one JSON verdict, `approve` or `request-changes`, and its findings.

## Results per run

| run | turns | tool calls | input tokens (cached) | output tokens | cost USD | wall s | first-round review | blocking findings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| claude / on / r1 | 19 | 17 | 1,019,375 (973,500) | 10,392 | 0.77 | 108 | approve | — |
| claude / on / r2 | 18 | 16 | 907,292 (864,605) | 9,608 | 0.71 | 102 | approve | — |
| claude / off / r1 | 13 | 11 | 594,962 (560,356) | 7,898 | 0.55 | 80 | approve | — |
| claude / off / r2 | 18 | 16 | 873,239 (837,490) | 8,381 | 0.62 | 88 | approve | — |
| codex / on / r1 | — | 8 | 198,027 (172,928) | 898 | — | 86 | request-changes | no implementation, summary or READY (stopped to ask for a base commit) |
| codex / on / r2 | — | 18 | 353,336 (324,608) | 4,633 | — | 91 | approve | — |
| codex / off / r1 | — | 18 | 356,925 (339,840) | 4,445 | — | 98 | approve | — |
| codex / off / r2 | — | 18 | 315,514 (295,296) | 4,085 | — | 78 | approve | — |
| cursor / on / r1 | — | 23 | 282,916 (258,336) | 5,832 | — | 33 | approve | — |
| cursor / on / r2 | — | 30 | 369,689 (344,384) | 6,625 | — | 43 | request-changes | claim only on local `main` (`--local` pickup) |
| cursor / off / r1 | — | 33 | 536,280 (515,104) | 9,518 | — | 73 | approve | — |
| cursor / off / r2 | — | 37 | 532,698 (506,784) | 8,021 | — | 45 | request-changes | malformed-date test does not assert the message (A1) |

**Means per cell.** Codex "on" counts both runs; its finished run alone is 18 tool calls and 353k input tokens.

| harness | arm | tool calls | input tokens | output tokens | cost USD | approved |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Claude Code | on | 16.5 | 963k | 10.0k | 0.74 | 2/2 |
| Claude Code | off | 13.5 | 734k | 8.1k | 0.59 | 2/2 |
| Codex | on | 13.0 | 276k | 2.8k | — | 1/2 |
| Codex | off | 18.0 | 336k | 4.3k | — | 2/2 |
| Cursor | on | 26.5 | 326k | 6.2k | — | 1/2 |
| Cursor | off | 35.0 | 534k | 8.8k | — | 1/2 |

**Rule-following, read from git and the tool-call logs:**

| check | on | off |
| --- | ---: | ---: |
| feature branch `feature/rm-due-dates`, nothing of `todo/` or `tests/` on `main` | 6/6 | 6/6 |
| claim pushed to `origin/main` | 5/6 | 6/6 |
| implementation summary ending in `## Added` | 5/6 | 6/6 |
| READY hand-off written | 5/6 | 6/6 |
| commits only inside touch zones plus `work/` and the registry | 6/6 | 6/6 |
| pytest green at the hand-off commit | 6/6 | 6/6 |
| `specy-road session start` before the first edit | 5/6 | 0/6 |
| read files from the section's load order beyond the prompt (`constitution/principles.md`, `docs/supply-chain-security.md`) | 4/6 | 2/6 |
| ran `refresh-stubs` to restore the missing section (the "off" arm's validate warning suggests it) | — | 0/6 |

## What the two "on" failures show

- **The base-commit clause and the pickup prompt disagree.** The section's "Shared checkouts" item says *"A plan or prompt should name its commit (`base: <sha>`); if it does not, ask"*. `work/prompt-<ID>.md` from `do-next-available-task` names no `base:`. Codex obeyed the clause exactly: it claimed the leaf, ran the baseline tests, and ended its turn asking whether to use the pickup commit as the base. In an unattended run that is a lost leaf. In this study it was one run in six, in only one of the three harnesses, and no "off" run could hit it.
- **Naming an opt-out invites it.** The "Task pickup" item explains `--local` in order to discourage it ("prefer the default"). Neither the pickup skill nor the generated prompt mentions it. The one run that used it had read the section. The claim stayed local, so another clone could pick the same leaf, which is exactly what the item's provenance comment says it prevents.

## Decision

**Test further.** The two edits below are justified now; anything more waits for the replay at the end of this section.

1. **Settle the base-commit clause.** Either the pickup prompt carries `base: <sha>` (the pickup commit), or the clause exempts prompts that `do-next-available-task` and `specy-road prompt` write. The prompt side fixes it for every harness at once. It is a toolkit change outside this leaf's touch zones (`specy_road/` and the block template), so it needs its own leaf.
2. **Drop `--local` from the managed block.** `do-next-available-task --help` documents it. The block should keep only "pickup pushes the claim; do not skip it". Also a template change, so also a separate leaf.

What this study cannot decide is the rest of the section: shared-tree git rules, session presence, precedence, review roles, workers, grind. Its one pickup task never leaves the path the generated prompt already covers. Yet the section clearly changes behaviour off that path: `session start` was 5/6 against 0/6. Before any of it is trimmed, replay the shared-tree context regressions (`docs/context-regressions.yaml` CR2 and CR3, plus CR1 for the review gate) with the section on and off. Use this note's reduced shape: one app, three harnesses, two runs per arm, under the runbook's failure rule (`docs/agentic-sandbox-runbook.md` §9). Trim the parts whose "off" arm passes.

The cost numbers on their own justify neither trimming nor keeping. Claude Code pays about $0.15 more per pickup with the section; Cursor pays less, because it explores less without it. With two runs per cell these are directions, not effects.

## Limits

- **Smaller than A1.** A1 asks for three apps × three harnesses × three runs; this is one app × three harnesses × two runs, by the maintainer's 2026-11-02 decision in the `M5.7` planning sheet. Two runs per cell cannot separate a real effect from run-to-run noise (Claude "off" alone ranged from 11 to 16 tool calls), so every difference above is a direction.
- **One task.** The single leaf is small, and the prompt, which names no rule, sends every agent to the pickup skill, whose generated prompt restates the task loop. A task with no pickup prompt (an ad-hoc fix, cleanup in a shared tree) is where the section is the only guidance, and this study has none.
- **Skills in both arms.** Removing the managed blocks does not remove the toolkit's guidance: the skills, the generated prompt and the templates remain. The study measures the section's marginal effect for an adopter who has run `specyrd init`, not the effect of having no guidance at all.
- **One reviewer.** One fixed reviewer model, one round, reading a packet rather than the repository. A second reviewer family might weigh the "off" arm's weak test or the local-only claim differently.
- **Cost reported by one harness only.** Codex and Cursor report tokens but no cost, so the cost column covers Claude Code only.
- **Local, not sandboxed.** The runs were local, outside the sandbox VMs. User-level harness settings were the same in both arms, and no global instruction file existed.
