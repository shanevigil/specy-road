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
| `M3` | 0.3.1 pre-final fixes from rc1 feedback | phase | — | Complete |
| `M3.1` | Refuse to pick up leaves whose planning sheet is still a placeholder | task | Agentic-led | Complete |
| `M3.2` | handoff status reports review records without a claim | task | Agentic-led | Complete |
| `M3.3` | Document the canonical chunk key order and offer a deliberate normalisation | task | Agentic-led | Complete |
| `M3.4` | Brainstorm prompts: shards from the allocation, per-pass files, framing with proposed answers | task | Agentic-led | Complete |
| `M3.5` | Converge and evidence passes that cannot silently skip work | task | Agentic-led | Complete |
| `M3.6` | Triage commands: realize, append-why, summary, consistent reasons, all-or-nothing accept | task | Agentic-led | Complete |
| `M3.7` | promote writes usable nodes once, with short codenames | task | Agentic-led | Complete |
| `M3.8` | Upgrade and validate report drift and migrations plainly | task | Agentic-led | Complete |
| `M3.9` | Worker and session CLI: resume permissions, roster provenance, event gaps | task | Agentic-led | Complete |
| `M3.10` | Worker hand-off, reconcile and finish report what actually happened | task | Agentic-led | Complete |
| `M3.11` | Roster ids with effort suffixes, packet path, stale sessions | task | Agentic-led | Complete |
| `M3.12` | A baseline gate runs on the integration branch before pickup | task | Agentic-led | Complete |
| `M3.13` | A trial merge with the integration branch runs before review and before finish | task | Agentic-led | Complete |
| `M3.14` | finish-this-task and pickup detect a planning sheet that is still the scaffold | task | Agentic-led | Complete |
| `M3.15` | Read-only review commands take --ref, handoff status exit codes are distinct, review list, and an orchestration.yaml starter | task | Agentic-led | Complete |
| `M3.16` | Bring worker_cli and worker_adapters back under the 400-line cap | task | Agentic-led | Complete |
| `M3.17` | A failing verifier in the READY file blocks the gate unless a reviewer marks it as already failing on the integration branch | task | Agentic-led | Complete |
| `M3.18` | Bring role_prompt under the file cap and clear the ruff complexity error | task | Agentic-led | Complete |
| `M4` | Brainstorm and roadmap editing features | phase | — | Complete |
| `M4.1` | promote carries the converge judgement into sheets and writes an authoring prompt | task | Agentic-led | Complete |
| `M4.2` | Structured promote: target parents, clusters, minimum recommendation, plan file | task | Agentic-led | Complete |
| `M4.3` | Batch ideas and verdicts from a file, merge, and gap ideas | task | Agentic-led | Complete |
| `M4.4` | Policies and decisions as first-class brainstorm outcomes; frame amendments | task | Agentic-led | Complete |
| `M4.5` | Repository files as evidence; null results; quotes on research-born ideas | task | Agentic-led | Complete |
| `M4.6` | Lenses from the frame and a ranked node list in the recommend prompt | task | Agentic-led | Complete |
| `M4.7` | Scriptable graph edits: apply a change file with dry run, acceptance at creation, display-id dependencies | task | Agentic-led | Complete |
| `M4.8` | list-nodes --json, refresh-stubs --diff, move-node zone rewrite | task | Agentic-led | Complete |
| `M4.9` | Opt-in auto-pick ordering by execution milestone | task | Agentic-led | Complete |
| `M4.10` | Clean up merged feature branches after finish | task | Agentic-led | Complete |
| `M4.11` | grind-session --plan keeps ready leaves with overlapping touch zones out of the same parallel wave | task | Agentic-led | Complete |
| `M4.12` | file-limits function-length check covers TypeScript and JavaScript | task | Agentic-led | Complete |
| `M4.13` | specy-road doctor lists merged or stale feature branches, worktrees, registry rows and stashes | task | Agentic-led | Complete |
| `M4.14` | brainstorm promote inherits execution_milestone from the anchor | task | Agentic-led | Complete |
| `M4.15` | Session overlap warnings name the other worktree and its edit state | task | Agentic-led | Complete |
| `M4.16` | Review rounds and elapsed time per leaf, and doctor lists detached worktrees | task | Agentic-led | Complete |
| `M4.17` | Review-loop escalation: a root-cause analysis runs when reviews keep blocking | task | Agentic-led | Complete |
| `M4.18` | Further TS/JS syntax forms for the function cap found in M4.12 review | task | Agentic-led | Complete |
| `M5` | Agent context and outcomes | phase | — | Complete |
| `M5.1` | Every managed AGENTS.md rule carries its provenance in the template | task | Agentic-led | Complete |
| `M5.2` | validate flags specy-road commands that do not exist in the consumer's agent files | task | Agentic-led | Complete |
| `M5.3` | validate reports always-injected context per harness against documented limits | task | Agentic-led | Complete |
| `M5.4` | Rules the CLI or hooks enforce shrink to one-line pointers in the managed block | task | Agentic-led | Complete |
| `M5.5` | A replayable context regression set for the sandbox runbook | task | Mixed | Complete |
| `M5.6` | Pilot the context-feedback question in the sandbox before shipping it | task | Agentic-led | Complete |
| `M5.7` | Measure the managed section on and off across the sandbox apps | task | Agentic-led | Complete |
| `M5.8` | Further Markdown mention forms for the stale-command check found in M5.2 review | task | Agentic-led | Complete |
| `M6` | 0.3.1-rc2 release | phase | — | Complete |
| `M6.1` | Close out the triage note, changelog and what's-new for rc2 | task | Agentic-led | Complete |
| `M6.2` | Pre-release checks and the 0.3.1-rc2 cut | task | Human-led | Complete |
| `M7` | Keeping current: recurring research | phase | — | Not Started |
| `M7.1` | A research register tracks deep-research topics with a refresh cadence | task | Agentic-led | Complete |
| `M7.2` | Run the harness-capabilities research and fold its findings | task | Human-led | Not Started |
| `M8` | Harness compatibility | phase | — | Not Started |
| `M8.1` | Harness facts fixture drives model-profiles and executor templates, with a classified diff on version bumps | task | Agentic-led | Complete |
| `M8.2` | Worker adapters harden the launch and run a deterministic post-run check | task | Agentic-led | Not Started |
| `M8.3` | Reviewer runs are read-only and specy-road writes the review record from structured output | task | Agentic-led | Not Started |
| `M8.4` | Ship skills once and meter every file each harness injects | task | Agentic-led | Complete |
| `M8.5` | Guard hooks per harness and avoid lists in every model profile | task | Agentic-led | Not Started |
| `M8.6` | Candidate harness profiles: Copilot CLI reviewer and Antigravity agy generic | task | Agentic-led | Not Started |
| `M8.7` | Runtime verification of the harness facts against installed binaries | task | Agentic-led | Not Started |
| `M9` | Regression prevention | phase | — | Complete |
| `M9.1` | finish-this-task runs a configured land check on the merge commit before it pushes | task | Agentic-led | Complete |
| `M9.2` | pytest refuses to start while tests/fixtures holds ignored files, and fails when a run changes the fixture tree | task | Agentic-led | Complete |
| `M9.3` | Finish, the packet and a finish re-run are tested in a nested layout whose leaf also changes a file outside the project | task | Agentic-led | Complete |
| `M9.4` | An executor that cannot meet a criterion without weakening a test or a baseline records blocked_on in READY, and the gate stays unmet | task | Agentic-led | Complete |
| `M9.5` | specy-road integrity reports removed tests, new skips, lost asserts and test-config changes on a leaf, and the packet shows them | task | Agentic-led | Complete |
| `M9.6` | With integrity_gate on, a test-integrity finding blocks the review gate unless the leaf declared it before pickup | task | Agentic-led | Complete |
| `M9.7` | specy-road integrity also reports new lint suppressions and widened baseline files | task | Agentic-led | Complete |
| `M9.8` | A pre-existing verifier failure counts only when specy-road reproduced it twice on the integration tip | task | Agentic-led | Complete |
| `M9.9` | The executor prompt and the review packet list the Python tests that import the leaf's code | task | Agentic-led | Complete |
| `M9.10` | Opt-in red-green evidence: tests a leaf adds or changes fail on the base commit and pass at head | task | Agentic-led | Complete |
| `M9.11` | Touch-zone checks match project-relative and git-root-relative paths alike in a nested project | task | Agentic-led | Complete |
| `M10` | Agent loop performance and observability | phase | — | Not Started |
| `M10.1` | Record phase timestamps in the event log and print a per-leaf timeline | task | Agentic-led | Complete |
| `M10.2` | Normalised usage event in the worker log | task | Agentic-led | Complete |
| `M10.3` | Replace per-worker polling with a single mailbox flag file and a foreground --wait | task | Agentic-led | Complete |
| `M10.4` | Pin harness discovery mode per profile | task | Agentic-led | Complete |
| `M10.5` | Per-role effort in model profiles | task | Agentic-led | Complete |
| `M10.6` | Measure whether lower reviewer effort changes verdicts | task | Agentic-led | Complete |
| `M10.7` | Output budgets with --full on packets, briefs and plans | task | Agentic-led | Complete |
| `M10.8` | Reviewers launch without repo hooks or MCP | task | Agentic-led | Complete |
| `M10.9` | Emit a stalled event when a worker goes silent past a threshold | task | Agentic-led | Complete |
| `M10.10` | Position the docs on governance, not on CLI workers | task | Agentic-led | Complete |
| `M10.11` | Document the harness-subagent recipe for parallel work inside a leaf | task | Agentic-led | Complete |
| `M10.12` | Visual explorer for worker event logs in the PM GUI | task | Agentic-led | Complete |
| `M10.13` | A project setting decides whether agent logs are tracked in git | task | Agentic-led | Complete |
| `M10.14` | edit-node keeps an active claim's touch zones in step with the node | task | Agentic-led | Complete |
| `M10.15` | Executor prompt keeps long commands in the foreground so a headless turn does not end before its tests finish | task | Agentic-led | Complete |
| `M10.16` | The worker wrapper imports the launching specy-road, not the worktree's copy | task | Agentic-led | Complete |
| `M10.17` | The review packet caps its inlined diff by bytes too and lists generated bundles by size only | task | Agentic-led | Complete |
| `M10.18` | Review records are found and written with the canonical file name on case-insensitive filesystems | task | Agentic-led | Complete |
| `M10.19` | The executor prompt forbids killing processes the executor did not start | task | Agentic-led | Complete |
| `M10.20` | Pilot GPT-6.1 Terra as a lower-cost executor before rostering it | task | Agentic-led | Not Started |
| `M11` | rc2 field feedback: worktrees, workers and the review loop | phase | Agentic-led | Not Started |
| `M11.1` | In a git worktree, every command resolves work/ paths the same way and a sandboxed reviewer can file its record | task | Agentic-led | Complete |
| `M11.2` | worker message resumes a failed or stalled worker whose native session id is known | task | Agentic-led | Complete |
| `M11.3` | specy-road's own runtime directories never fail the clean-tree checks | task | Agentic-led | Complete |
| `M11.4` | max_workers counts live workers across checkouts and applies to resumes | task | Agentic-led | Not Started |
| `M11.5` | Pickup's stale-claim check tests the local branch and never advises deleting a live claim | task | Agentic-led | Complete |
| `M11.6` | worker reconcile judges a worker against the leaf's current contract | task | Agentic-led | Complete |
| `M11.7` | review delegate runs a rostered reviewer like worker delegate runs an executor | task | Agentic-led | Complete |
| `M11.8` | An opt-in delta review packet for small fix rounds | task | Agentic-led | Not Started |
| `M11.9` | Acceptance items a human must satisfy are marked and handled as such | task | Agentic-led | Complete |
| `M11.10` | edit-node can add and remove single list entries | task | Agentic-led | Complete |
| `M11.11` | orchestrate plan, grind-session --plan and pickup share one readiness rule and rank executors by class and billing route | task | Agentic-led | Complete |
| `M11.12` | specy-road ready writes a valid READY hand-off | task | Agentic-led | Complete |
| `M11.13` | A milestone gets one full review of its combined change before it is marked complete | task | Agentic-led | Not Started |
| `M11.14` | worker message queues a follow-up for a worker whose turn is still running | task | Agentic-led | Not Started |
| `M11.15` | Pickup and finish agree on unwritten planning sheets | task | Agentic-led | Not Started |
| `M11.16` | A commit that changes only planning or bookkeeping files keeps existing approvals | task | Agentic-led | Not Started |
| `M11.17` | edit-node names every chunk file it changes, and relocation is loud | task | Agentic-led | Not Started |
| `M11.18` | Registry overlap warnings show only what concerns the command at hand | task | Agentic-led | Not Started |
| `M11.19` | Pickup never stashes work/ around the registry commit | task | Agentic-led | Not Started |
| `M11.20` | orchestrate plan and validate say where the roster is read from | task | Agentic-led | Not Started |
| `M11.22` | Worker worktrees can include nested sibling repositories | task | Mixed | Not Started |
| `M11.23` | A custom launch command's permissions carry through resume | task | Agentic-led | Not Started |
| `M11.24` | Executors and reviewers in a worktree can write and check the right places | task | Agentic-led | Not Started |
| `M11.25` | finish-this-task says what merge mode will push before it pushes | task | Agentic-led | Not Started |
| `M11.26` | A model profile can match harness model ids that carry an effort suffix | task | Agentic-led | Not Started |
| `M11.27` | Small CLI fixes from field use | task | Agentic-led | Not Started |
| `M11.28` | A light chore mode for work outside the roadmap | task | Mixed | Not Started |
| `M11.29` | doctor warns when the running specy-road is older than the project's stubs | task | Agentic-led | Not Started |
| `M11.30` | Leaf worktrees get the project's environment set up | task | Agentic-led | Not Started |
| `M11.31` | A safe command to retire a leaf worktree | task | Agentic-led | Not Started |
| `M11.32` | Unpushed nested-repo commits are reported | task | Agentic-led | Not Started |
| `M11.33` | A reviewer whose harness routes models dynamically does not count as an independent family by default | task | Agentic-led | Not Started |
| `M11.34` | Open human decisions live in one tracked ledger and every question is self-contained | task | Agentic-led | Not Started |
| `M11.35` | A roster entry maps to the harness's own model id, and a failed start says why | task | Agentic-led | Not Started |

Chunk files (authoritative definitions): see [`roadmap/manifest.json`](roadmap/manifest.json) `includes` (e.g. [`roadmap/phases/`](roadmap/phases/)).
