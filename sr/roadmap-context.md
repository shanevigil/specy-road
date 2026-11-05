# Roadmap context

<!-- specy-road: generated context digest — do not edit by hand. Regenerate with `specy-road digest`. -->

The current state of this project's roadmap, generated from the merged graph, the archive ledger and git history. Read this before crawling `planning/` or `work/` — it is the authoritative summary, and those directories contain a great deal of duplicated text.

## Live roadmap

Status is the computed rollup: a non-leaf is Complete only when every leaf descendant is.

- `M1` Adopt specy-road `adopt-specy-road` — phase — **Complete**
  - `M1.1` Set up the project's specy-road basics `project-setup` — task — **Complete**
- `M2` Outcome record pilot `outcome-record-pilot` — phase — **Not Started**
  - `M2.1` List shipped nodes with no result after N days `list-shipped-nodes-with-no-result-after-n-days` — milestone — **Not Started**
  - `M2.2` Store a pointer and a human verdict for outcomes, never the metric itself `store-a-pointer-and-a-human-verdict-for-outcomes-never-the-metric-itself` — milestone — **Not Started**
- `M3` 0.3.1 pre-final fixes from rc1 feedback `pre-final-fixes` — phase — **Complete**
  - `M3.1` Refuse to pick up leaves whose planning sheet is still a placeholder `unauthored-leaf-guard` — task — **Complete**
  - `M3.2` handoff status reports review records without a claim `handoff-local-records` — task — **Complete**
  - `M3.3` Document the canonical chunk key order and offer a deliberate normalisation `chunk-key-order` — task — **Complete**
  - `M3.4` Brainstorm prompts: shards from the allocation, per-pass files, framing with proposed answers `brainstorm-prompt-fixes` — task — **Complete**
  - `M3.5` Converge and evidence passes that cannot silently skip work `brainstorm-converge-checks` — task — **Complete**
  - `M3.6` Triage commands: realize, append-why, summary, consistent reasons, all-or-nothing accept `brainstorm-triage-cli` — task — **Complete**
  - `M3.7` promote writes usable nodes once, with short codenames `promote-node-quality` — task — **Complete**
  - `M3.8` Upgrade and validate report drift and migrations plainly `upgrade-and-validate-checks` — task — **Complete**
  - `M3.9` Worker and session CLI: resume permissions, roster provenance, event gaps `worker-cli-fixes` — task — **Complete**
  - `M3.10` Worker hand-off, reconcile and finish report what actually happened `worker-reconcile-and-status` — task — **Complete**
  - `M3.11` Roster ids with effort suffixes, packet path, stale sessions `roster-profiles-and-packet-path` — task — **Complete**
  - `M3.12` A baseline gate runs on the integration branch before pickup `a-baseline-gate-runs-on-the-integration-branch-before-pickup` — task — **Complete**
  - `M3.13` A trial merge with the integration branch runs before review and before finish `a-trial-merge-with-the-integration-branch-runs-before-review-and-before-finish` — task — **Complete**
  - `M3.14` finish-this-task and pickup detect a planning sheet that is still the scaffold `finish-this-task-and-pickup-detect-a-planning-sheet-that-is-still-the-scaffold` — task — **Complete**
  - `M3.15` Read-only review commands take --ref, handoff status exit codes are distinct, review list, and an orchestration.yaml starter `read-only-review-commands-take-ref-handoff-status-exit-codes-are-distinct-review-list-and-an-orchestration-yaml-starter` — task — **Complete**
  - `M3.16` Bring worker_cli and worker_adapters back under the 400-line cap `bring-worker-cli-and-worker-adapters-back-under-the-400-line-cap` — task — **Complete**
  - `M3.17` A failing verifier in the READY file blocks the gate unless a reviewer marks it as already failing on the integration branch `a-failing-verifier-in-the-ready-file-blocks-the-gate-unless-a-reviewer-marks-it-as-already-failing-on-the-integration-branch` — task — **Complete**
  - `M3.18` Bring role_prompt under the file cap and clear the ruff complexity error `bring-role-prompt-under-the-file-cap-and-clear-the-ruff-complexity-error` — task — **Complete**
- `M4` Brainstorm and roadmap editing features `brainstorm-editing-features` — phase — **Complete**
  - `M4.1` promote carries the converge judgement into sheets and writes an authoring prompt `promote-judgement` — task — **Complete**
  - `M4.2` Structured promote: target parents, clusters, minimum recommendation, plan file `promote-structured` — task — **Complete**
  - `M4.3` Batch ideas and verdicts from a file, merge, and gap ideas `brainstorm-batch-io` — task — **Complete**
  - `M4.4` Policies and decisions as first-class brainstorm outcomes; frame amendments `brainstorm-decisions` — task — **Complete**
  - `M4.5` Repository files as evidence; null results; quotes on research-born ideas `brainstorm-repo-evidence` — task — **Complete**
  - `M4.6` Lenses from the frame and a ranked node list in the recommend prompt `brainstorm-lenses` — task — **Complete**
  - `M4.7` Scriptable graph edits: apply a change file with dry run, acceptance at creation, display-id dependencies `graph-apply` — task — **Complete**
  - `M4.8` list-nodes --json, refresh-stubs --diff, move-node zone rewrite `graph-listing-and-moves` — task — **Complete**
  - `M4.9` Opt-in auto-pick ordering by execution milestone `pick-ordering` — task — **Complete**
  - `M4.10` Clean up merged feature branches after finish `branch-cleanup` — task — **Complete**
  - `M4.11` grind-session --plan keeps ready leaves with overlapping touch zones out of the same parallel wave `grind-session-plan-keeps-ready-leaves-with-overlapping-touch-zones-out-of-the-same-parallel-wave` — task — **Complete**
  - `M4.12` file-limits function-length check covers TypeScript and JavaScript `file-limits-function-length-check-covers-typescript-and-javascript` — task — **Complete**
  - `M4.13` specy-road doctor lists merged or stale feature branches, worktrees, registry rows and stashes `specy-road-doctor-lists-merged-or-stale-feature-branches-worktrees-registry-rows-and-stashes` — task — **Complete**
  - `M4.14` brainstorm promote inherits execution_milestone from the anchor `brainstorm-promote-inherits-execution-milestone-from-the-anchor` — task — **Complete**
  - `M4.15` Session overlap warnings name the other worktree and its edit state `session-overlap-warnings-name-the-other-worktree-and-its-edit-state` — task — **Complete**
  - `M4.16` Review rounds and elapsed time per leaf, and doctor lists detached worktrees `review-rounds-and-elapsed-time-per-leaf-and-doctor-lists-detached-worktrees` — task — **Complete**
  - `M4.17` Review-loop escalation: a root-cause analysis runs when reviews keep blocking `review-loop-escalation-a-root-cause-analysis-runs-when-reviews-keep-blocking` — task — **Complete**
  - `M4.18` Further TS/JS syntax forms for the function cap found in M4.12 review `further-ts-js-syntax-forms-for-the-function-cap-found-in-m4-12-review` — task — **Complete**
- `M5` Agent context and outcomes `context-and-outcomes` — phase — **In Progress**
  - `M5.1` Every managed AGENTS.md rule carries its provenance in the template `rule-provenance` — task — **Complete**
  - `M5.2` validate flags specy-road commands that do not exist in the consumer's agent files `stale-command-check` — task — **Complete**
  - `M5.3` validate reports always-injected context per harness against documented limits `context-budget-meter` — task — **Complete**
  - `M5.4` Rules the CLI or hooks enforce shrink to one-line pointers in the managed block `enforced-rules-pointers` — task — **Complete**
  - `M5.5` A replayable context regression set for the sandbox runbook `context-regression-set` — task — **Complete**
  - `M5.6` Pilot the context-feedback question in the sandbox before shipping it `context-feedback-pilot` — task — **Complete**
  - `M5.7` Measure the managed section on and off across the sandbox apps `managed-section-ablation` — task — **Complete**
  - `M5.8` Further Markdown mention forms for the stale-command check found in M5.2 review `further-markdown-mention-forms-for-the-stale-command-check-found-in-m5-2-review` — task — **Complete**
- `M6` 0.3.1-rc2 release `release-0-3-1-rc2` — phase — **In Progress**
  - `M6.1` Close out the triage note, changelog and what's-new for rc2 `rc2-closeout-docs` — task — **Complete**
  - `M6.2` Pre-release checks and the 0.3.1-rc2 cut `rc2-cut` — task — **Complete**
- `M7` Keeping current: recurring research `keeping-current-recurring-research` — phase — **In Progress**
  - `M7.1` A research register tracks deep-research topics with a refresh cadence `a-research-register-tracks-deep-research-topics-with-a-refresh-cadence` — task — **Complete**
  - `M7.2` Run the harness-capabilities research and fold its findings `run-the-harness-capabilities-research-and-fold-its-findings` — task — **Complete**
- `M8` Harness compatibility `harness-compatibility` — phase — **In Progress**
  - `M8.1` Harness facts fixture drives model-profiles and executor templates, with a classified diff on version bumps `harness-facts-fixture-drives-model-profiles-and-executor-templates-with-a-classified-diff-on-version-bumps` — task — **Complete**
  - `M8.2` Worker adapters harden the launch and run a deterministic post-run check `worker-adapters-harden-the-launch-and-run-a-deterministic-post-run-check` — task — **Complete**
  - `M8.3` Reviewer runs are read-only and specy-road writes the review record from structured output `reviewer-runs-are-read-only-and-specy-road-writes-the-review-record-from-structured-output` — task — **Complete**
  - `M8.4` Ship skills once and meter every file each harness injects `ship-skills-once-and-meter-every-file-each-harness-injects` — task — **Complete**
  - `M8.5` Guard hooks per harness and avoid lists in every model profile `guard-hooks-per-harness-and-avoid-lists-in-every-model-profile` — task — **Complete**
  - `M8.7` Runtime verification of the harness facts against installed binaries `runtime-verification-of-the-harness-facts-against-installed-binaries` — task — **Complete**
  - `M8.6` Candidate harness profiles: Copilot CLI reviewer and Antigravity agy generic `candidate-harness-profiles-copilot-cli-reviewer-and-antigravity-agy-generic` — task — **Complete**
- `M9` Regression prevention `regression-prevention` — phase — **In Progress**
  - `M9.1` finish-this-task runs a configured land check on the merge commit before it pushes `land-check-on-merge-commit` — task — **Complete**
  - `M9.2` pytest refuses to start while tests/fixtures holds ignored files, and fails when a run changes the fixture tree `fixture-pollution-guard` — task — **Complete**
  - `M9.3` Finish, the packet and a finish re-run are tested in a nested layout whose leaf also changes a file outside the project `layout-with-outside-change` — task — **Complete**
  - `M9.4` An executor that cannot meet a criterion without weakening a test or a baseline records blocked_on in READY, and the gate stays unmet `executor-blocked-on` — task — **Complete**
  - `M9.5` specy-road integrity reports removed tests, new skips, lost asserts and test-config changes on a leaf, and the packet shows them `integrity-report` — task — **Complete**
  - `M9.6` With integrity_gate on, a test-integrity finding blocks the review gate unless the leaf declared it before pickup `integrity-gate-and-waivers` — task — **Complete**
  - `M9.7` specy-road integrity also reports new lint suppressions and widened baseline files `suppression-and-ratchet-findings` — task — **Complete**
  - `M9.8` A pre-existing verifier failure counts only when specy-road reproduced it twice on the integration tip `verified-pre-existing-claims` — task — **Complete**
  - `M9.9` The executor prompt and the review packet list the Python tests that import the leaf's code `tests-at-risk` — task — **Complete**
  - `M9.10` Opt-in red-green evidence: tests a leaf adds or changes fail on the base commit and pass at head `red-green-evidence` — task — **Complete**
  - `M9.11` Touch-zone checks match project-relative and git-root-relative paths alike in a nested project `nested-zone-paths` — task — **Complete**
- `M10` Agent loop performance and observability `agent-loop-performance` — phase — **In Progress**
  - `M10.1` Record phase timestamps in the event log and print a per-leaf timeline `record-phase-timestamps-in` — task — **Complete**
  - `M10.2` Normalised usage event in the worker log `normalised-usage-event-in` — task — **Complete**
  - `M10.3` Replace per-worker polling with a single mailbox flag file and a foreground --wait `replace-per-worker-polling-with` — task — **Complete**
  - `M10.4` Pin harness discovery mode per profile `pin-harness-discovery-mode` — task — **Complete**
  - `M10.5` Per-role effort in model profiles `per-role-effort-in-model` — task — **Complete**
  - `M10.6` Measure whether lower reviewer effort changes verdicts `measure-whether-lower-reviewer` — task — **Complete**
  - `M10.7` Output budgets with --full on packets, briefs and plans `output-budgets-with-full` — task — **Complete**
  - `M10.8` Reviewers launch without repo hooks or MCP `reviewers-launch-without-repo` — task — **Complete**
  - `M10.9` Emit a stalled event when a worker goes silent past a threshold `emit-a-stalled-event` — task — **Complete**
  - `M10.10` Position the docs on governance, not on CLI workers `position-the-docs-on` — task — **Complete**
  - `M10.11` Document the harness-subagent recipe for parallel work inside a leaf `document-the-harness-subagent-recipe` — task — **Complete**
  - `M10.12` Visual explorer for worker event logs in the PM GUI `visual-explorer-for-worker` — task — **Complete**
  - `M10.13` A project setting decides whether agent logs are tracked in git `a-project-setting-decides` — task — **Complete**
  - `M10.14` edit-node keeps an active claim's touch zones in step with the node `claim-zones-follow-edit-node` — task — **Complete**
  - `M10.15` Executor prompt keeps long commands in the foreground so a headless turn does not end before its tests finish `foreground-long-commands` — task — **Complete**
  - `M10.16` The worker wrapper imports the launching specy-road, not the worktree's copy `wrapper-imports-launcher` — task — **Complete**
  - `M10.17` The review packet caps its inlined diff by bytes too and lists generated bundles by size only `packet-byte-budget` — task — **Complete**
  - `M10.18` Review records are found and written with the canonical file name on case-insensitive filesystems `review-file-case` — task — **Complete**
  - `M10.19` The executor prompt forbids killing processes the executor did not start `no-foreign-kills` — task — **Complete**
  - `M10.20` Pilot GPT-6.1 Terra as a lower-cost executor before rostering it `terra-executor-pilot` — task — **Complete**
- `M11` rc2 field feedback: worktrees, workers and the review loop `rc2-field-feedback` — phase — **In Progress**
  - `M11.1` In a git worktree, every command resolves work/ paths the same way and a sandboxed reviewer can file its record `worktree-paths-agree` — task — **Complete**
  - `M11.2` worker message resumes a failed or stalled worker whose native session id is known `resume-failed-workers` — task — **Complete**
  - `M11.3` specy-road's own runtime directories never fail the clean-tree checks `runtime-dirs-not-dirty` — task — **Complete**
  - `M11.4` max_workers counts live workers across checkouts and applies to resumes `max-workers-global` — task — **Complete**
  - `M11.5` Pickup's stale-claim check tests the local branch and never advises deleting a live claim `pickup-claim-heuristic` — task — **Complete**
  - `M11.6` worker reconcile judges a worker against the leaf's current contract `reconcile-current-contract` — task — **Complete**
  - `M11.7` review delegate runs a rostered reviewer like worker delegate runs an executor `review-delegate` — task — **Complete**
  - `M11.8` An opt-in delta review packet for small fix rounds `delta-review-packet` — task — **Complete**
  - `M11.9` Acceptance items a human must satisfy are marked and handled as such `human-acceptance` — task — **Complete**
  - `M11.10` edit-node can add and remove single list entries `edit-node-add-remove` — task — **Complete**
  - `M11.11` orchestrate plan, grind-session --plan and pickup share one readiness rule and rank executors by class and billing route `one-readiness-rule` — task — **Complete**
  - `M11.12` specy-road ready writes a valid READY hand-off `ready-command` — task — **Complete**
  - `M11.13` A milestone gets one full review of its combined change before it is marked complete `milestone-full-review` — task — **Complete**
  - `M11.14` worker message queues a follow-up for a worker whose turn is still running `queue-worker-message` — task — **Complete**
  - `M11.15` Pickup and finish agree on unwritten planning sheets `pickup-refuses-scaffold-sheet` — task — **Complete**
  - `M11.16` A commit that changes only planning or bookkeeping files keeps existing approvals `sheet-edits-keep-approvals` — task — **Complete**
  - `M11.17` edit-node names every chunk file it changes, and relocation is loud `edit-node-names-chunks` — task — **Complete**
  - `M11.18` Registry overlap warnings show only what concerns the command at hand `quieter-overlap-warnings` — task — **Complete**
  - `M11.19` Pickup never stashes work/ around the registry commit `pickup-no-work-stash` — task — **Complete**
  - `M11.20` orchestrate plan and validate say where the roster is read from `roster-source-explained` — task — **Complete**
  - `M11.22` Worker worktrees can include nested sibling repositories `nested-repo-worktrees` — task — **Complete**
  - `M11.23` A custom launch command's permissions carry through resume `resume-keeps-permissions` — task — **Complete**
  - `M11.24` Executors and reviewers in a worktree can write and check the right places `worktree-handoff-writable` — task — **Complete**
  - `M11.25` finish-this-task says what merge mode will push before it pushes `merge-push-disclosure` — task — **Complete**
  - `M11.26` A model profile can match harness model ids that carry an effort suffix `profile-aliases` — task — **Complete**
  - `M11.27` Small CLI fixes from field use `small-cli-fixes` — task — **Complete**
  - `M11.28` A light chore mode for work outside the roadmap `chore-mode` — task — **Complete**
  - `M11.29` doctor warns when the running specy-road is older than the project's stubs `doctor-version-skew` — task — **Complete**
  - `M11.30` Leaf worktrees get the project's environment set up `worktree-env-setup` — task — **Complete**
  - `M11.31` A safe command to retire a leaf worktree `worktree-prune` — task — **Complete**
  - `M11.32` Unpushed nested-repo commits are reported `nested-unpushed-report` — task — **Complete**
  - `M11.33` A reviewer whose harness routes models dynamically does not count as an independent family by default `dynamic-routing-reviewers` — task — **Complete**
  - `M11.34` Open human decisions live in one tracked ledger and every question is self-contained `decision-ledger` — task — **Complete**
  - `M11.35` A roster entry maps to the harness's own model id, and a failed start says why `roster-harness-model-id` — task — **Complete**
  - `M11.36` A resumed reviewer session may approve a delta it was shown `resumed-delta-approval` — task — **Complete**
  - `M11.37` review-packet warns when the brief or summary names a file not committed at the reviewed commit `packet-uncommitted-refs` — task — **Complete**
  - `M11.38` handoff status says who can still supply a missing approval `handoff-eligible-reviewers` — task — **Complete**
  - `M11.39` A roster entry can be marked unavailable without deleting it `roster-availability` — task — **Complete**
  - `M11.40` worker reconcile works on merged leaves and separates untracked files `reconcile-merged-and-untracked` — task — **Complete**
  - `M11.41` The two review-gate settings cannot silently disagree `gate-config-agree` — task — **Complete**
  - `M11.42` session end finds the session the same agent started `session-end-default` — task — **Complete**
  - `M11.43` init project reports exactly what it writes `init-project-reports-writes` — task — **Complete**
  - `M11.44` init project can install only the model profiles a project uses `init-profiles-subset` — task — **Complete**
  - `M11.45` The stale-command warning fires only on command-shaped mentions `stale-command-prose` — task — **Complete**
  - `M11.46` Placeholder leaves neither fail validate --strict nor pad briefs `placeholder-leaves-strict-brief` — task — **Complete**
  - `M11.47` validate checks git-root touch zones in a nested project `validate-zones-git-root` — task — **Complete**
  - `M11.48` A claimed leaf reads as claimed in list-nodes and brief `claimed-leaf-status` — task — **Complete**
  - `M11.49` The review packet takes touch zones from the reviewed commit and treats lockfiles as generated `packet-zones-at-commit` — task — **Complete**
  - `M11.50` finish keeps a committed implementation summary in history `finish-keeps-summary` — task — **Complete**
  - `M11.51` Dashboard saves never overwrite newer disk edits, and the read API is documented `dashboard-safe-saves` — task — **Complete**
  - `M11.52` PR mode predicts and resolves the registry conflict `pr-mode-registry-conflict` — task — **Complete**
  - `M11.53` A worktree-based flow can claim leaves without pushing from the worktree `pickup-into-worktree` — task — **Complete**
  - `M11.54` The test suite and land check run in parallel `parallel-test-suite` — task — **Complete**
  - `M11.55` Executors split modules to meet file limits instead of deleting documentation `file-limit-split-not-delete` — task — **Complete**
  - `M11.56` Delegate creates the reviews directory before a harness is told to allow it `reviews-dir-before-launch` — task — **Complete**
  - `M11.57` A completed worker on a finished leaf does not hold a max_workers slot `completed-worker-frees-slot` — task — **Complete**
  - `M11.58` The coordinator records the session's routing preferences where the next session can read them `session-routing-preferences` — task — **Complete**
  - `M11.59` Split worker_ops and worker_adapters so parallel leaves stop colliding `split-worker-modules` — task — **Complete**
  - `M11.62` Headless runs report usage limits and denied actions instead of looking like success `headless-limits-denials` — task — **Complete**
  - `M11.60` The harness facts fixture takes the 2026-11-02 sourced findings and watches the new scope-escape feature names `harness-facts-nov-refresh` — task — **Complete**
  - `M11.61` The context meter counts Claude rules, auto memory, Cursor nested AGENTS.md and Copilot path instructions `meter-claude-rules-and-nested` — task — **Complete**
  - `M11.63` do-next-available-task refuses a second claim in a checkout that already holds one `pickup-second-claim-guard` — task — **Complete**
  - `M11.64` abort-task-pickup treats untracked files the way pickup does `abort-untracked-like-pickup` — task — **Complete**
  - `M11.65` why-blocked reports touch-zone holds from the plan `why-blocked-plan-holds` — task — **Complete**
  - `M11.66` specy-road --version identifies the code when run from a checkout `version-shows-checkout-sha` — task — **Complete**
  - `M11.67` Worker usage prices Cursor runs from the roster's price table `cursor-usage-cost` — task — **Complete**
  - `M11.68` A re-delegated executor starts from the blocking review findings `rework-findings-in-prompt` — task — **Complete**
  - `M11.69` A leaf that adds a schema key can be gated and finished `branch-schema-for-gate-and-finish` — task — **Complete**
  - `M11.70` Touch zones are checked when they are written `zones-checked-at-authoring` — task — **Complete**
  - `M11.71` Review loops escalate on their own and criteria are written with bounds `review-loops-escalate` — task — **Complete**
  - `M11.72` A reviewer run that ends without a record is reported as a failure `reviewer-failure-visible` — task — **Complete**
  - `M11.73` specy-road ready warns when the leaf no longer merges cleanly `ready-warns-integration-conflict` — task — **Complete**
  - `M11.74` Pickup and finish in one checkout take a shared lock in order `pickup-finish-shared-lock` — task — **Complete**
  - `M11.75` Reviewer prompt asks for independent probes, not the executor's own checks `reviewer-probe-rules` — task — **Complete**
  - `M11.76` Every roster model reaches its profile notes `profile-alias-coverage` — task — **Complete**
  - `M11.77` A completed reviewer run does not report a missing record `run-record-no-false-failure` — task — **Complete**
  - `M11.78` Review lessons: escaped defect classes feed every reviewer prompt `review-lessons` — task — **Complete**
  - `M11.79` Leaves that touch high-risk zones need a stronger reviewer `risk-tiered-review` — task — **Complete**
  - `M11.80` Executors and reviewers run tests with a bounded worker count `test-worker-cap` — task — **Complete**
  - `M11.82` The integration branch passes ruff again and the land check runs it `wip-ruff-clean` — task — **Complete**
- `M12` Harness engineering: cheaper gates, clearer refusals, less drift `harness-engineering-cheaper-gates-clearer-refusals-less-drift` — phase — **Not Started**
  - `M12.1` A review fix-round budget that defers new-input-class findings to a follow-up leaf `a-review-fix-round-budget-that-defers-new-input-class-findings-to-a-follow-up-leaf` — task — **Complete**
  - `M12.2` Every refusal names its fix `every-refusal-names-its-fix` — task — **Complete**
  - `M12.3` Scheduled gardening chores that find drift and open small chore leaves `scheduled-gardening-chores-that-find-drift-and-open-small-chore-leaves` — task — **Complete**
  - `M12.4` Quality signals agents and PMs read first `quality-signals-agents-and-pms-read-first` — milestone — **Not Started**
    - `M12.4.1` Per-area quality scores in the digest from review history `per-area-quality-scores-in-the-digest-from-review-history` — task — **Complete**
    - `M12.4.2` A tracked tech-debt ledger that planning can turn into leaves `a-tracked-tech-debt-ledger-that-planning-can-turn-into-leaves` — task — **Not Started**
    - `M12.4.3` Per-model review evidence: block rate and overturned approvals feed orchestrate plan `per-model-review-evidence-block-rate-and-overturned-approvals-feed-orchestrate-plan` — task — **Not Started**
  - `M12.5` The orchestrator cleans up landed leaves and stale worktrees automatically, saving hand-off files first `the-orchestrator-cleans-up-landed-leaves-and-stale-worktrees-automatically-saving-hand-off-files-first` — task — **Not Started**
  - `M12.6` Every command exposes its parser, and the stale-command scan reports flags a command does not accept `every-command-exposes-its-parser-and-the-stale-command-scan-reports-flags-a-command-does-not-accept` — task — **Not Started**
- `M13` rc3 adopter feedback: upgrade and adoption friction `rc3-adopter-feedback-upgrade-and-adoption-friction` — phase — **Not Started**
  - `M13.1` Say which install is running and flag managed blocks an older version wrote `say-which-install-is-running-and-flag-managed-blocks-an-older-version-wrote` — task — **Complete**
  - `M13.2` upgrade previews as the new version, validates in a dry run and names files it pushed over the line cap `upgrade-previews-as-the-new-version-validates-in-a-dry-run-and-names-files-it-pushed-over-the-line-cap` — task — **Complete**
  - `M13.3` A pointer-only AGENTS.md block option, and upgrade names the project text the new rules file duplicates `a-pointer-only-agents-md-block-option-and-upgrade-names-the-project-text-the-new-rules-file-duplicates` — task — **Complete**
  - `M13.4` A milestone held for its full review says so in validate, list-nodes and why-blocked `a-milestone-held-for-its-full-review-says-so-in-validate-list-nodes-and-why-blocked` — task — **Complete**
  - `M13.5` refresh-profiles installs only the profiles the roster names, and suggests the alias for a near miss `refresh-profiles-installs-only-the-profiles-the-roster-names-and-suggests-the-alias-for-a-near-miss` — task — **Complete**
  - `M13.6` Safe release-candidate install recipe, pipx and uv tool upgrades, and checking which binary is on PATH `safe-release-candidate-install-recipe-pipx-and-uv-tool-upgrades-and-checking-which-binary-is-on-path` — task — **Complete**
  - `M13.7` Clearer notices: symlinked skill dirs, new ignore rules over tracked files, and session end `clearer-notices-symlinked-skill-dirs-new-ignore-rules-over-tracked-files-and-session-end` — task — **Complete**
  - `M13.8` A behaviour-change catalogue, and validate reports project agent text it contradicts `a-behaviour-change-catalogue-and-validate-reports-project-agent-text-it-contradicts` — task — **Complete**
  - `M13.9` Notices for how the agent files fit together: missing CLAUDE.md import, two load orders, floor read twice `notices-for-how-the-agent-files-fit-together-missing-claude-md-import-two-load-orders-floor-read-twice` — task — **Not Started**
  - `M13.10` Upgrade guide: moving to the split rules files, previewing an uninstalled version, telling old installs apart `upgrade-guide-moving-to-the-split-rules-files-previewing-an-uninstalled-version-telling-old-installs-apart` — task — **Complete**
  - `M13.11` upgrade says what changed for this repo: behaviour changes, a pin below the new minimum, the new files and duplicated paragraphs `upgrade-says-what-changed-for-this-repo-behaviour-changes-a-pin-below-the-new-minimum-the-new-files-and-duplicated-paragraphs` — task — **Not Started**
  - `M13.12` Quieter, accurate validate notices: untracked touch zones, the managed .gitignore comment, and tracked files under new ignore rules `quieter-accurate-validate-notices-untracked-touch-zones-the-managed-gitignore-comment-and-tracked-files-under-new-ignore-rules` — task — **Not Started**
  - `M13.13` upgrade --prompt writes an agent upgrade prompt filled in from this repo `upgrade-prompt-writes-an-agent-upgrade-prompt-filled-in-from-this-repo` — task — **Not Started**
  - `M13.14` validate flags project agent text that mandates a changed behaviour (best-effort hint) `validate-flags-project-agent-text-that-mandates-a-changed-behaviour-best-effort-hint` — task — **Not Started**
- `M14` Nested repos and review-gate integrity `nested-repos-and-review-gate-integrity` — phase — **Not Started**
  - `M14.1` Approvals never carry across unreviewed changes in a sibling repository `approvals-never-carry-across-unreviewed-changes-in-a-sibling-repository` — task — **Not Started**
  - `M14.2` doctor never offers to remove a live leaf's worktree or branch `doctor-never-offers-to-remove-a-live-leaf-s-worktree-or-branch` — task — **Complete**
  - `M14.3` worktree prune refuses to delete another repository's worktree or checkout `worktree-prune-refuses-to-delete-another-repository-s-worktree-or-checkout` — task — **Complete**
  - `M14.4` nested_repos that a project can adopt without pushing: local landing, local base, sibling diffs and checks `nested-repos-that-a-project-can-adopt-without-pushing-local-landing-local-base-sibling-diffs-and-checks` — milestone — **Not Started**
    - `M14.4.1` Per nested repository, land by push, locally or by hand, and base worktrees on the remote or local tip `per-nested-repository-land-by-push-locally-or-by-hand-and-base-worktrees-on-the-remote-or-local-tip` — task — **Complete**
    - `M14.4.2` review-packet includes sibling repository diffs `review-packet-includes-sibling-repository-diffs` — task — **Not Started**
    - `M14.4.3` worker reconcile and the post-run check see sibling repositories `worker-reconcile-and-the-post-run-check-see-sibling-repositories` — task — **Not Started**
  - `M14.5` An approve with no recorded probe is flagged, and policy can refuse to count it `an-approve-with-no-recorded-probe-is-flagged-and-policy-can-refuse-to-count-it` — task — **Not Started**
  - `M14.6` Reviewer usage is visible: review usage, reviewers in the node total, RUN logs kept per round `reviewer-usage-is-visible-review-usage-reviewers-in-the-node-total-run-logs-kept-per-round` — task — **Complete**
  - `M14.7` session end finds this agent's session by worktree and branch when the derived id has no record `session-end-finds-this-agent-s-session-by-worktree-and-branch-when-the-derived-id-has-no-record` — task — **Complete**
  - `M14.8` The implementation-zone check runs before a review is spent, and knows about sibling repositories `the-implementation-zone-check-runs-before-a-review-is-spent-and-knows-about-sibling-repositories` — task — **Not Started**
  - `M14.9` review rca launches the root-cause analyst like review delegate, and says what to do when no analyst is available `review-rca-launches-the-root-cause-analyst-like-review-delegate-and-says-what-to-do-when-no-analyst-is-available` — task — **Not Started**
  - `M14.10` Escalation recognises a converging loop and handoff status shows the findings trend `escalation-recognises-a-converging-loop-and-handoff-status-shows-the-findings-trend` — task — **Complete**
  - `M14.11` The rework and fix-round prompt asks the executor to audit the whole failure class and list its probes `the-rework-and-fix-round-prompt-asks-the-executor-to-audit-the-whole-failure-class-and-list-its-probes` — task — **Complete**
- `M15` rc3 adopter feedback: install safety, multi-harness reviewers and parallel-grind friction `rc3-multi-harness-adoption-friction` — phase — **Not Started**
  - `M15.1` RC install docs cover extras and the direct wheel URL, and each RC announcement carries the filled-in command `rc-install-docs-cover-extras-and-direct-wheel-url` — task — **Complete**
  - `M15.2` A Claude Code reviewer works on a subscription login: bare only with an API key, explicit mode otherwise, checked before launch `claude-code-reviewer-works-on-a-subscription-login` — task — **Not Started**
  - `M15.3` prompt --channel cli launches nothing without --run, and a run uses the rostered model in the leaf's worktree; a model the harness did not report as rostered is flagged `prompt-channel-cli-launches-nothing-without-run` — task — **Not Started**
  - `M15.4` Parallel PR-mode leaves reconcile bookkeeping by rule, and pickup's register commit leaves the digest current `parallel-pr-leaves-reconcile-bookkeeping-by-rule` — task — **Complete**
  - `M15.5` Host effects policy: workers and reviewers do not take over the screen or change shared services, the guard denies such commands, and a message can interrupt a turn `host-effects-policy-and-interruptible-worker-messages` — task — **Not Started**
  - `M15.6` The rework prompt carries the accepted root-cause analysis as the governing design, ahead of the reviews' suggested fixes `rework-prompt-carries-the-accepted-rca` — task — **Complete**
  - `M15.7` file-limits can write a baseline of today's exceptions, a failing run points at it, and upgrade reports the file-limits count `file-limits-baseline-and-upgrade-report` — task — **Not Started**
  - `M15.8` A promoted leaf is never stuck: promote's sheet says Approach is written before pickup, and author-approach prints the prompt to write it `promoted-leaf-is-never-stuck-on-an-empty-approach` — task — **Complete**
  - `M15.9` Harness launches survive large prompts and a harness binary off PATH, for every role `harness-launches-survive-large-prompts-and-binaries-off-path` — task — **Not Started**
  - `M15.10` Try a roster before it lands: a dry-run plan from the working tree and local roster entries, and models list shows the uncommitted roster diff `try-a-roster-before-it-lands` — task — **Complete**
  - `M15.11` A working roster in one command, profile values validated locally, consistent ids in docs, and plans that can spread executors `working-roster-in-one-command-and-validated-profiles` — task — **Complete**
  - `M15.12` Shared documentation zones do not serialize grind-session batches `shared-doc-zones-do-not-serialize-batches` — task — **Complete**
  - `M15.13` Worker loop friction: sync waits for the events that matter, tool-use noise collapses, rework after a completed worker, a READY-only resume, a quieter pickup `worker-loop-friction-sync-until-and-ready-only-resume` — task — **Complete**
  - `M15.14` Chores at parity with leaves: worktree, branch and env_setup on start, widen zones, the review-record path, and work/chores ignored `chores-at-parity-with-leaves` — task — **Not Started**
  - `M15.15` upgrade ships the work/ templates every prompt references, and the .specyrd README matches upgrade's steps `upgrade-ships-the-templates-prompts-reference` — task — **Complete**
  - `M15.16` Role-observed acceptance needs evidence from that role, and coordinator probes are not acceptance `role-observed-acceptance-needs-that-role` — task — **Not Started**
  - `M15.17` Review friction: delegate builds a missing packet, the packet skips ignored evidence and numbers suppressions correctly, refusals quote the line, and superseded failed runs say so `review-friction-packet-and-record` — task — **Not Started**
  - `M15.18` planned_test_changes can be edited after pickup, and an unplanned test removal is a required reviewer check `planned-test-changes-editable-and-removals-surfaced` — task — **Complete**
  - `M15.19` Cursor worker cost is estimated when the harness reports a display name for the rostered model `cursor-cost-with-display-name-models` — task — **Complete**
  - `M15.20` Touch zones that miss what acceptance needs are flagged at plan time, and the brief's zone section stays short `zones-missing-what-acceptance-needs-flagged` — task — **Not Started**
  - `M15.21` Linked worktrees: commands resolve the enclosing worktree, and env_setup handles symlinked environments `linked-worktrees-resolve-root-and-symlinked-envs` — task — **Complete**
  - `M15.22` Project preferences the workflow respects: local decisions, a PR body footer, the summary commit rule, and local landing for the root repository `project-preferences-local-decisions-footer-summary-landing` — task — **Complete**
  - `M15.23` A project declares its merge-blocking CI commands per touch zone; ready always runs them and the review packet shows their result at the reviewed commit `ci-gates-run-by-ready-and-shown-in-the-packet` — task — **Not Started**
  - `M15.24` ready does not record false evidence: a passing run whose output shows a failed command is flagged, and --run-argv runs a command without a shell `ready-flags-failure-tails-and-takes-argv` — task — **Complete**
  - `M15.25` A change to the shared stash is attributed to the worker whose branch made it, not to whichever worker's turn ended while the entry existed `stash-changes-attributed-to-the-owning-branch` — task — **Not Started**
  - `M15.26` A claim left with no worker is never silent: finished workers free their max_workers slot, handoff status and doctor list orphaned claims, and a failed delegate says how to resolve its claim `claims-with-no-worker-are-reported-and-never-hold-slots` — task — **Not Started**
  - `M15.27` worker usage counts every usage-bearing event of a long Cursor turn and marks a turn whose output tokens are implausibly low for its length `cursor-usage-sums-segments-and-flags-undercounts` — task — **Not Started**
  - `M15.28` --rework carries blocks at the branch tip as required changes, lists older blocks as possibly resolved, and takes a coordinator note placed above the reviews `rework-carries-current-blocks-and-a-coordinator-note` — task — **Not Started**
  - `M15.29` A review that stops before filing leaves a trace: every reviewer channel opens a RUN record, and review list shows started but not filed `every-reviewer-channel-leaves-a-run-record` — task — **Not Started**
  - `M15.30` Under delta review, one approval per round still checks the whole leaf against the merge base on a fixed checklist `one-full-leaf-checklist-review-per-round` — task — **Not Started**
- `M16` lean core: harden and optimize code and docs, all delivered functionality kept `lean-core` — phase — **Not Started**
  - `M16.0` Parity harness: command inventory, golden --help transcripts, an end-to-end leaf loop and dogfood outputs `parity-harness-command-inventory-golden-help-transcripts-an-end-to-end-leaf-loop-and-dogfood-outputs` — task — **Not Started**
  - `M16.1` Parity harness: a review-gate decision table covering every review policy `parity-harness-a-review-gate-decision-table-covering-every-review-policy` — task — **Not Started**
  - `M16.2` Baseline metrics, a coverage floor in CI, and the M16 working rules written down `baseline-metrics-a-coverage-floor-in-ci-and-the-m16-working-rules-written-down` — task — **Not Started**
  - `M16.3` Delete dead and unwired code, and add vulture as an advisory CI step `delete-dead-and-unwired-code-and-add-vulture-as-an-advisory-ci-step` — task — **Not Started**
  - `M16.4` Shared helpers for time, atomic writes, git queries and registry I/O replace their copies `shared-helpers-for-time-atomic-writes-git-queries-and-registry-i-o-replace-their-copies` — task — **Not Started**
  - `M16.5` One roadmap index answers every graph query: by id, by key, effective dependencies, unmet, ready `one-roadmap-index-answers-every-graph-query-by-id-by-key-effective-dependencies-unmet-ready` — task — **Not Started**
  - `M16.6` Library code moves out of bundled_scripts, the two large import cycles are broken, and a layering gate keeps them broken `library-code-moves-out-of-bundled-scripts-the-two-large-import-cycles-are-broken-and-a-layering-gate-keeps-them-broken` — task — **Not Started**
  - `M16.7` Commands run in-process with lazy imports, one error type and shared argument helpers `commands-run-in-process-with-lazy-imports-one-error-type-and-shared-argument-helpers` — task — **Not Started**
  - `M16.8` A 100-character line-width rule with a shrink-only baseline, and the consumer file-limit default decided `a-100-character-line-width-rule-with-a-shrink-only-baseline-and-the-consumer-file-limit-default-decided` — task — **Not Started**
  - `M16.9` Fold the cap-driven splits in pickup, finish, milestone and the PM UI server into their parents `fold-the-cap-driven-splits-in-pickup-finish-milestone-and-the-pm-ui-server-into-their-parents` — task — **Not Started**
  - `M16.10` Fold brainstorm, agent-file and miscellaneous splits, and extract one LLM client from review_node `fold-brainstorm-agent-file-and-miscellaneous-splits-and-extract-one-llm-client-from-review-node` — task — **Not Started**
  - `M16.11` doctor --prune is the one cleanup path; branches prune, registry-prune and the grind cleanup become aliases `doctor-prune-is-the-one-cleanup-path-branches-prune-registry-prune-and-the-grind-cleanup-become-aliases` — task — **Not Started**
  - `M16.12` upgrade absorbs the refresh commands and prints one report of what changed for the repo; update becomes self-update `upgrade-absorbs-the-refresh-commands-and-prints-one-report-of-what-changed-for-the-repo-update-becomes-self-update` — task — **Not Started**
  - `M16.13` Command groups and renames: milestone, planning, archive --deep, review status, decisions --kind lesson, presence `command-groups-and-renames-milestone-planning-archive-deep-review-status-decisions-kind-lesson-presence` — task — **Not Started**
  - `M16.14` One checks: block replaces baseline_cmd, land_check_cmd and verify_cmd and carries per-zone merge-blocking gates `one-checks-block-replaces-baseline-cmd-land-check-cmd-and-verify-cmd-and-carries-per-zone-merge-blocking-gates` — task — **Not Started**
  - `M16.15` Orchestration subpackage with one public interface and one state model for the gate, the CLI and the PM GUI `orchestration-subpackage-with-one-public-interface-and-one-state-model-for-the-gate-the-cli-and-the-pm-gui` — task — **Not Started**
  - `M16.16` Worker runtime moves into orchestration/workers, the worker_ops facade and its module-class swap go `worker-runtime-moves-into-orchestration-workers-the-worker-ops-facade-and-its-module-class-swap-go` — task — **Not Started**
  - `M16.17` Roster, model profiles, planning and role prompts move into orchestration, with one eligibility check for every launch `roster-model-profiles-planning-and-role-prompts-move-into-orchestration-with-one-eligibility-check-for-every-launch` — task — **Not Started**
  - `M16.18` Shared-checkout guard and session presence move into orchestration, and the guard classifier becomes table-driven `shared-checkout-guard-and-session-presence-move-into-orchestration-and-the-guard-classifier-becomes-table-driven` — task — **Not Started**
  - `M16.19` Grind session, its plan, chores, decisions and lessons move into orchestration, and grind settings live under grind: `grind-session-its-plan-chores-decisions-and-lessons-move-into-orchestration-and-grind-settings-live-under-grind` — task — **Not Started**
  - `M16.20` Review-policy evidence: how often each optional review policy changed a gate outcome `review-policy-evidence-how-often-each-optional-review-policy-changed-a-gate-outcome` — task — **Not Started**
  - `M16.21` Fold the review gate, packet and escalation fragments, and deprecate the policies the evidence did not keep `fold-the-review-gate-packet-and-escalation-fragments-and-deprecate-the-policies-the-evidence-did-not-keep` — task — **Not Started**
  - `M16.22` Post-fix refactor gate: ready and the review packet report the complexity delta, and policy can block on growth `post-fix-refactor-gate-ready-and-the-review-packet-report-the-complexity-delta-and-policy-can-block-on-growth` — task — **Not Started**
  - `M16.23` Tests: shared fixtures in tests/support replace copied helpers and cross-test-file imports `tests-shared-fixtures-in-tests-support-replace-copied-helpers-and-cross-test-file-imports` — task — **Not Started**
  - `M16.24` Tests: one file per module or flow, named for behaviour, in unit, flows, cli, gui and repo lanes `tests-one-file-per-module-or-flow-named-for-behaviour-in-unit-flows-cli-gui-and-repo-lanes` — task — **Not Started**
  - `M16.25` Tests: remove duplicates and fold single-input regressions into tables, with no coverage drop `tests-remove-duplicates-and-fold-single-input-regressions-into-tables-with-no-coverage-drop` — task — **Not Started**
  - `M16.26` Tests: public seams replace private-name patches, property tests cover parsers and transforms, no wall-clock sleeps `tests-public-seams-replace-private-name-patches-property-tests-cover-parsers-and-transforms-no-wall-clock-sleeps` — task — **Not Started**
  - `M16.27` Tests: fill the milestone, outline and edit-field coverage gaps `tests-fill-the-milestone-outline-and-edit-field-coverage-gaps` — task — **Not Started**
  - `M16.28` Tests: a CLI smoke lane of at most 50 subprocess tests, everything else in-process, full suite under 35 s `tests-a-cli-smoke-lane-of-at-most-50-subprocess-tests-everything-else-in-process-full-suite-under-35-s` — task — **Not Started**
  - `M16.29` Constitution names orchestration as part of the product, bounds scope with a 'not' list, and drops contradictions `constitution-names-orchestration-as-part-of-the-product-bounds-scope-with-a-not-list-and-drops-contradictions` — task — **Not Started**
  - `M16.30` AGENTS.md is the one agent entry with a task-conditional load order; CLAUDE.md is a pointer `agents-md-is-the-one-agent-entry-with-a-task-conditional-load-order-claude-md-is-a-pointer` — task — **Not Started**
  - `M16.31` Docs by topic: design notes out of docs/, one workers doc, folded small docs, no pinned release candidate, one GUI extra `docs-by-topic-design-notes-out-of-docs-one-workers-doc-folded-small-docs-no-pinned-release-candidate-one-gui-extra` — task — **Not Started**
  - `M16.32` suggested_prompts follow the real formats: CLI authoring, complete deliverables, no restated rules, nested layout `suggested-prompts-follow-the-real-formats-cli-authoring-complete-deliverables-no-restated-rules-nested-layout` — task — **Not Started**
  - `M16.33` After the next release: delete the deprecated aliases and shims, and check the end-state targets `after-the-next-release-delete-the-deprecated-aliases-and-shims-and-check-the-end-state-targets` — task — **Not Started**
  - `M16.34` Triage: the maintainer decides each held feature leaf not absorbed by an M16 leaf `triage-the-maintainer-decides-each-held-feature-leaf-not-absorbed-by-an-m16-leaf` — task — **Not Started**

## Dependencies that were removed

Someone deliberately dropped these. Check why before re-adding one.

- 2026-10-30 `M10.13` stopped depending on `M10.1 Record phase timestamps in the event log and print a per-leaf timeline`

## Archived (not in the live roadmap)

This work was completed and moved out of the graph. It is deliberately excluded from IDE indexing; reach it with `specy-road search <QUERY> --scope archived`.

- 2026-11-02 `M11.21` (1 node) — `specy-road show-archive M11.21-439c8b26-20261102`

## Claimed and in flight

Do not pick these up.

- `M12.5` on `feature/rm-the-orchestrator-cleans-up-landed-leaves-and-stale-worktrees-automatically-saving-hand-off-files-first` since 2026-11-05
- `M13.12` on `feature/rm-quieter-accurate-validate-notices-untracked-touch-zones-the-managed-gitignore-comment-and-tracked-files-under-new-ignore-rules` since 2026-11-05
- `M13.9` on `feature/rm-notices-for-how-the-agent-files-fit-together-missing-claude-md-import-two-load-orders-floor-read-twice` since 2026-11-05
- `M14.1` on `feature/rm-approvals-never-carry-across-unreviewed-changes-in-a-sibling-repository` since 2026-11-05
- `M14.5` on `feature/rm-an-approve-with-no-recorded-probe-is-flagged-and-policy-can-refuse-to-count-it` since 2026-11-05
- `M15.2` on `feature/rm-claude-code-reviewer-works-on-a-subscription-login` since 2026-11-05
- `M15.20` on `feature/rm-zones-missing-what-acceptance-needs-flagged` since 2026-11-04
- `M15.25` on `feature/rm-stash-changes-attributed-to-the-owning-branch` since 2026-11-05
- `M15.26` on `feature/rm-claims-with-no-worker-are-reported-and-never-hold-slots` since 2026-11-05
- `M15.27` on `feature/rm-cursor-usage-sums-segments-and-flags-undercounts` since 2026-11-05
- `M15.7` on `feature/rm-file-limits-baseline-and-upgrade-report` since 2026-11-05

## Quality by area

Review cost of the last 50 completed leaves, per touch-zone area, from the `Review-tally` trailers on their gate commits. Block rate is the share of tallied leaves with at least one blocking round; areas above 50% are **flagged** and listed first. Plan tighter acceptance there.

| Area | Leaves | No tally | Mean rounds | Block rate | Integrity findings | RCA escalations |
| --- | --- | --- | --- | --- | --- | --- |
| `docs` **flagged** | 36 | 31 | 9.40 | 100% | 10 | 1 |
| `specy_road` **flagged** | 47 | 41 | 8.83 | 100% | 10 | 1 |
| `tests` **flagged** | 49 | 43 | 8.83 | 100% | 10 | 1 |
| `CHANGELOG.md` | 1 | 1 | — | — | 0 | 0 |
| `README.md` | 2 | 2 | — | — | 0 | 0 |
| `gui` | 1 | 1 | — | — | 0 | 0 |
| `research` | 1 | 1 | — | — | 0 | 0 |
| `roadmap` | 2 | 2 | — | — | 0 | 0 |
| `roadmap-context.md` | 1 | 1 | — | — | 0 | 0 |
| `schemas` | 1 | 1 | — | — | 0 | 0 |
| `suggested_prompts` | 1 | 1 | — | — | 0 | 0 |

Leaves with no tally landed before tallies were recorded; they are left out of the rates.

## Reaching the detail behind this

This digest is a summary. The full text of planning sheets, shared contracts and archived work is searchable:

```bash
specy-road search "<query>"                 # live + archived, ranked
specy-road search "<query>" --scope archived  # completed work only
specy-road search <NODE_ID>                  # everything about one node
specy-road history <NODE_ID>                 # how it got to this state
```
