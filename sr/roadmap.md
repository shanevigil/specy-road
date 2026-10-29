# Roadmap index

<!-- specy-road: generated index from merged roadmap (manifest.json + chunk files) — do not edit by hand -->

Gate maps milestone execution: **Human-led** / **Agentic-led** / **Mixed**. All leaf tasks are agentic by design.

Status shown is the **computed rollup status**: for leaves, the node's own status; for non-leaves, the roll-up over leaf descendants (Complete when every leaf descendant is Complete; otherwise the most-pressing non-complete status).

| ID | Title | Type | Gate | Status |
|----|-------|------|------|--------|
| `M1` | Adopt specy-road | phase | Human-led | Not Started |
| `M1.1` | Set up the project's specy-road basics | task | Mixed | Not Started |
| `M2` | Outcome record pilot | phase | — | Not Started |
| `M2.1` | List shipped nodes with no result after N days | milestone | Agentic-led | Not Started |
| `M2.2` | Store a pointer and a human verdict for outcomes, never the metric itself | milestone | Agentic-led | Not Started |
| `M3` | 0.3.1 pre-final fixes from rc1 feedback | phase | — | Not Started |
| `M3.1` | Refuse to pick up leaves whose planning sheet is still a placeholder | task | Agentic-led | Complete |
| `M3.2` | handoff status reports review records without a claim | task | Agentic-led | Complete |
| `M3.3` | Document the canonical chunk key order and offer a deliberate normalisation | task | Agentic-led | Complete |
| `M3.4` | Brainstorm prompts: shards from the allocation, per-pass files, framing with proposed answers | task | Agentic-led | Complete |
| `M3.5` | Converge and evidence passes that cannot silently skip work | task | Agentic-led | Not Started |
| `M3.6` | Triage commands: realize, append-why, summary, consistent reasons, all-or-nothing accept | task | Agentic-led | Not Started |
| `M3.7` | promote writes usable nodes once, with short codenames | task | Agentic-led | Not Started |
| `M3.8` | Upgrade and validate report drift and migrations plainly | task | Agentic-led | Complete |
| `M3.9` | Worker and session CLI: resume permissions, roster provenance, event gaps | task | Agentic-led | Complete |
| `M3.10` | Worker hand-off, reconcile and finish report what actually happened | task | Agentic-led | Complete |
| `M3.11` | Roster ids with effort suffixes, packet path, stale sessions | task | Agentic-led | Complete |
| `M3.12` | A baseline gate runs on the integration branch before pickup | task | Agentic-led | Complete |
| `M3.13` | A trial merge with the integration branch runs before review and before finish | task | Agentic-led | Not Started |
| `M3.14` | finish-this-task and pickup detect a planning sheet that is still the scaffold | task | Agentic-led | Complete |
| `M3.15` | Read-only review commands take --ref, handoff status exit codes are distinct, review list, and an orchestration.yaml starter | task | Agentic-led | Complete |
| `M4` | Brainstorm and roadmap editing features | phase | — | Not Started |
| `M4.1` | promote carries the converge judgement into sheets and writes an authoring prompt | task | Agentic-led | Not Started |
| `M4.2` | Structured promote: target parents, clusters, minimum recommendation, plan file | task | Agentic-led | Not Started |
| `M4.3` | Batch ideas and verdicts from a file, merge, and gap ideas | task | Agentic-led | Not Started |
| `M4.4` | Policies and decisions as first-class brainstorm outcomes; frame amendments | task | Agentic-led | Not Started |
| `M4.5` | Repository files as evidence; null results; quotes on research-born ideas | task | Agentic-led | Not Started |
| `M4.6` | Lenses from the frame and a ranked node list in the recommend prompt | task | Agentic-led | Not Started |
| `M4.7` | Scriptable graph edits: apply a change file with dry run, acceptance at creation, display-id dependencies | task | Agentic-led | Complete |
| `M4.8` | list-nodes --json, refresh-stubs --diff, move-node zone rewrite | task | Agentic-led | Complete |
| `M4.9` | Opt-in auto-pick ordering by execution milestone | task | Agentic-led | Complete |
| `M4.10` | Clean up merged feature branches after finish | task | Agentic-led | Complete |
| `M4.11` | grind-session --plan keeps ready leaves with overlapping touch zones out of the same parallel wave | task | Agentic-led | Complete |
| `M4.12` | file-limits function-length check covers TypeScript and JavaScript | task | Agentic-led | Not Started |
| `M4.13` | specy-road doctor lists merged or stale feature branches, worktrees, registry rows and stashes | task | Agentic-led | Not Started |
| `M4.14` | brainstorm promote inherits execution_milestone from the anchor | task | Agentic-led | Not Started |
| `M4.15` | Session overlap warnings name the other worktree and its edit state | task | Agentic-led | Not Started |
| `M4.16` | Review rounds and elapsed time per leaf, and doctor lists detached worktrees | task | Agentic-led | Not Started |
| `M4.17` | Review-loop escalation: a root-cause analysis runs when reviews keep blocking | task | Agentic-led | Not Started |
| `M5` | Agent context and outcomes | phase | — | Not Started |
| `M5.1` | Every managed AGENTS.md rule carries its provenance in the template | task | Agentic-led | Complete |
| `M5.2` | validate flags specy-road commands that do not exist in the consumer's agent files | task | Agentic-led | Not Started |
| `M5.3` | validate reports always-injected context per harness against documented limits | task | Agentic-led | Complete |
| `M5.4` | Rules the CLI or hooks enforce shrink to one-line pointers in the managed block | task | Agentic-led | Not Started |
| `M5.5` | A replayable context regression set for the sandbox runbook | task | Mixed | Complete |
| `M5.6` | Pilot the context-feedback question in the sandbox before shipping it | task | Mixed | Not Started |
| `M5.7` | Measure the managed section on and off across the sandbox apps | task | Human-led | Not Started |
| `M6` | 0.3.1-rc2 release | phase | — | Not Started |
| `M6.1` | Close out the triage note, changelog and what's-new for rc2 | task | Agentic-led | Not Started |
| `M6.2` | Pre-release checks and the 0.3.1-rc2 cut | task | Human-led | Not Started |
| `M7` | Keeping current: recurring research | phase | — | Not Started |
| `M7.1` | A research register tracks deep-research topics with a refresh cadence | task | Agentic-led | Not Started |
| `M7.2` | Run the harness-capabilities research and fold its findings | task | Human-led | Not Started |
| `M8` | Harness compatibility | phase | — | Not Started |
| `M8.1` | Harness facts fixture drives model-profiles and executor templates, with a classified diff on version bumps | task | Agentic-led | Not Started |
| `M8.2` | Worker adapters harden the launch and run a deterministic post-run check | task | Agentic-led | Not Started |
| `M8.3` | Reviewer runs are read-only and specy-road writes the review record from structured output | task | Agentic-led | Not Started |
| `M8.4` | Ship skills once and meter every file each harness injects | task | Agentic-led | Not Started |
| `M8.5` | Guard hooks per harness and avoid lists in every model profile | task | Agentic-led | Not Started |
| `M8.6` | Candidate harness profiles: Copilot CLI reviewer and Antigravity agy generic | task | Human-led | Not Started |
| `M8.7` | Runtime verification of the harness facts against installed binaries | task | Human-led | Not Started |

Chunk files (authoritative definitions): see [`roadmap/manifest.json`](roadmap/manifest.json) `includes` (e.g. [`roadmap/phases/`](roadmap/phases/)).
