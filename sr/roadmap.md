# Roadmap index

<!-- specy-road: generated index from merged roadmap (manifest.json + chunk files) — do not edit by hand -->

Gate maps milestone execution: **Human-led** / **Agentic-led** / **Mixed**. All leaf tasks are agentic by design.

Status shown is the **computed rollup status**: for leaves, the node's own status; for non-leaves, the roll-up over leaf descendants (Complete when every leaf descendant is Complete; otherwise the most-pressing non-complete status).

| ID | Title | Type | Gate | Status |
|----|-------|------|------|--------|
| `M1` | Adopt specy-road | phase | Human-led | Complete |
| `M1.1` | Set up the project's specy-road basics | task | Mixed | Complete |
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
| `M5` | Agent context and outcomes | phase | — | In Progress |
| `M5.1` | Every managed AGENTS.md rule carries its provenance in the template | task | Agentic-led | Complete |
| `M5.2` | validate flags specy-road commands that do not exist in the consumer's agent files | task | Agentic-led | Complete |
| `M5.3` | validate reports always-injected context per harness against documented limits | task | Agentic-led | Complete |
| `M5.4` | Rules the CLI or hooks enforce shrink to one-line pointers in the managed block | task | Agentic-led | Complete |
| `M5.5` | A replayable context regression set for the sandbox runbook | task | Mixed | Complete |
| `M5.6` | Pilot the context-feedback question in the sandbox before shipping it | task | Agentic-led | Complete |
| `M5.7` | Measure the managed section on and off across the sandbox apps | task | Agentic-led | Complete |
| `M5.8` | Further Markdown mention forms for the stale-command check found in M5.2 review | task | Agentic-led | Complete |
| `M6` | 0.3.1-rc2 release | phase | — | In Progress |
| `M6.1` | Close out the triage note, changelog and what's-new for rc2 | task | Agentic-led | Complete |
| `M6.2` | Pre-release checks and the 0.3.1-rc2 cut | task | Human-led | Complete |
| `M7` | Keeping current: recurring research | phase | — | In Progress |
| `M7.1` | A research register tracks deep-research topics with a refresh cadence | task | Agentic-led | Complete |
| `M7.2` | Run the harness-capabilities research and fold its findings | task | Human-led | Complete |
| `M8` | Harness compatibility | phase | — | In Progress |
| `M8.1` | Harness facts fixture drives model-profiles and executor templates, with a classified diff on version bumps | task | Agentic-led | Complete |
| `M8.2` | Worker adapters harden the launch and run a deterministic post-run check | task | Agentic-led | Complete |
| `M8.3` | Reviewer runs are read-only and specy-road writes the review record from structured output | task | Agentic-led | Complete |
| `M8.4` | Ship skills once and meter every file each harness injects | task | Agentic-led | Complete |
| `M8.5` | Guard hooks per harness and avoid lists in every model profile | task | Agentic-led | Complete |
| `M8.6` | Candidate harness profiles: Copilot CLI reviewer and Antigravity agy generic | task | Agentic-led | Complete |
| `M8.7` | Runtime verification of the harness facts against installed binaries | task | Agentic-led | Complete |
| `M9` | Regression prevention | phase | — | In Progress |
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
| `M10` | Agent loop performance and observability | phase | — | In Progress |
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
| `M10.20` | Pilot GPT-6.1 Terra as a lower-cost executor before rostering it | task | Agentic-led | Complete |
| `M11` | rc2 field feedback: worktrees, workers and the review loop | phase | Agentic-led | In Progress |
| `M11.1` | In a git worktree, every command resolves work/ paths the same way and a sandboxed reviewer can file its record | task | Agentic-led | Complete |
| `M11.2` | worker message resumes a failed or stalled worker whose native session id is known | task | Agentic-led | Complete |
| `M11.3` | specy-road's own runtime directories never fail the clean-tree checks | task | Agentic-led | Complete |
| `M11.4` | max_workers counts live workers across checkouts and applies to resumes | task | Agentic-led | Complete |
| `M11.5` | Pickup's stale-claim check tests the local branch and never advises deleting a live claim | task | Agentic-led | Complete |
| `M11.6` | worker reconcile judges a worker against the leaf's current contract | task | Agentic-led | Complete |
| `M11.7` | review delegate runs a rostered reviewer like worker delegate runs an executor | task | Agentic-led | Complete |
| `M11.8` | An opt-in delta review packet for small fix rounds | task | Agentic-led | Complete |
| `M11.9` | Acceptance items a human must satisfy are marked and handled as such | task | Agentic-led | Complete |
| `M11.10` | edit-node can add and remove single list entries | task | Agentic-led | Complete |
| `M11.11` | orchestrate plan, grind-session --plan and pickup share one readiness rule and rank executors by class and billing route | task | Agentic-led | Complete |
| `M11.12` | specy-road ready writes a valid READY hand-off | task | Agentic-led | Complete |
| `M11.13` | A milestone gets one full review of its combined change before it is marked complete | task | Agentic-led | Complete |
| `M11.14` | worker message queues a follow-up for a worker whose turn is still running | task | Agentic-led | Complete |
| `M11.15` | Pickup and finish agree on unwritten planning sheets | task | Agentic-led | Complete |
| `M11.16` | A commit that changes only planning or bookkeeping files keeps existing approvals | task | Agentic-led | Complete |
| `M11.17` | edit-node names every chunk file it changes, and relocation is loud | task | Agentic-led | Complete |
| `M11.18` | Registry overlap warnings show only what concerns the command at hand | task | Agentic-led | Complete |
| `M11.19` | Pickup never stashes work/ around the registry commit | task | Agentic-led | Complete |
| `M11.20` | orchestrate plan and validate say where the roster is read from | task | Agentic-led | Complete |
| `M11.22` | Worker worktrees can include nested sibling repositories | task | Agentic-led | Complete |
| `M11.23` | A custom launch command's permissions carry through resume | task | Agentic-led | Complete |
| `M11.24` | Executors and reviewers in a worktree can write and check the right places | task | Agentic-led | Complete |
| `M11.25` | finish-this-task says what merge mode will push before it pushes | task | Agentic-led | Complete |
| `M11.26` | A model profile can match harness model ids that carry an effort suffix | task | Agentic-led | Complete |
| `M11.27` | Small CLI fixes from field use | task | Agentic-led | Complete |
| `M11.28` | A light chore mode for work outside the roadmap | task | Agentic-led | Complete |
| `M11.29` | doctor warns when the running specy-road is older than the project's stubs | task | Agentic-led | Complete |
| `M11.30` | Leaf worktrees get the project's environment set up | task | Agentic-led | Complete |
| `M11.31` | A safe command to retire a leaf worktree | task | Agentic-led | Complete |
| `M11.32` | Unpushed nested-repo commits are reported | task | Agentic-led | Complete |
| `M11.33` | A reviewer whose harness routes models dynamically does not count as an independent family by default | task | Agentic-led | Complete |
| `M11.34` | Open human decisions live in one tracked ledger and every question is self-contained | task | Agentic-led | Complete |
| `M11.35` | A roster entry maps to the harness's own model id, and a failed start says why | task | Agentic-led | Complete |
| `M11.36` | A resumed reviewer session may approve a delta it was shown | task | Agentic-led | Complete |
| `M11.37` | review-packet warns when the brief or summary names a file not committed at the reviewed commit | task | Agentic-led | Complete |
| `M11.38` | handoff status says who can still supply a missing approval | task | Agentic-led | Complete |
| `M11.39` | A roster entry can be marked unavailable without deleting it | task | Agentic-led | Complete |
| `M11.40` | worker reconcile works on merged leaves and separates untracked files | task | Agentic-led | Complete |
| `M11.41` | The two review-gate settings cannot silently disagree | task | Agentic-led | Complete |
| `M11.42` | session end finds the session the same agent started | task | Agentic-led | Complete |
| `M11.43` | init project reports exactly what it writes | task | Agentic-led | Complete |
| `M11.44` | init project can install only the model profiles a project uses | task | Agentic-led | Complete |
| `M11.45` | The stale-command warning fires only on command-shaped mentions | task | Agentic-led | Complete |
| `M11.46` | Placeholder leaves neither fail validate --strict nor pad briefs | task | Agentic-led | Complete |
| `M11.47` | validate checks git-root touch zones in a nested project | task | Agentic-led | Complete |
| `M11.48` | A claimed leaf reads as claimed in list-nodes and brief | task | Agentic-led | Complete |
| `M11.49` | The review packet takes touch zones from the reviewed commit and treats lockfiles as generated | task | Agentic-led | Complete |
| `M11.50` | finish keeps a committed implementation summary in history | task | Agentic-led | Complete |
| `M11.51` | Dashboard saves never overwrite newer disk edits, and the read API is documented | task | Agentic-led | Complete |
| `M11.52` | PR mode predicts and resolves the registry conflict | task | Agentic-led | Complete |
| `M11.53` | A worktree-based flow can claim leaves without pushing from the worktree | task | Agentic-led | Complete |
| `M11.54` | The test suite and land check run in parallel | task | Agentic-led | Complete |
| `M11.55` | Executors split modules to meet file limits instead of deleting documentation | task | Agentic-led | Complete |
| `M11.56` | Delegate creates the reviews directory before a harness is told to allow it | task | Agentic-led | Complete |
| `M11.57` | A completed worker on a finished leaf does not hold a max_workers slot | task | Agentic-led | Complete |
| `M11.58` | The coordinator records the session's routing preferences where the next session can read them | task | Agentic-led | Complete |
| `M11.59` | Split worker_ops and worker_adapters so parallel leaves stop colliding | task | Agentic-led | Complete |
| `M11.60` | The harness facts fixture takes the 2026-11-02 sourced findings and watches the new scope-escape feature names | task | Agentic-led | Complete |
| `M11.61` | The context meter counts Claude rules, auto memory, Cursor nested AGENTS.md and Copilot path instructions | task | Agentic-led | Complete |
| `M11.62` | Headless runs report usage limits and denied actions instead of looking like success | task | Agentic-led | Complete |
| `M11.63` | do-next-available-task refuses a second claim in a checkout that already holds one | task | Agentic-led | Complete |
| `M11.64` | abort-task-pickup treats untracked files the way pickup does | task | Agentic-led | Complete |
| `M11.65` | why-blocked reports touch-zone holds from the plan | task | Agentic-led | Complete |
| `M11.66` | specy-road --version identifies the code when run from a checkout | task | Agentic-led | Complete |
| `M11.67` | Worker usage prices Cursor runs from the roster's price table | task | Agentic-led | Complete |
| `M11.68` | A re-delegated executor starts from the blocking review findings | task | Agentic-led | Complete |
| `M11.69` | A leaf that adds a schema key can be gated and finished | task | Agentic-led | Complete |
| `M11.70` | Touch zones are checked when they are written | task | Agentic-led | Complete |
| `M11.71` | Review loops escalate on their own and criteria are written with bounds | task | Agentic-led | Complete |
| `M11.72` | A reviewer run that ends without a record is reported as a failure | task | Agentic-led | Complete |
| `M11.73` | specy-road ready warns when the leaf no longer merges cleanly | task | Agentic-led | Complete |
| `M11.74` | Pickup and finish in one checkout take a shared lock in order | task | Agentic-led | Complete |
| `M11.75` | Reviewer prompt asks for independent probes, not the executor's own checks | task | Agentic-led | Complete |
| `M11.76` | Every roster model reaches its profile notes | task | Agentic-led | Complete |
| `M11.77` | A completed reviewer run does not report a missing record | task | Agentic-led | Complete |
| `M11.78` | Review lessons: escaped defect classes feed every reviewer prompt | task | Agentic-led | Complete |
| `M11.79` | Leaves that touch high-risk zones need a stronger reviewer | task | Agentic-led | Complete |
| `M11.80` | Executors and reviewers run tests with a bounded worker count | task | Agentic-led | Complete |
| `M11.82` | The integration branch passes ruff again and the land check runs it | task | Agentic-led | Complete |
| `M12` | Harness engineering: cheaper gates, clearer refusals, less drift | phase | — | Not Started |
| `M12.1` | A review fix-round budget that defers new-input-class findings to a follow-up leaf | task | Agentic-led | Complete |
| `M12.2` | Every refusal names its fix | task | Agentic-led | Complete |
| `M12.3` | Scheduled gardening chores that find drift and open small chore leaves | task | Agentic-led | Complete |
| `M12.4` | Quality signals agents and PMs read first | milestone | — | Not Started |
| `M12.4.1` | Per-area quality scores in the digest from review history | task | Agentic-led | Complete |
| `M12.4.2` | A tracked tech-debt ledger that planning can turn into leaves | task | Agentic-led | Not Started |
| `M12.4.3` | Per-model review evidence: block rate and overturned approvals feed orchestrate plan | task | Agentic-led | Not Started |
| `M12.5` | The orchestrator cleans up landed leaves and stale worktrees automatically, saving hand-off files first | task | Agentic-led | Not Started |
| `M12.6` | Every command exposes its parser, and the stale-command scan reports flags a command does not accept | task | Agentic-led | Not Started |
| `M13` | rc3 adopter feedback: upgrade and adoption friction | phase | — | Not Started |
| `M13.1` | Say which install is running and flag managed blocks an older version wrote | task | Agentic-led | Complete |
| `M13.2` | upgrade previews as the new version, validates in a dry run and names files it pushed over the line cap | task | Agentic-led | Complete |
| `M13.3` | A pointer-only AGENTS.md block option, and upgrade names the project text the new rules file duplicates | task | Agentic-led | Complete |
| `M13.4` | A milestone held for its full review says so in validate, list-nodes and why-blocked | task | Agentic-led | Complete |
| `M13.5` | refresh-profiles installs only the profiles the roster names, and suggests the alias for a near miss | task | Agentic-led | Complete |
| `M13.6` | Safe release-candidate install recipe, pipx and uv tool upgrades, and checking which binary is on PATH | task | Agentic-led | Complete |
| `M13.7` | Clearer notices: symlinked skill dirs, new ignore rules over tracked files, and session end | task | Agentic-led | Complete |
| `M13.8` | A behaviour-change catalogue, and validate reports project agent text it contradicts | task | Agentic-led | Complete |
| `M13.9` | Notices for how the agent files fit together: missing CLAUDE.md import, two load orders, floor read twice | task | Agentic-led | Not Started |
| `M13.10` | Upgrade guide: moving to the split rules files, previewing an uninstalled version, telling old installs apart | task | Agentic-led | Complete |
| `M13.11` | upgrade says what changed for this repo: behaviour changes, a pin below the new minimum, the new files and duplicated paragraphs | task | Agentic-led | Not Started |
| `M13.12` | Quieter, accurate validate notices: untracked touch zones, the managed .gitignore comment, and tracked files under new ignore rules | task | Agentic-led | Complete |
| `M13.13` | upgrade --prompt writes an agent upgrade prompt filled in from this repo | task | Agentic-led | Not Started |
| `M13.14` | validate flags project agent text that mandates a changed behaviour (best-effort hint) | task | Agentic-led | Not Started |
| `M14` | Nested repos and review-gate integrity | phase | — | Not Started |
| `M14.1` | Approvals never carry across unreviewed changes in a sibling repository | task | Agentic-led | Not Started |
| `M14.2` | doctor never offers to remove a live leaf's worktree or branch | task | Agentic-led | Complete |
| `M14.3` | worktree prune refuses to delete another repository's worktree or checkout | task | Agentic-led | Complete |
| `M14.4` | nested_repos that a project can adopt without pushing: local landing, local base, sibling diffs and checks | milestone | — | Not Started |
| `M14.4.1` | Per nested repository, land by push, locally or by hand, and base worktrees on the remote or local tip | task | Agentic-led | Complete |
| `M14.4.2` | review-packet includes sibling repository diffs | task | Agentic-led | Not Started |
| `M14.4.3` | worker reconcile and the post-run check see sibling repositories | task | Agentic-led | Not Started |
| `M14.5` | An approve with no recorded probe is flagged, and policy can refuse to count it | task | Agentic-led | Not Started |
| `M14.6` | Reviewer usage is visible: review usage, reviewers in the node total, RUN logs kept per round | task | Agentic-led | Complete |
| `M14.7` | session end finds this agent's session by worktree and branch when the derived id has no record | task | Agentic-led | Complete |
| `M14.8` | The implementation-zone check runs before a review is spent, and knows about sibling repositories | task | Agentic-led | Not Started |
| `M14.9` | review rca launches the root-cause analyst like review delegate, and says what to do when no analyst is available | task | Agentic-led | Not Started |
| `M14.10` | Escalation recognises a converging loop and handoff status shows the findings trend | task | Agentic-led | Complete |
| `M14.11` | The rework and fix-round prompt asks the executor to audit the whole failure class and list its probes | task | Agentic-led | Complete |
| `M15` | rc3 adopter feedback: install safety, multi-harness reviewers and parallel-grind friction | phase | — | Not Started |
| `M15.1` | RC install docs cover extras and the direct wheel URL, and each RC announcement carries the filled-in command | task | Agentic-led | Complete |
| `M15.2` | A Claude Code reviewer works on a subscription login: bare only with an API key, explicit mode otherwise, checked before launch | task | Agentic-led | Not Started |
| `M15.3` | prompt --channel cli launches nothing without --run, and a run uses the rostered model in the leaf's worktree; a model the harness did not report as rostered is flagged | task | Agentic-led | Not Started |
| `M15.4` | Parallel PR-mode leaves reconcile bookkeeping by rule, and pickup's register commit leaves the digest current | task | Agentic-led | Complete |
| `M15.5` | Host effects policy: workers and reviewers do not take over the screen or change shared services, the guard denies such commands, and a message can interrupt a turn | task | Agentic-led | Not Started |
| `M15.6` | The rework prompt carries the accepted root-cause analysis as the governing design, ahead of the reviews' suggested fixes | task | Agentic-led | Complete |
| `M15.7` | file-limits can write a baseline of today's exceptions, a failing run points at it, and upgrade reports the file-limits count | task | Agentic-led | Not Started |
| `M15.8` | A promoted leaf is never stuck: promote's sheet says Approach is written before pickup, and author-approach prints the prompt to write it | task | Agentic-led | Complete |
| `M15.9` | Harness launches survive large prompts and a harness binary off PATH, for every role | task | Agentic-led | Complete |
| `M15.10` | Try a roster before it lands: a dry-run plan from the working tree and local roster entries, and models list shows the uncommitted roster diff | task | Agentic-led | Complete |
| `M15.11` | A working roster in one command, profile values validated locally, consistent ids in docs, and plans that can spread executors | task | Agentic-led | Complete |
| `M15.12` | Shared documentation zones do not serialize grind-session batches | task | Agentic-led | Complete |
| `M15.13` | Worker loop friction: sync waits for the events that matter, tool-use noise collapses, rework after a completed worker, a READY-only resume, a quieter pickup | task | Agentic-led | Complete |
| `M15.14` | Chores at parity with leaves: worktree, branch and env_setup on start, widen zones, the review-record path, and work/chores ignored | task | Agentic-led | Not Started |
| `M15.15` | upgrade ships the work/ templates every prompt references, and the .specyrd README matches upgrade's steps | task | Agentic-led | Complete |
| `M15.16` | Role-observed acceptance needs evidence from that role, and coordinator probes are not acceptance | task | Agentic-led | Not Started |
| `M15.17` | Review friction: delegate builds a missing packet, the packet skips ignored evidence and numbers suppressions correctly, refusals quote the line, and superseded failed runs say so | task | Agentic-led | Not Started |
| `M15.18` | planned_test_changes can be edited after pickup, and an unplanned test removal is a required reviewer check | task | Agentic-led | Complete |
| `M15.19` | Cursor worker cost is estimated when the harness reports a display name for the rostered model | task | Agentic-led | Complete |
| `M15.20` | Touch zones that miss what acceptance needs are flagged at plan time, and the brief's zone section stays short | task | Agentic-led | Not Started |
| `M15.21` | Linked worktrees: commands resolve the enclosing worktree, and env_setup handles symlinked environments | task | Agentic-led | Complete |
| `M15.22` | Project preferences the workflow respects: local decisions, a PR body footer, the summary commit rule, and local landing for the root repository | task | Agentic-led | Complete |
| `M15.23` | A project declares its merge-blocking CI commands per touch zone; ready always runs them and the review packet shows their result at the reviewed commit | task | Agentic-led | Not Started |
| `M15.24` | ready does not record false evidence: a passing run whose output shows a failed command is flagged, and --run-argv runs a command without a shell | task | Agentic-led | Complete |
| `M15.25` | A change to the shared stash is attributed to the worker whose branch made it, not to whichever worker's turn ended while the entry existed | task | Agentic-led | Not Started |
| `M15.26` | A claim left with no worker is never silent: finished workers free their max_workers slot, handoff status and doctor list orphaned claims, and a failed delegate says how to resolve its claim | task | Agentic-led | Complete |
| `M15.27` | worker usage counts every usage-bearing event of a long Cursor turn and marks a turn whose output tokens are implausibly low for its length | task | Agentic-led | Complete |
| `M15.28` | --rework carries blocks at the branch tip as required changes, lists older blocks as possibly resolved, and takes a coordinator note placed above the reviews | task | Agentic-led | Not Started |
| `M15.29` | A review that stops before filing leaves a trace: every reviewer channel opens a RUN record, and review list shows started but not filed | task | Agentic-led | Not Started |
| `M15.30` | Under delta review, one approval per round still checks the whole leaf against the merge base on a fixed checklist | task | Agentic-led | Not Started |
| `M15.31` | A delegated reviewer always runs a named model: review delegate passes the roster id as worker delegate does, refuses a reviewer with no model, and files the model the harness reported | task | Agentic-led | Not Started |
| `M15.32` | An implementation summary that finish archives to work/done/ is not measured by file-limits, so finish never lands a file-limits failure | task | Agentic-led | Not Started |
| `M15.33` | A refused review record leaves a trace: review record writes REJECTED-<model>.md, and review list and handoff status show it until a record is filed | task | Agentic-led | Not Started |
| `M15.34` | The executor prompt states the test rules that the reviewer's excess checklist enforces | task | Agentic-led | Not Started |
| `M15.35` | The review packet never lists .git or a path under it as an uncommitted reference | task | Agentic-led | Not Started |
| `M16` | lean core: harden and optimize code and docs, all delivered functionality kept | phase | — | Not Started |
| `M16.0` | Parity harness: command inventory, golden --help transcripts, an end-to-end leaf loop and dogfood outputs | task | Agentic-led | Not Started |
| `M16.1` | Parity harness: a review-gate decision table covering every review policy | task | Agentic-led | Not Started |
| `M16.2` | Baseline metrics, a coverage floor in CI, and the M16 working rules written down | task | Agentic-led | Not Started |
| `M16.3` | Delete dead and unwired code from a decided list, and add vulture as an advisory CI step | task | Agentic-led | Not Started |
| `M16.4` | Shared clock and atomic-write helpers replace the nine now() copies and the hand-written atomic writers | task | Agentic-led | Not Started |
| `M16.5` | One roadmap index answers every graph query: by id, by key, effective dependencies, unmet, ready | task | Agentic-led | Not Started |
| `M16.6` | The 29 package-imported library modules move out of bundled_scripts | task | Agentic-led | Not Started |
| `M16.7` | Commands run in the CLI's process: no python -m re-launch, no cwd globals | task | Agentic-led | Not Started |
| `M16.8` | A 100-character line-width rule with a shrink-only baseline, and the consumer file-limit default decided | task | Agentic-led | Not Started |
| `M16.9` | Fold the cap-driven splits in pickup and finish into their parents | task | Agentic-led | Not Started |
| `M16.10` | One LLM client module replaces the provider code inside review_node | task | Agentic-led | Not Started |
| `M16.11` | doctor --prune is the one cleanup path; branches prune, registry-prune and the grind cleanup become aliases | task | Agentic-led | Not Started |
| `M16.12` | upgrade absorbs the refresh commands and prints one report of what changed for the repo; update becomes self-update | task | Agentic-led | Not Started |
| `M16.13` | review status, review packet, decisions --kind lesson and presence replace handoff status, review list, review-packet, lessons and session | task | Agentic-led | Not Started |
| `M16.14` | One checks: block replaces baseline_cmd, land_check_cmd and verify_cmd with the same commands at the same points | task | Agentic-led | Not Started |
| `M16.15` | Orchestration subpackage with one public interface and one state model for the gate, the CLI and the PM GUI | task | Agentic-led | Not Started |
| `M16.16` | Worker runtime moves into orchestration/workers with import-path edits only | task | Agentic-led | Not Started |
| `M16.17` | Roster, model profiles, harness facts, orchestrate and role prompts move into orchestration | task | Agentic-led | Not Started |
| `M16.18` | Shared-checkout guard and session presence move into orchestration | task | Agentic-led | Not Started |
| `M16.19` | Grind session and its plan move into orchestration, read the index and the snapshot, and fold their cap siblings | task | Agentic-led | Not Started |
| `M16.20` | Review-policy evidence: how often each optional review policy changed a gate outcome | task | Mixed | Not Started |
| `M16.21` | Fold the review gate and escalation fragments, and mark the policies the evidence did not keep as deprecated | task | Agentic-led | Not Started |
| `M16.22` | Post-fix refactor gate: ready and the review packet report any complexity growth, and policy can block on it | task | Agentic-led | Not Started |
| `M16.23` | Tests: tests/support primitives, and the four heaviest cross-imported test files switch to them | task | Agentic-led | Not Started |
| `M16.24` | Tests: files move into unit, flows, cli, gui and repo lanes, moves only | task | Agentic-led | Not Started |
| `M16.25` | Tests: a committed dedupe worklist per subsystem names each removal and the assertion that covers it | task | Agentic-led | Not Started |
| `M16.26` | Tests: public seams replace private-name patches, and no test sleeps on the wall clock | task | Agentic-led | Not Started |
| `M16.27` | Tests: public scenarios for milestone sessions, rollup and reconcile, written before the milestone and nested-repo fold | task | Agentic-led | Not Started |
| `M16.28` | Tests: a CLI smoke lane of at most 50 subprocess items, everything else in process, suite time halved | task | Agentic-led | Not Started |
| `M16.29` | Constitution names orchestration as part of the product, bounds scope with a 'not' list, and drops contradictions | task | Agentic-led | Not Started |
| `M16.30` | AGENTS.md is the one agent entry with a task-conditional load order; CLAUDE.md is a pointer | task | Agentic-led | Not Started |
| `M16.31` | Docs by topic: design notes out of docs/, one workers doc, folded small docs, no pinned release candidate, one GUI extra | task | Agentic-led | Not Started |
| `M16.32` | suggested_prompts follow the real formats: CLI authoring, complete deliverables, no restated rules, nested layout | task | Agentic-led | Not Started |
| `M16.33` | rc5 close: lean metrics checked against the baseline and the sum of the leaf budgets | task | Mixed | Not Started |
| `M16.34` | Triage: the maintainer decides each held feature leaf not absorbed by an M16 leaf | task | Human-led | Not Started |
| `M16.35` | Git queries and registry I/O go through one helper each | task | Agentic-led | Not Started |
| `M16.36` | A shrink-only layering gate records the import cycles and package-to-entry-point imports | task | Agentic-led | Not Started |
| `M16.37` | Break the 45-module import cycle through the graph loader, the brief and validate | task | Agentic-led | Not Started |
| `M16.38` | Break the 25-module import cycle between roadmap CRUD, worker ops and the chore CLI | task | Agentic-led | Not Started |
| `M16.39` | Every command exposes build_parser(), imports lazily and shares the common argument helpers | task | Agentic-led | Not Started |
| `M16.40` | One SpecyError base for the 15 error classes, printed and turned into an exit code once | task | Agentic-led | Not Started |
| `M16.41` | Nested-repo landing folds into nested_repos, breaking its cycle, and the two session-file readers become one | task | Agentic-led | Not Started |
| `M16.42` | Fold the PM UI server and roadmap CRUD splits, after the orchestration snapshot is fixed | task | Agentic-led | Not Started |
| `M16.43` | The brainstorm CLI becomes two modules and the three managed-block writers share one engine | task | Agentic-led | Not Started |
| `M16.44` | Fold the remaining single-importer siblings from the code report's misc list | task | Agentic-led | Not Started |
| `M16.45` | milestone and planning command groups, and archive --hard-remove replaces archive-node | task | Agentic-led | Not Started |
| `M16.46` | worker_ops parts and the worker siblings fold into their parents, and the module-class swap goes | task | Agentic-led | Not Started |
| `M16.47` | One check_assignment decides eligibility for every launch and for the gate | task | Agentic-led | Not Started |
| `M16.48` | The guard classifier becomes three rule tables with every verdict unchanged | task | Agentic-led | Not Started |
| `M16.49` | Chore, decision and lesson records share internal adapters and keep their files byte for byte | task | Agentic-led | Not Started |
| `M16.50` | Grind settings move under grind: in git-workflow.yaml, migrated by upgrade | task | Agentic-led | Not Started |
| `M16.51` | The review packet fragments fold into review_packet | task | Agentic-led | Not Started |
| `M16.52` | checks: entries scoped to touch zones block a merge when they fail (held M15.23's purpose) | task | Agentic-led | Not Started |
| `M16.53` | Tests: public scenarios for outline moves, edit-field setters, archive, scaffold and update, written before the CRUD fold | task | Agentic-led | Not Started |
| `M16.54` | Tests: every other cross-file import, copied helper and hand-written manifest moves to tests/support | task | Agentic-led | Not Started |
| `M16.55` | Tests: per-leaf and per-round test files fold into the file for the module or flow they test | task | Agentic-led | Not Started |
| `M16.56` | Tests: apply the dedupe worklist for review gate | task | Agentic-led | Not Started |
| `M16.57` | Tests: apply the dedupe worklist for worker | task | Agentic-led | Not Started |
| `M16.58` | Tests: apply the dedupe worklist for pickup and finish | task | Agentic-led | Not Started |
| `M16.59` | Tests: apply the dedupe worklist for the rest | task | Agentic-led | Not Started |
| `M16.60` | Tests: five named properties replace the single-input tests they cover | task | Agentic-led | Not Started |
| `M16.61` | Gate: the release that shipped the M16 aliases is out and the maintainer closes the alias window | gate | Human-led | Not Started |
| `M16.62` | After the alias window: delete the deprecated command aliases, config-form fallbacks and re-export shims | task | Agentic-led | Not Started |

Chunk files (authoritative definitions): see [`roadmap/manifest.json`](roadmap/manifest.json) `includes` (e.g. [`roadmap/phases/`](roadmap/phases/)).
