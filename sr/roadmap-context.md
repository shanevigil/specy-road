# Roadmap context

<!-- specy-road: generated context digest — do not edit by hand. Regenerate with `specy-road digest`. -->

The current state of this project's roadmap, generated from the merged graph, the archive ledger and git history. Read this before crawling `planning/` or `work/` — it is the authoritative summary, and those directories contain a great deal of duplicated text.

## Live roadmap

Status is the computed rollup: a non-leaf is Complete only when every leaf descendant is.

- `M15` rc3 adopter feedback: install safety, multi-harness reviewers and parallel-grind friction `rc3-multi-harness-adoption-friction` — phase — **Not Started**
  - `M15.1` RC install docs cover extras and the direct wheel URL, and each RC announcement carries the filled-in command `rc-install-docs-cover-extras-and-direct-wheel-url` — task — **Complete**
  - `M15.2` A Claude Code reviewer works on a subscription login: bare only with an API key, explicit mode otherwise, checked before launch `claude-code-reviewer-works-on-a-subscription-login` — task — **Complete**
  - `M15.3` prompt --channel cli launches nothing without --run, and a run uses the rostered model in the leaf's worktree; a model the harness did not report as rostered is flagged `prompt-channel-cli-launches-nothing-without-run` — task — **Complete**
  - `M15.4` Parallel PR-mode leaves reconcile bookkeeping by rule, and pickup's register commit leaves the digest current `parallel-pr-leaves-reconcile-bookkeeping-by-rule` — task — **Complete**
  - `M15.6` The rework prompt carries the accepted root-cause analysis as the governing design, ahead of the reviews' suggested fixes `rework-prompt-carries-the-accepted-rca` — task — **Complete**
  - `M15.8` A promoted leaf is never stuck: promote's sheet says Approach is written before pickup, and author-approach prints the prompt to write it `promoted-leaf-is-never-stuck-on-an-empty-approach` — task — **Complete**
  - `M15.9` Harness launches survive large prompts and a harness binary off PATH, for every role `harness-launches-survive-large-prompts-and-binaries-off-path` — task — **Complete**
  - `M15.10` Try a roster before it lands: a dry-run plan from the working tree and local roster entries, and models list shows the uncommitted roster diff `try-a-roster-before-it-lands` — task — **Complete**
  - `M15.11` A working roster in one command, profile values validated locally, consistent ids in docs, and plans that can spread executors `working-roster-in-one-command-and-validated-profiles` — task — **Complete**
  - `M15.12` Shared documentation zones do not serialize grind-session batches `shared-doc-zones-do-not-serialize-batches` — task — **Complete**
  - `M15.13` Worker loop friction: sync waits for the events that matter, tool-use noise collapses, rework after a completed worker, a READY-only resume, a quieter pickup `worker-loop-friction-sync-until-and-ready-only-resume` — task — **Complete**
  - `M15.15` upgrade ships the work/ templates every prompt references, and the .specyrd README matches upgrade's steps `upgrade-ships-the-templates-prompts-reference` — task — **Complete**
  - `M15.17` Review friction: delegate builds a missing packet, the packet skips ignored evidence and numbers suppressions correctly, refusals quote the line, and superseded failed runs say so `review-friction-packet-and-record` — task — **Complete**
  - `M15.18` planned_test_changes can be edited after pickup, and an unplanned test removal is a required reviewer check `planned-test-changes-editable-and-removals-surfaced` — task — **Complete**
  - `M15.19` Cursor worker cost is estimated when the harness reports a display name for the rostered model `cursor-cost-with-display-name-models` — task — **Complete**
  - `M15.21` Linked worktrees: commands resolve the enclosing worktree, and env_setup handles symlinked environments `linked-worktrees-resolve-root-and-symlinked-envs` — task — **Complete**
  - `M15.22` Project preferences the workflow respects: local decisions, a PR body footer, the summary commit rule, and local landing for the root repository `project-preferences-local-decisions-footer-summary-landing` — task — **Complete**
  - `M15.24` ready does not record false evidence: a passing run whose output shows a failed command is flagged, and --run-argv runs a command without a shell `ready-flags-failure-tails-and-takes-argv` — task — **Complete**
  - `M15.26` A claim left with no worker is never silent: finished workers free their max_workers slot, handoff status and doctor list orphaned claims, and a failed delegate says how to resolve its claim `claims-with-no-worker-are-reported-and-never-hold-slots` — task — **Complete**
  - `M15.27` worker usage counts every usage-bearing event of a long Cursor turn and marks a turn whose output tokens are implausibly low for its length `cursor-usage-sums-segments-and-flags-undercounts` — task — **Complete**
  - `M15.31` A delegated reviewer always runs a named model: review delegate passes the roster id as worker delegate does, refuses a reviewer with no model, and files the model the harness reported `delegated-reviewer-always-runs-a-named-model` — task — **Not Started**
  - `M15.32` An implementation summary that finish archives to work/done/ is not measured by file-limits, so finish never lands a file-limits failure `archived-summary-exempt-from-file-limits` — task — **Complete**
  - `M15.33` A refused review record leaves a trace: review record writes REJECTED-<model>.md, and review list and handoff status show it until a record is filed `refused-review-record-leaves-a-trace` — task — **Complete**
  - `M15.34` The executor prompt states the test rules that the reviewer's excess checklist enforces `executor-prompt-states-the-test-rules` — task — **Complete**
  - `M15.35` The review packet never lists .git or a path under it as an uncommitted reference `packet-never-lists-dot-git-as-uncommitted` — task — **Complete**
  - `M15.36` Claude Code workers never depend on the -p default mode: auth preflight before launch, explicit mode `worker-launch-never-depends-on-claude-default-mode` — task — **Complete**
  - `M15.37` Review notes: a part joined by a comma or 'and' is a second observation only when it names a defect `comma-or-and-part-counts-only-when-it-names-a-defect` — task — **Complete**
  - `M15.38` add-node caps a title-derived codename at 64 characters so the planning file name fits `derived-codename-capped-so-planning-names-fit` — task — **Complete**
  - `M15.39` A roadmap write that fails part-way restores every file it changed `failed-roadmap-write-restores-every-file` — task — **Complete**
  - `M15.40` finish-this-task: a failed merge landing reports after the land check output and undoes its bookkeeping commit `finish-merge-failure-reports-and-undoes-bookkeeping` — task — **Complete**
- `M16` lean core: harden and optimize code and docs, all delivered functionality kept `lean-core` — phase — **Not Started**
  - `M16.0` Parity harness: command inventory, golden --help transcripts, an end-to-end leaf loop and dogfood outputs `parity-harness-command-inventory-golden-help-transcripts-an-end-to-end-leaf-loop-and-dogfood-outputs` — task — **Not Started**
  - `M16.1` Parity harness: a review-gate decision table covering every review policy `parity-harness-a-review-gate-decision-table-covering-every-review-policy` — task — **Not Started**
  - `M16.2` Baseline metrics, a coverage floor in CI, and the M16 working rules written down `baseline-metrics-a-coverage-floor-in-ci-and-the-m16-working-rules-written-down` — task — **Not Started**
  - `M16.3` Delete dead and unwired code from a decided list, and add vulture as an advisory CI step `delete-dead-and-unwired-code-from-a-decided-list-and-add-vulture-as-an-advisory-ci-step` — task — **Not Started**
  - `M16.4` Shared clock and atomic-write helpers replace the nine now() copies and the hand-written atomic writers `shared-clock-and-atomic-write-helpers-replace-the-nine-now-copies-and-the-hand-written-atomic-writers` — task — **Not Started**
  - `M16.5` One roadmap index answers every graph query: by id, by key, effective dependencies, unmet, ready `one-roadmap-index-answers-every-graph-query-by-id-by-key-effective-dependencies-unmet-ready` — task — **Not Started**
  - `M16.6` The 29 package-imported library modules move out of bundled_scripts `the-29-package-imported-library-modules-move-out-of-bundled-scripts` — task — **Not Started**
  - `M16.7` Commands run in the CLI's process: no python -m re-launch, no cwd globals `commands-run-in-the-cli-s-process-no-python-m-re-launch-no-cwd-globals` — task — **Not Started**
  - `M16.8` Ruff quality rule families and the 100-character width with shrink-only baselines, and the consumer file-limit default decided `ruff-quality-baseline` — task — **Not Started**
  - `M16.9` Fold the cap-driven splits in pickup and finish into their parents `fold-the-cap-driven-splits-in-pickup-and-finish-into-their-parents` — task — **Not Started**
  - `M16.10` One LLM client module replaces the provider code inside review_node `one-llm-client-module-replaces-the-provider-code-inside-review-node` — task — **Not Started**
  - `M16.11` doctor --prune is the one cleanup path; branches prune, registry-prune and the grind cleanup become aliases `doctor-prune-is-the-one-cleanup-path-branches-prune-registry-prune-and-the-grind-cleanup-become-aliases` — task — **Not Started**
  - `M16.12` upgrade absorbs the refresh commands and prints one report of what changed for the repo; update becomes self-update `upgrade-absorbs-the-refresh-commands-and-prints-one-report-of-what-changed-for-the-repo-update-becomes-self-update` — task — **Not Started**
  - `M16.13` review status, review packet, decisions --kind lesson and presence replace handoff status, review list, review-packet, lessons and session `review-status-review-packet-decisions-kind-lesson-and-presence-replace-handoff-status-review-list-review-packet-lessons-and-session` — task — **Not Started**
  - `M16.14` One checks: block replaces baseline_cmd, land_check_cmd and verify_cmd with the same commands at the same points `one-checks-block-replaces-baseline-cmd-land-check-cmd-and-verify-cmd-with-the-same-commands-at-the-same-points` — task — **Not Started**
  - `M16.15` Orchestration subpackage with one public interface and one state model for the gate, the CLI and the PM GUI `orchestration-subpackage-with-one-public-interface-and-one-state-model-for-the-gate-the-cli-and-the-pm-gui` — task — **Not Started**
  - `M16.16` Worker runtime moves into orchestration/workers with import-path edits only `worker-runtime-moves-into-orchestration-workers-with-import-path-edits-only` — task — **Not Started**
  - `M16.17` Roster, model profiles, harness facts, orchestrate and role prompts move into orchestration `roster-model-profiles-harness-facts-orchestrate-and-role-prompts-move-into-orchestration` — task — **Not Started**
  - `M16.18` Shared-checkout guard and session presence move into orchestration `shared-checkout-guard-and-session-presence-move-into-orchestration` — task — **Not Started**
  - `M16.19` Grind session and its plan move into orchestration, read the index and the snapshot, and fold their cap siblings `grind-session-and-its-plan-move-into-orchestration-read-the-index-and-the-snapshot-and-fold-their-cap-siblings` — task — **Not Started**
  - `M16.20` Review-policy evidence: how often each optional review policy changed a gate outcome `review-policy-evidence-how-often-each-optional-review-policy-changed-a-gate-outcome` — task — **Not Started**
  - `M16.21` Fold the review gate and escalation fragments, and mark the policies the evidence did not keep as deprecated `fold-the-review-gate-and-escalation-fragments-and-mark-the-policies-the-evidence-did-not-keep-as-deprecated` — task — **Not Started**
  - `M16.22` Post-fix refactor gate: ready and the review packet report any complexity growth, and policy can block on it `post-fix-refactor-gate-ready-and-the-review-packet-report-any-complexity-growth-and-policy-can-block-on-it` — task — **Not Started**
  - `M16.23` Tests: tests/support primitives, and the four heaviest cross-imported test files switch to them `tests-tests-support-primitives-and-the-four-heaviest-cross-imported-test-files-switch-to-them` — task — **Not Started**
  - `M16.24` Tests: files move into unit, flows, cli, gui and repo lanes, moves only `tests-files-move-into-unit-flows-cli-gui-and-repo-lanes-moves-only` — task — **Not Started**
  - `M16.25` Tests: a committed dedupe worklist per subsystem names each removal and the assertion that covers it `tests-a-committed-dedupe-worklist-per-subsystem-names-each-removal-and-the-assertion-that-covers-it` — task — **Not Started**
  - `M16.26` Tests: public seams replace private-name patches, and no test sleeps on the wall clock `tests-public-seams-replace-private-name-patches-and-no-test-sleeps-on-the-wall-clock` — task — **Not Started**
  - `M16.27` Tests: public scenarios for milestone sessions, rollup and reconcile, written before the milestone and nested-repo fold `tests-public-scenarios-for-milestone-sessions-rollup-and-reconcile-written-before-the-milestone-and-nested-repo-fold` — task — **Not Started**
  - `M16.28` Tests: a CLI smoke lane of at most 50 subprocess items, everything else in process, suite time halved `tests-a-cli-smoke-lane-of-at-most-50-subprocess-items-everything-else-in-process-suite-time-halved` — task — **Not Started**
  - `M16.29` Constitution names orchestration as part of the product, bounds scope with a 'not' list, and drops contradictions `constitution-names-orchestration-as-part-of-the-product-bounds-scope-with-a-not-list-and-drops-contradictions` — task — **Not Started**
  - `M16.30` AGENTS.md is the one agent entry with a task-conditional load order; CLAUDE.md is a pointer `agents-md-is-the-one-agent-entry-with-a-task-conditional-load-order-claude-md-is-a-pointer` — task — **Not Started**
  - `M16.31` Docs by topic: design notes out of docs/, one workers doc, folded small docs, no pinned release candidate, one GUI extra `docs-by-topic-design-notes-out-of-docs-one-workers-doc-folded-small-docs-no-pinned-release-candidate-one-gui-extra` — task — **Not Started**
  - `M16.32` suggested_prompts follow the real formats: CLI authoring, complete deliverables, no restated rules, nested layout `suggested-prompts-follow-the-real-formats-cli-authoring-complete-deliverables-no-restated-rules-nested-layout` — task — **Not Started**
  - `M16.33` rc5 close: lean metrics measured against the baseline `rc5-close-lean-metrics-measured-against-the-baseline` — task — **Not Started**
  - `M16.34` Triage: the maintainer decides each held feature leaf not absorbed by an M16 leaf `triage-the-maintainer-decides-each-held-feature-leaf-not-absorbed-by-an-m16-leaf` — task — **Not Started**
  - `M16.53` Tests: public scenarios for outline moves, edit-field setters, archive, scaffold and update, written before the CRUD fold `tests-public-scenarios-for-outline-moves-edit-field-setters-archive-scaffold-and-update-written-before-the-crud-fold` — task — **Not Started**
  - `M16.35` Git queries and registry I/O go through one helper each `git-queries-and-registry-i-o-go-through-one-helper-each` — task — **Not Started**
  - `M16.36` A shrink-only layering gate records the import cycles and package-to-entry-point imports `a-shrink-only-layering-gate-records-the-import-cycles-and-package-to-entry-point-imports` — task — **Not Started**
  - `M16.37` Break the 45-module import cycle through the graph loader, the brief and validate `break-the-45-module-import-cycle-through-the-graph-loader-the-brief-and-validate` — task — **Not Started**
  - `M16.38` Break the 25-module import cycle between roadmap CRUD, worker ops and the chore CLI `break-the-25-module-import-cycle-between-roadmap-crud-worker-ops-and-the-chore-cli` — task — **Not Started**
  - `M16.39` Every command exposes build_parser(), imports lazily and shares the common argument helpers `every-command-exposes-build-parser-imports-lazily-and-shares-the-common-argument-helpers` — task — **Not Started**
  - `M16.40` One SpecyError base for the 15 error classes, printed and turned into an exit code once `one-specyerror-base-for-the-15-error-classes-printed-and-turned-into-an-exit-code-once` — task — **Not Started**
  - `M16.41` Nested-repo landing folds into nested_repos, breaking its cycle, and the two session-file readers become one `nested-repo-landing-folds-into-nested-repos-breaking-its-cycle-and-the-two-session-file-readers-become-one` — task — **Not Started**
  - `M16.43` The brainstorm CLI becomes two modules and the three managed-block writers share one engine `the-brainstorm-cli-becomes-two-modules-and-the-three-managed-block-writers-share-one-engine` — task — **Not Started**
  - `M16.44` Fold the remaining single-importer siblings from the code report's misc list `fold-the-remaining-single-importer-siblings-from-the-code-report-s-misc-list` — task — **Not Started**
  - `M16.42` Fold the PM UI server and roadmap CRUD splits, after the orchestration snapshot is fixed `fold-the-pm-ui-server-and-roadmap-crud-splits-after-the-orchestration-snapshot-is-fixed` — task — **Not Started**
  - `M16.45` milestone and planning command groups, and archive --hard-remove replaces archive-node `milestone-and-planning-command-groups-and-archive-hard-remove-replaces-archive-node` — task — **Not Started**
  - `M16.52` checks: entries scoped to touch zones block a merge when they fail (held M15.23's purpose) `checks-entries-scoped-to-touch-zones-block-a-merge-when-they-fail-held-m15-23-s-purpose` — task — **Not Started**
  - `M16.46` worker_ops parts and the worker siblings fold into their parents, and the module-class swap goes `worker-ops-parts-and-the-worker-siblings-fold-into-their-parents-and-the-module-class-swap-goes` — task — **Not Started**
  - `M16.47` One check_assignment decides eligibility for every launch and for the gate `one-check-assignment-decides-eligibility-for-every-launch-and-for-the-gate` — task — **Not Started**
  - `M16.48` The guard classifier becomes three rule tables with every verdict unchanged `the-guard-classifier-becomes-three-rule-tables-with-every-verdict-unchanged` — task — **Not Started**
  - `M16.49` Chore, decision and lesson records share internal adapters and keep their files byte for byte `chore-decision-and-lesson-records-share-internal-adapters-and-keep-their-files-byte-for-byte` — task — **Not Started**
  - `M16.50` Grind settings move under grind: in git-workflow.yaml, migrated by upgrade `grind-settings-move-under-grind-in-git-workflow-yaml-migrated-by-upgrade` — task — **Not Started**
  - `M16.51` The review packet fragments fold into review_packet `the-review-packet-fragments-fold-into-review-packet` — task — **Not Started**
  - `M16.54` Tests: every other cross-file import, copied helper and hand-written manifest moves to tests/support `tests-every-other-cross-file-import-copied-helper-and-hand-written-manifest-moves-to-tests-support` — task — **Not Started**
  - `M16.55` Tests: per-leaf and per-round test files fold into the file for the module or flow they test `tests-per-leaf-and-per-round-test-files-fold-into-the-file-for-the-module-or-flow-they-test` — task — **Not Started**
  - `M16.56` Tests: apply the dedupe worklist for review gate `tests-apply-the-dedupe-worklist-for-review-gate` — task — **Not Started**
  - `M16.57` Tests: apply the dedupe worklist for worker `tests-apply-the-dedupe-worklist-for-worker` — task — **Not Started**
  - `M16.58` Tests: apply the dedupe worklist for pickup and finish `tests-apply-the-dedupe-worklist-for-pickup-and-finish` — task — **Not Started**
  - `M16.59` Tests: apply the dedupe worklist for the rest `tests-apply-the-dedupe-worklist-for-the-rest` — task — **Not Started**
  - `M16.60` Tests: five named properties replace the single-input tests they cover `tests-five-named-properties-replace-the-single-input-tests-they-cover` — task — **Not Started**
  - `M16.61` Gate: the release that shipped the M16 aliases is out and the maintainer closes the alias window `gate-the-release-that-shipped-the-m16-aliases-is-out-and-the-maintainer-closes-the-alias-window` — gate — **Not Started**
  - `M16.62` After the alias window: delete the deprecated command aliases, config-form fallbacks and re-export shims `after-the-alias-window-delete-the-deprecated-command-aliases-config-form-fallbacks-and-re-export-shims` — task — **Not Started**
  - `M16.63` Roster entries split into core fields and a typed run: block, read in both forms `roster-core-and-run-block` — task — **Not Started**
  - `M16.64` upgrade migrates rosters to core fields plus run: `roster-upgrade-to-run-block` — task — **Not Started**
  - `M16.65` End-to-end pass on the toolkit and a feedback-and-fix round before 0.3.1 `e2e-pass-and-fix-round` — task — **Not Started**
  - `M16.66` Gate: ready to tag 0.3.1 `ready-to-tag-0-3-1` — gate — **Not Started**
  - `M16.67` move-node changes only the moved subtree's ids; whole-outline renumber becomes explicit `move-node-keeps-other-ids` — task — **Complete**
  - `M16.68` finish resolves roadmap chunk conflicts the branch only inherited `finish-resolves-inherited-roadmap-conflicts` — task — **Complete**
  - `M16.69` Cursor workers launch sandboxed without --force unless the roster opts in `cursor-workers-no-force-by-default` — task — **Complete**
  - `M16.70` Release docs for 0.3.1: README, docs, prompts and the CHANGELOG brought in line with what ships `release-docs-0-3-1` — task — **Not Started**
- `M21` rc4 stabilization: fixes filed after the themed-milestone rule `rc4-stabilization` — phase — **Not Started**
  - `M21.1` move-node takes a chosen free id or fills the lowest gap; PM GUI moves renumber only the moved subtree `move-node-chosen-id` — task — **Complete**
  - `M21.2` CLI indent, outdent and group-nodes re-level siblings in one transaction validated once `outline-group-cli` — task — **Not Started**
  - `M21.3` Opt-in rewrite of prose id references after a move, and a standalone rename-refs `rewrite-id-refs` — task — **Not Started**
  - `M21.4` remove-node deletes an empty never-started node and names every blocker otherwise `remove-node` — task — **Not Started**
  - `M21.5` apply CHANGES.yaml expresses moves, grouping and removals, rehearsed by --dry-run and validated once `apply-restructure-ops` — task — **Not Started**
  - `M21.6` validate and add-dependency catch cycles made through inherited group dependencies `inherited-dep-cycles` — task — **Complete**
  - `M21.7` Executors cannot change the files that steer harnesses and specy-road unnoticed `steering-file-guard` — task — **Not Started**
  - `M21.8` The queued-message worker test waits for the idle state, not just the second completion event `queue-message-test-waits-for-idle` — task — **Complete**
  - `M21.9` A freshly initialized project passes its own checks `init-passes-own-checks` — task — **Complete**
  - `M21.10` doctor works in a repo with no remote `doctor-without-a-remote` — task — **Complete**
  - `M21.11` Help text names installed commands `help-names-installed-commands` — task — **Complete**
  - `M21.12` A review record is refused for joined observations only when one of them names a defect `joined-observations-need-a-defect` — task — **Complete**
- `M17` 0.3.2: PM GUI shows orchestration and worktree state `pm-gui-orchestration-view` — phase — **Not Started**
  - `M17.1` 0.3.2 PM GUI orchestration and worktree view: plan from the snapshot interface `pm-gui-orchestration-plan` — gate — **Not Started**
- `M18` Orchestration and review-loop features (after 0.3.1) `orch-review-loop` — phase — **Not Started**
  - `M18.1` Reviewers check that code is well-formed and that fixes do not degrade it `review-code-quality` — task — **Not Started**
  - `M18.2` Harness-facts records for the Copilot CLI and Antigravity agy `harness-facts-copilot-agy` — task — **Not Started**
  - `M18.3` The shared-checkout guard sees file-tool edits and refuses ending a live peer's session `guard-file-tools` — task — **Not Started**
  - `M18.4` Unattended Codex and Cursor executors warn when reviews are unsigned `unsigned-review-warning` — task — **Not Started**
  - `M18.5` worker sync prints a paused_until line for a worker paused by a usage limit `sync-paused-until-hint` — task — **Not Started**
  - `M18.6` Per-model review evidence: block rate and overturned approvals feed orchestrate plan `per-model-review-evidence-block-rate-and-overturned-approvals-feed-orchestrate-plan` — task — **Not Started**
  - `M18.7` review-packet includes sibling repository diffs `review-packet-includes-sibling-repository-diffs` — task — **Not Started**
  - `M18.8` worker reconcile and the post-run check see sibling repositories `worker-reconcile-and-the-post-run-check-see-sibling-repositories` — task — **Not Started**
  - `M18.9` The implementation-zone check runs before a review is spent, and knows about sibling repositories `the-implementation-zone-check-runs-before-a-review-is-spent-and-knows-about-sibling-repositories` — task — **Not Started**
  - `M18.10` review rca launches the root-cause analyst like review delegate, and says what to do when no analyst is available `review-rca-launches-the-root-cause-analyst-like-review-delegate-and-says-what-to-do-when-no-analyst-is-available` — task — **Not Started**
  - `M18.11` Host effects policy: workers and reviewers do not take over the screen or change shared services, the guard denies such commands, and a message can interrupt a turn `host-effects-policy-and-interruptible-worker-messages` — task — **Not Started**
  - `M18.12` Role-observed acceptance needs evidence from that role, and coordinator probes are not acceptance `role-observed-acceptance-needs-that-role` — task — **Not Started**
  - `M18.13` Touch zones that miss what acceptance needs are flagged at plan time, and the brief's zone section stays short `zones-missing-what-acceptance-needs-flagged` — task — **Not Started**
  - `M18.14` A change to the shared stash is attributed to the worker whose branch made it, not to whichever worker's turn ended while the entry existed `stash-changes-attributed-to-the-owning-branch` — task — **Not Started**
  - `M18.15` --rework carries blocks at the branch tip as required changes, lists older blocks as possibly resolved, and takes a coordinator note placed above the reviews `rework-carries-current-blocks-and-a-coordinator-note` — task — **Not Started**
  - `M18.16` A review that stops before filing leaves a trace: every reviewer channel opens a RUN record, and review list shows started but not filed `every-reviewer-channel-leaves-a-run-record` — task — **Not Started**
  - `M18.17` Under delta review, one approval per round still checks the whole leaf against the merge base on a fixed checklist `one-full-leaf-checklist-review-per-round` — task — **Not Started**
  - `M18.18` Plan review after planning, and a staleness check before pickup `plan-review-and-pickup-staleness` — task — **Not Started**
  - `M18.19` orchestrate plan and review delegate apply reviewer preferences from the decisions ledger and say when they do `plan-applies-preferences` — task — **Not Started**
  - `M18.20` Unattended grind loop: several workers at once, zone-overlap scheduling, per-model caps, review hand-off and landing when the gate is met `unattended-grind-loop` — task — **Not Started**
  - `M18.21` Automatic fix rounds in the unattended loop, capped by the fix-round budget, then parked for a human `auto-fix-rounds` — task — **Not Started**
  - `M18.22` doctor reports a stalled orchestration: a silent loop, failed or stalled workers, idle leaves, a stuck review queue, undelegated ready leaves and a dirty checkout `orchestration-supervision` — task — **Not Started**
  - `M18.23` Executor account pools: weighted accounts per roster entry, session-account affinity, and failover on a usage limit `executor-account-pools` — task — **Not Started**
  - `M18.24` review run: the required reviewers in order for one leaf, a concurrency cap across leaves, and one retry on a refused record `review-run-queue` — task — **Not Started**
  - `M18.25` A channels.cli reviewer writes its final answer to a file specy-road names, and its transcript is kept beside the run record `reviewer-answer-file` — task — **Not Started**
  - `M18.26` Amending a claimed leaf's touch zones or one acceptance line records the reason, commits on the leaf branch and re-arms its review `claimed-leaf-amendments` — task — **Not Started**
  - `M18.27` Append-only zone paths such as CHANGELOG.md do not serialize leaves, and finish merges their added lines `append-only-zone-paths` — task — **Not Started**
- `M19` Adopter-project features: upgrade, agent-file layering, planning hygiene, project tooling (after 0.3.1) `adopter-features` — phase — **Not Started**
  - `M19.1` Configurable code-analysis tools `analysis-tools` — task — **Not Started**
  - `M19.2` Research reminders leave validate `research-due-in-doctor` — task — **Not Started**
  - `M19.3` The pickup prompt names its base commit `pickup-prompt-base` — task — **Not Started**
  - `M19.4` The managed block stops naming pickup's --local opt-out `no-local-in-block` — task — **Not Started**
  - `M19.5` A tracked tech-debt ledger that planning can turn into leaves `a-tracked-tech-debt-ledger-that-planning-can-turn-into-leaves` — task — **Not Started**
  - `M19.6` The orchestrator cleans up landed leaves and stale worktrees automatically, saving hand-off files first `the-orchestrator-cleans-up-landed-leaves-and-stale-worktrees-automatically-saving-hand-off-files-first` — task — **Not Started**
  - `M19.7` Notices for how the agent files fit together: missing CLAUDE.md import, two load orders, floor read twice `notices-for-how-the-agent-files-fit-together-missing-claude-md-import-two-load-orders-floor-read-twice` — task — **Not Started**
  - `M19.8` upgrade says what changed for this repo: behaviour changes, a pin below the new minimum, the new files and duplicated paragraphs `upgrade-says-what-changed-for-this-repo-behaviour-changes-a-pin-below-the-new-minimum-the-new-files-and-duplicated-paragraphs` — task — **Not Started**
  - `M19.9` upgrade --prompt writes an agent upgrade prompt filled in from this repo `upgrade-prompt-writes-an-agent-upgrade-prompt-filled-in-from-this-repo` — task — **Not Started**
  - `M19.10` file-limits can write a baseline of today's exceptions, a failing run points at it, and upgrade reports the file-limits count `file-limits-baseline-and-upgrade-report` — task — **Not Started**
  - `M19.11` Chores at parity with leaves: worktree, branch and env_setup on start, widen zones, the review-record path, and work/chores ignored `chores-at-parity-with-leaves` — task — **Not Started**
  - `M19.12` List shipped nodes with no result after N days `list-shipped-nodes-with-no-result-after-n-days` — milestone — **Not Started**
  - `M19.13` Store a pointer and a human verdict for outcomes, never the metric itself `store-a-pointer-and-a-human-verdict-for-outcomes-never-the-metric-itself` — milestone — **Not Started**
  - `M19.14` Human decisions get recorded and shown: agent rule, digest, review status and decisions add --help `decisions-discoverable` — task — **Not Started**
  - `M19.15` Decision ids take a project prefix (default DEC-) and warn when a new id already appears in governance files `decision-id-prefix` — task — **Not Started**
  - `M19.16` validate notices sheet acceptance that drifted from the node, and gate dependencies the gate never names `sheet-acceptance-drift` — task — **Not Started**
  - `M19.17` validate notices governance files that require a field validate strips, and names the replacement `governance-deprecated-fields` — task — **Not Started**
  - `M19.18` A ratified scope boundary in the decisions ledger, with validate and digest notices for phases beyond it `scope-boundary` — task — **Not Started**
- `M20` Agent safety and governance posture (after 0.3.1) `agent-safety-posture` — phase — **Not Started**
  - `M20.1` Posture advisor: plan the M20 leaves from the research `plan-m20-from-research` — task — **Not Started**
  - `M20.2` Probe each reviewer harness for instruction-file leakage into fresh sessions `fresh-reviewer-leak-probe` — task — **Not Started**

## Open gates

Work behind these is deliberately held back until they clear.

- `M16.61 Gate: the release that shipped the M16 aliases is out and the maintainer closes the alias window` — **Not Started**
- `M16.66 Gate: ready to tag 0.3.1` — **Not Started**
- `M17.1 0.3.2 PM GUI orchestration and worktree view: plan from the snapshot interface` — **Not Started**

## Dependencies that were removed

Someone deliberately dropped these. Check why before re-adding one.

- 2026-11-05 `M16.60` stopped depending on `M16.31 Docs by topic: design notes out of docs/, one workers doc, folded small docs, no pinned release candidate, one GUI extra`
- 2026-11-05 `M15.30` stopped depending on `2535829e-6a0d-40e3-aa42-9b0506bb9fe9` (no longer live)
- 2026-11-05 `M16.18` stopped depending on `M16.47 One check_assignment decides eligibility for every launch and for the gate`
- 2026-11-05 `M16.12` stopped depending on `M16.7 Commands run in the CLI's process: no python -m re-launch, no cwd globals`
- 2026-11-05 `M16.12` stopped depending on `M16.10 One LLM client module replaces the provider code inside review_node`
- 2026-11-05 `M16.15` stopped depending on `M16.1 Parity harness: a review-gate decision table covering every review policy`
- 2026-11-05 `M16.15` stopped depending on `M16.6 The 29 package-imported library modules move out of bundled_scripts`
- 2026-11-05 `M16.15` stopped depending on `M16.5 One roadmap index answers every graph query: by id, by key, effective dependencies, unmet, ready`
- 2026-11-05 `M16.33` stopped depending on `M16.12 upgrade absorbs the refresh commands and prints one report of what changed for the repo; update becomes self-update`
- 2026-11-05 `M16.33` stopped depending on `M16.13 review status, review packet, decisions --kind lesson and presence replace handoff status, review list, review-packet, lessons and session`
- 2026-11-05 `M16.33` stopped depending on `M16.11 doctor --prune is the one cleanup path; branches prune, registry-prune and the grind cleanup become aliases`
- 2026-11-05 `M16.33` stopped depending on `M16.18 Shared-checkout guard and session presence move into orchestration`
- 2026-11-05 `M16.33` stopped depending on `M16.22 Post-fix refactor gate: ready and the review packet report any complexity growth, and policy can block on it`
- 2026-11-05 `M16.33` stopped depending on `M16.14 One checks: block replaces baseline_cmd, land_check_cmd and verify_cmd with the same commands at the same points`
- 2026-11-05 `M16.33` stopped depending on `M16.17 Roster, model profiles, harness facts, orchestrate and role prompts move into orchestration`
- 2026-11-05 `M16.33` stopped depending on `M16.21 Fold the review gate and escalation fragments, and mark the policies the evidence did not keep as deprecated`
- 2026-11-05 `M16.33` stopped depending on `M16.16 Worker runtime moves into orchestration/workers with import-path edits only`
- 2026-11-05 `M16.33` stopped depending on `M16.19 Grind session and its plan move into orchestration, read the index and the snapshot, and fold their cap siblings`
- 2026-11-05 `M16.9` stopped depending on `M16.6 The 29 package-imported library modules move out of bundled_scripts`
- 2026-11-05 `M16.13` stopped depending on `M16.11 doctor --prune is the one cleanup path; branches prune, registry-prune and the grind cleanup become aliases`
- 2026-11-05 `M16.3` stopped depending on `M16.0 Parity harness: command inventory, golden --help transcripts, an end-to-end leaf loop and dogfood outputs`
- 2026-11-05 `M16.11` stopped depending on `M16.7 Commands run in the CLI's process: no python -m re-launch, no cwd globals`
- 2026-11-05 `M16.18` stopped depending on `M16.15 Orchestration subpackage with one public interface and one state model for the gate, the CLI and the PM GUI`
- 2026-11-05 `M16.32` stopped depending on `M16.13 review status, review packet, decisions --kind lesson and presence replace handoff status, review list, review-packet, lessons and session`
- 2026-11-05 `M16.32` stopped depending on `M16.30 AGENTS.md is the one agent entry with a task-conditional load order; CLAUDE.md is a pointer`
- _…and 35 earlier — `specy-road history --json`_

## Archived (not in the live roadmap)

This work was completed and moved out of the graph. It is deliberately excluded from IDE indexing; reach it with `specy-road search <QUERY> --scope archived`.

- 2026-11-02 `M11.21` (1 node) — `specy-road show-archive M11.21-439c8b26-20261102`
- 2026-11-05 `M1` (2 nodes) — `specy-road show-archive M1-a1b2c3d4-20261105`
- 2026-11-05 `M3` (19 nodes) — `specy-road show-archive M3-c78073ae-20261105`
- 2026-11-05 `M4` (19 nodes) — `specy-road show-archive M4-4e85b231-20261105`
- 2026-11-05 `M5` (9 nodes) — `specy-road show-archive M5-0e8ca94e-20261105`
- 2026-11-05 `M6` (3 nodes) — `specy-road show-archive M6-856ec58c-20261105`
- 2026-11-05 `M7` (3 nodes) — `specy-road show-archive M7-abf3ac61-20261105`
- 2026-11-05 `M8` (8 nodes) — `specy-road show-archive M8-dc1820b2-20261105`
- 2026-11-05 `M9` (12 nodes) — `specy-road show-archive M9-5f87b038-20261105`
- 2026-11-05 `M10` (21 nodes) — `specy-road show-archive M10-deb4dfb7-20261105`
- 2026-11-05 `M11` (81 nodes) — `specy-road show-archive M11-e10fe30c-20261105`
- 2026-11-05 `M12` (6 nodes) — `specy-road show-archive M12-eecba3f4-20261105`
- 2026-11-05 `M13` (11 nodes) — `specy-road show-archive M13-2fe2e067-20261105`
- 2026-11-05 `M14` (10 nodes) — `specy-road show-archive M14-20b59415-20261105`

## Claimed and in flight

Do not pick these up.

- `M18.13` on `feature/rm-zones-missing-what-acceptance-needs-flagged` since 2026-11-04
- `M18.14` on `feature/rm-stash-changes-attributed-to-the-owning-branch` since 2026-11-05
- `M19.10` on `feature/rm-file-limits-baseline-and-upgrade-report` since 2026-11-05
- `M19.6` on `feature/rm-the-orchestrator-cleans-up-landed-leaves-and-stale-worktrees-automatically-saving-hand-off-files-first` since 2026-11-05
- `M19.7` on `feature/rm-notices-for-how-the-agent-files-fit-together-missing-claude-md-import-two-load-orders-floor-read-twice` since 2026-11-05
- `M21.2` on `feature/rm-outline-group-cli` since 2026-11-05
- `M21.4` on `feature/rm-remove-node` since 2026-11-05
- `M21.7` on `feature/rm-steering-file-guard` since 2026-11-05

## Quality by area

Review cost of the last 50 completed leaves, per touch-zone area, from the `Review-tally` trailers on their gate commits. Block rate is the share of tallied leaves with at least one blocking round; areas above 50% are **flagged** and listed first. Plan tighter acceptance there.

| Area | Leaves | No tally | Mean rounds | Block rate | Integrity findings | RCA escalations |
| --- | --- | --- | --- | --- | --- | --- |
| `docs` **flagged** | 26 | 9 | 4.88 | 76% | 25 | 3 |
| `roadmap` **flagged** | 1 | 0 | 3.00 | 100% | 1 | 0 |
| `specy_road` **flagged** | 49 | 17 | 4.28 | 72% | 34 | 6 |
| `tests` **flagged** | 50 | 17 | 4.24 | 73% | 34 | 6 |
| `CHANGELOG.md` | 6 | 0 | 2.50 | 33% | 6 | 0 |
| `planning` | 2 | 0 | 2.00 | 50% | 0 | 0 |
| `roadmap-context.md` | 1 | 1 | — | — | 0 | 0 |

Leaves with no tally landed before tallies were recorded; they are left out of the rates.

## Reaching the detail behind this

This digest is a summary. The full text of planning sheets, shared contracts and archived work is searchable:

```bash
specy-road search "<query>"                 # live + archived, ranked
specy-road search "<query>" --scope archived  # completed work only
specy-road search <NODE_ID>                  # everything about one node
specy-road history <NODE_ID>                 # how it got to this state
```
