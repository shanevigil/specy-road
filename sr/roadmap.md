# Roadmap index

<!-- specy-road: generated index from merged roadmap (manifest.json + chunk files) — do not edit by hand -->

Gate maps milestone execution: **Human-led** / **Agentic-led** / **Mixed**. All leaf tasks are agentic by design.

Status shown is the **computed rollup status**: for leaves, the node's own status; for non-leaves, the roll-up over leaf descendants (Complete when every leaf descendant is Complete; otherwise the most-pressing non-complete status).

| ID | Title | Type | Gate | Status |
|----|-------|------|------|--------|
| `M15` | rc3 adopter feedback: install safety, multi-harness reviewers and parallel-grind friction | phase | — | Not Started |
| `M15.1` | RC install docs cover extras and the direct wheel URL, and each RC announcement carries the filled-in command | task | Agentic-led | Complete |
| `M15.2` | A Claude Code reviewer works on a subscription login: bare only with an API key, explicit mode otherwise, checked before launch | task | Agentic-led | Complete |
| `M15.3` | prompt --channel cli launches nothing without --run, and a run uses the rostered model in the leaf's worktree; a model the harness did not report as rostered is flagged | task | Agentic-led | Not Started |
| `M15.4` | Parallel PR-mode leaves reconcile bookkeeping by rule, and pickup's register commit leaves the digest current | task | Agentic-led | Complete |
| `M15.6` | The rework prompt carries the accepted root-cause analysis as the governing design, ahead of the reviews' suggested fixes | task | Agentic-led | Complete |
| `M15.8` | A promoted leaf is never stuck: promote's sheet says Approach is written before pickup, and author-approach prints the prompt to write it | task | Agentic-led | Complete |
| `M15.9` | Harness launches survive large prompts and a harness binary off PATH, for every role | task | Agentic-led | Complete |
| `M15.10` | Try a roster before it lands: a dry-run plan from the working tree and local roster entries, and models list shows the uncommitted roster diff | task | Agentic-led | Complete |
| `M15.11` | A working roster in one command, profile values validated locally, consistent ids in docs, and plans that can spread executors | task | Agentic-led | Complete |
| `M15.12` | Shared documentation zones do not serialize grind-session batches | task | Agentic-led | Complete |
| `M15.13` | Worker loop friction: sync waits for the events that matter, tool-use noise collapses, rework after a completed worker, a READY-only resume, a quieter pickup | task | Agentic-led | Complete |
| `M15.15` | upgrade ships the work/ templates every prompt references, and the .specyrd README matches upgrade's steps | task | Agentic-led | Complete |
| `M15.17` | Review friction: delegate builds a missing packet, the packet skips ignored evidence and numbers suppressions correctly, refusals quote the line, and superseded failed runs say so | task | Agentic-led | Complete |
| `M15.18` | planned_test_changes can be edited after pickup, and an unplanned test removal is a required reviewer check | task | Agentic-led | Complete |
| `M15.19` | Cursor worker cost is estimated when the harness reports a display name for the rostered model | task | Agentic-led | Complete |
| `M15.21` | Linked worktrees: commands resolve the enclosing worktree, and env_setup handles symlinked environments | task | Agentic-led | Complete |
| `M15.22` | Project preferences the workflow respects: local decisions, a PR body footer, the summary commit rule, and local landing for the root repository | task | Agentic-led | Complete |
| `M15.24` | ready does not record false evidence: a passing run whose output shows a failed command is flagged, and --run-argv runs a command without a shell | task | Agentic-led | Complete |
| `M15.26` | A claim left with no worker is never silent: finished workers free their max_workers slot, handoff status and doctor list orphaned claims, and a failed delegate says how to resolve its claim | task | Agentic-led | Complete |
| `M15.27` | worker usage counts every usage-bearing event of a long Cursor turn and marks a turn whose output tokens are implausibly low for its length | task | Agentic-led | Complete |
| `M15.31` | A delegated reviewer always runs a named model: review delegate passes the roster id as worker delegate does, refuses a reviewer with no model, and files the model the harness reported | task | Agentic-led | Not Started |
| `M15.32` | An implementation summary that finish archives to work/done/ is not measured by file-limits, so finish never lands a file-limits failure | task | Agentic-led | Complete |
| `M15.33` | A refused review record leaves a trace: review record writes REJECTED-<model>.md, and review list and handoff status show it until a record is filed | task | Agentic-led | Complete |
| `M15.34` | The executor prompt states the test rules that the reviewer's excess checklist enforces | task | Agentic-led | Complete |
| `M15.35` | The review packet never lists .git or a path under it as an uncommitted reference | task | Agentic-led | Complete |
| `M15.36` | Claude Code workers never depend on the -p default mode: auth preflight before launch, explicit mode | task | Agentic-led | Not Started |
| `M15.37` | Review notes: a part joined by a comma or 'and' is a second observation only when it names a defect | task | Agentic-led | Complete |
| `M15.38` | add-node caps a title-derived codename at 64 characters so the planning file name fits | task | Agentic-led | Complete |
| `M15.39` | A roadmap write that fails part-way restores every file it changed | task | Agentic-led | Complete |
| `M15.40` | finish-this-task: a failed merge landing reports after the land check output and undoes its bookkeeping commit | task | Agentic-led | Complete |
| `M16` | lean core: harden and optimize code and docs, all delivered functionality kept | phase | — | Not Started |
| `M16.0` | Parity harness: command inventory, golden --help transcripts, an end-to-end leaf loop and dogfood outputs | task | Agentic-led | Not Started |
| `M16.1` | Parity harness: a review-gate decision table covering every review policy | task | Agentic-led | Not Started |
| `M16.2` | Baseline metrics, a coverage floor in CI, and the M16 working rules written down | task | Agentic-led | Not Started |
| `M16.3` | Delete dead and unwired code from a decided list, and add vulture as an advisory CI step | task | Agentic-led | Not Started |
| `M16.4` | Shared clock and atomic-write helpers replace the nine now() copies and the hand-written atomic writers | task | Agentic-led | Not Started |
| `M16.5` | One roadmap index answers every graph query: by id, by key, effective dependencies, unmet, ready | task | Agentic-led | Not Started |
| `M16.6` | The 29 package-imported library modules move out of bundled_scripts | task | Agentic-led | Not Started |
| `M16.7` | Commands run in the CLI's process: no python -m re-launch, no cwd globals | task | Agentic-led | Not Started |
| `M16.8` | Ruff quality rule families and the 100-character width with shrink-only baselines, and the consumer file-limit default decided | task | Agentic-led | Not Started |
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
| `M16.33` | rc5 close: lean metrics measured against the baseline | task | Mixed | Not Started |
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
| `M16.63` | Roster entries split into core fields and a typed run: block, read in both forms | task | Agentic-led | Not Started |
| `M16.64` | upgrade migrates rosters to core fields plus run: | task | Agentic-led | Not Started |
| `M16.65` | End-to-end pass on the toolkit and a feedback-and-fix round before 0.3.1 | task | Human-led | Not Started |
| `M16.66` | Gate: ready to tag 0.3.1 | gate | Human-led | Not Started |
| `M16.67` | move-node changes only the moved subtree's ids; whole-outline renumber becomes explicit | task | Agentic-led | Complete |
| `M16.68` | finish resolves roadmap chunk conflicts the branch only inherited | task | Agentic-led | Complete |
| `M16.69` | Cursor workers launch sandboxed without --force unless the roster opts in | task | Agentic-led | Not Started |
| `M16.70` | Release docs for 0.3.1: README, docs, prompts and the CHANGELOG brought in line with what ships | task | — | Not Started |
| `M17` | 0.3.2: PM GUI shows orchestration and worktree state | phase | Human-led | Not Started |
| `M17.1` | 0.3.2 PM GUI orchestration and worktree view: plan from the snapshot interface | gate | Human-led | Not Started |
| `M18` | Orchestration and review-loop features (after 0.3.1) | phase | — | Not Started |
| `M18.1` | Reviewers check that code is well-formed and that fixes do not degrade it | task | — | Not Started |
| `M18.2` | Harness-facts records for the Copilot CLI and Antigravity agy | task | Agentic-led | Not Started |
| `M18.3` | The shared-checkout guard sees file-tool edits and refuses ending a live peer's session | task | Agentic-led | Not Started |
| `M18.4` | Unattended Codex and Cursor executors warn when reviews are unsigned | task | Agentic-led | Not Started |
| `M18.5` | worker sync prints a paused_until line for a worker paused by a usage limit | task | Agentic-led | Not Started |
| `M18.6` | Per-model review evidence: block rate and overturned approvals feed orchestrate plan | task | Agentic-led | Not Started |
| `M18.7` | review-packet includes sibling repository diffs | task | Agentic-led | Not Started |
| `M18.8` | worker reconcile and the post-run check see sibling repositories | task | Agentic-led | Not Started |
| `M18.9` | The implementation-zone check runs before a review is spent, and knows about sibling repositories | task | Agentic-led | Not Started |
| `M18.10` | review rca launches the root-cause analyst like review delegate, and says what to do when no analyst is available | task | Agentic-led | Not Started |
| `M18.11` | Host effects policy: workers and reviewers do not take over the screen or change shared services, the guard denies such commands, and a message can interrupt a turn | task | Agentic-led | Not Started |
| `M18.12` | Role-observed acceptance needs evidence from that role, and coordinator probes are not acceptance | task | Agentic-led | Not Started |
| `M18.13` | Touch zones that miss what acceptance needs are flagged at plan time, and the brief's zone section stays short | task | Agentic-led | Not Started |
| `M18.14` | A change to the shared stash is attributed to the worker whose branch made it, not to whichever worker's turn ended while the entry existed | task | Agentic-led | Not Started |
| `M18.15` | --rework carries blocks at the branch tip as required changes, lists older blocks as possibly resolved, and takes a coordinator note placed above the reviews | task | Agentic-led | Not Started |
| `M18.16` | A review that stops before filing leaves a trace: every reviewer channel opens a RUN record, and review list shows started but not filed | task | Agentic-led | Not Started |
| `M18.17` | Under delta review, one approval per round still checks the whole leaf against the merge base on a fixed checklist | task | Agentic-led | Not Started |
| `M18.18` | Plan review after planning, and a staleness check before pickup | task | Agentic-led | Not Started |
| `M18.19` | orchestrate plan and review delegate apply reviewer preferences from the decisions ledger and say when they do | task | Agentic-led | Not Started |
| `M19` | Adopter-project features: upgrade, agent-file layering, planning hygiene, project tooling (after 0.3.1) | phase | — | Not Started |
| `M19.1` | Configurable code-analysis tools | task | — | Not Started |
| `M19.2` | Research reminders leave validate | task | — | Not Started |
| `M19.3` | The pickup prompt names its base commit | task | Agentic-led | Not Started |
| `M19.4` | The managed block stops naming pickup's --local opt-out | task | Agentic-led | Not Started |
| `M19.5` | A tracked tech-debt ledger that planning can turn into leaves | task | Agentic-led | Not Started |
| `M19.6` | The orchestrator cleans up landed leaves and stale worktrees automatically, saving hand-off files first | task | Agentic-led | Not Started |
| `M19.7` | Notices for how the agent files fit together: missing CLAUDE.md import, two load orders, floor read twice | task | Agentic-led | Not Started |
| `M19.8` | upgrade says what changed for this repo: behaviour changes, a pin below the new minimum, the new files and duplicated paragraphs | task | Agentic-led | Not Started |
| `M19.9` | upgrade --prompt writes an agent upgrade prompt filled in from this repo | task | Agentic-led | Not Started |
| `M19.10` | file-limits can write a baseline of today's exceptions, a failing run points at it, and upgrade reports the file-limits count | task | Agentic-led | Not Started |
| `M19.11` | Chores at parity with leaves: worktree, branch and env_setup on start, widen zones, the review-record path, and work/chores ignored | task | Agentic-led | Not Started |
| `M19.12` | List shipped nodes with no result after N days | milestone | Agentic-led | Not Started |
| `M19.13` | Store a pointer and a human verdict for outcomes, never the metric itself | milestone | Agentic-led | Not Started |
| `M19.14` | Human decisions get recorded and shown: agent rule, digest, review status and decisions add --help | task | Agentic-led | Not Started |
| `M19.15` | Decision ids take a project prefix (default DEC-) and warn when a new id already appears in governance files | task | Agentic-led | Not Started |
| `M19.16` | validate notices sheet acceptance that drifted from the node, and gate dependencies the gate never names | task | Agentic-led | Not Started |
| `M19.17` | validate notices governance files that require a field validate strips, and names the replacement | task | Agentic-led | Not Started |
| `M19.18` | A ratified scope boundary in the decisions ledger, with validate and digest notices for phases beyond it | task | Agentic-led | Not Started |
| `M20` | Agent safety and governance posture (after 0.3.1) | phase | — | Not Started |
| `M20.1` | Posture advisor: plan the M20 leaves from the research | task | Human-led | Not Started |
| `M20.2` | Probe each reviewer harness for instruction-file leakage into fresh sessions | task | Agentic-led | Not Started |
| `M21` | rc4 stabilization: fixes filed after the themed-milestone rule | phase | — | Not Started |
| `M21.1` | move-node takes a chosen free id or fills the lowest gap; PM GUI moves renumber only the moved subtree | task | Agentic-led | Not Started |
| `M21.2` | CLI indent, outdent and group-nodes re-level siblings in one transaction validated once | task | Agentic-led | Not Started |
| `M21.3` | Opt-in rewrite of prose id references after a move, and a standalone rename-refs | task | Agentic-led | Not Started |
| `M21.4` | remove-node deletes an empty never-started node and names every blocker otherwise | task | Agentic-led | Not Started |
| `M21.5` | apply CHANGES.yaml expresses moves, grouping and removals, rehearsed by --dry-run and validated once | task | Agentic-led | Not Started |
| `M21.6` | validate and add-dependency catch cycles made through inherited group dependencies | task | Agentic-led | Complete |
| `M21.7` | Executors cannot change the files that steer harnesses and specy-road unnoticed | task | Agentic-led | Not Started |
| `M21.8` | The queued-message worker test waits for the idle state, not just the second completion event | task | — | Complete |
| `M21.9` | A freshly initialized project passes its own checks | task | — | Not Started |
| `M21.10` | doctor works in a repo with no remote | task | — | Not Started |
| `M21.11` | Help text names installed commands | task | — | Complete |
| `M21.12` | A review record is refused for joined observations only when one of them names a defect | task | — | Not Started |

Chunk files (authoritative definitions): see [`roadmap/manifest.json`](roadmap/manifest.json) `includes` (e.g. [`roadmap/phases/`](roadmap/phases/)).
