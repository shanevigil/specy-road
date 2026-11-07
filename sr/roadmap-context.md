# Roadmap context

<!-- specy-road: generated context digest — do not edit by hand. Regenerate with `specy-road digest`. -->

The current state of this project's roadmap, generated from the merged graph, the archive ledger and git history. Read this before crawling `planning/` or `work/` — it is the authoritative summary, and those directories contain a great deal of duplicated text.

## Live roadmap

Status is the computed rollup: a non-leaf is Complete only when every leaf descendant is.

- `M16` lean core: harden and optimize code and docs, all delivered functionality kept `lean-core` — phase — **Not Started**
  - `M16.1` Freeze, rules, parity harness and baselines `freeze-rules-parity-harness-and-baselines` — milestone — **Not Started**
    - `M16.1.1` Parity harness: command inventory, golden --help transcripts, an end-to-end leaf loop and dogfood outputs `parity-harness-command-inventory-golden-help-transcripts-an-end-to-end-leaf-loop-and-dogfood-outputs` — task — **Not Started**
    - `M16.1.2` Parity harness: a review-gate decision table covering every review policy `parity-harness-a-review-gate-decision-table-covering-every-review-policy` — task — **Not Started**
    - `M16.1.3` Triage: the maintainer decides each held feature leaf not absorbed by an M16 leaf `triage-the-maintainer-decides-each-held-feature-leaf-not-absorbed-by-an-m16-leaf` — task — **Not Started**
    - `M16.1.4` Constitution names orchestration as part of the product, bounds scope with a 'not' list, and drops contradictions `constitution-names-orchestration-as-part-of-the-product-bounds-scope-with-a-not-list-and-drops-contradictions` — task — **Not Started**
    - `M16.1.5` AGENTS.md is the one agent entry with a task-conditional load order; CLAUDE.md is a pointer `agents-md-is-the-one-agent-entry-with-a-task-conditional-load-order-claude-md-is-a-pointer` — task — **Not Started**
    - `M16.1.6` Review-policy evidence: how often each optional review policy changed a gate outcome `review-policy-evidence-how-often-each-optional-review-policy-changed-a-gate-outcome` — task — **Not Started**
    - `M16.1.7` Baseline metrics, a coverage floor in CI, and the M16 working rules written down `baseline-metrics-a-coverage-floor-in-ci-and-the-m16-working-rules-written-down` — task — **Not Started**
    - `M16.1.8` A 100-character line-width rule with a shrink-only baseline, and the consumer file-limit default decided `ruff-quality-baseline` — task — **Not Started**
    - `M16.1.9` Tests: public scenarios for milestone sessions, rollup and reconcile, written before the milestone and nested-repo fold `tests-public-scenarios-for-milestone-sessions-rollup-and-reconcile-written-before-the-milestone-and-nested-repo-fold` — task — **Not Started**
    - `M16.1.10` Tests: public scenarios for outline moves, edit-field setters, archive, scaffold and update, written before the CRUD fold `tests-public-scenarios-for-outline-moves-edit-field-setters-archive-scaffold-and-update-written-before-the-crud-fold` — task — **Not Started**
    - `M16.1.11` Ruff quality rule families with per-file shrink-only baselines and per-release totals `ruff-quality-family-baseline` — task — **Not Started**
  - `M16.2` Mechanical clean-up, layering and the in-process CLI `mechanical-clean-up-layering-and-the-in-process-cli` — milestone — **Not Started**
    - `M16.2.1` Delete dead and unwired code from a decided list, and add vulture as an advisory CI step `delete-dead-and-unwired-code-from-a-decided-list-and-add-vulture-as-an-advisory-ci-step` — task — **Not Started**
    - `M16.2.2` Shared clock and atomic-write helpers replace the nine now() copies and the hand-written atomic writers `shared-clock-and-atomic-write-helpers-replace-the-nine-now-copies-and-the-hand-written-atomic-writers` — task — **Not Started**
    - `M16.2.3` Git queries and registry I/O go through one helper each `git-queries-and-registry-i-o-go-through-one-helper-each` — task — **Not Started**
    - `M16.2.4` One roadmap index answers every graph query: by id, by key, effective dependencies, unmet, ready `one-roadmap-index-answers-every-graph-query-by-id-by-key-effective-dependencies-unmet-ready` — task — **Not Started**
    - `M16.2.5` Library modules imported by the package move out of bundled_scripts `library-modules-imported-by-the-package-move-out-of-bundled` — task — **Not Started**
    - `M16.2.6` A shrink-only layering gate records the import cycles and package-to-entry-point imports `a-shrink-only-layering-gate-records-the-import-cycles-and-package-to-entry-point-imports` — task — **Not Started**
    - `M16.2.7` Break the 45-module import cycle through the graph loader, the brief and validate `break-the-45-module-import-cycle-through-the-graph-loader-the-brief-and-validate` — task — **Not Started**
    - `M16.2.8` Break the 25-module import cycle between roadmap CRUD, worker ops and the chore CLI `break-the-25-module-import-cycle-between-roadmap-crud-worker-ops-and-the-chore-cli` — task — **Not Started**
    - `M16.2.9` Commands run in the CLI's process: no python -m re-launch, no cwd globals `commands-run-in-the-cli-s-process-no-python-m-re-launch-no-cwd-globals` — task — **Not Started**
    - `M16.2.10` Every command exposes build_parser(), imports lazily and shares the common argument helpers `every-command-exposes-build-parser-imports-lazily-and-shares-the-common-argument-helpers` — task — **Not Started**
    - `M16.2.11` One SpecyError base for the 15 error classes, printed and turned into an exit code once `one-specyerror-base-for-the-15-error-classes-printed-and-turned-into-an-exit-code-once` — task — **Not Started**
  - `M16.3` Orchestration state model and the cap-driven folds `orchestration-state-model-and-the-cap-driven-folds` — milestone — **Not Started**
    - `M16.3.1` Orchestration subpackage with one public interface and one state model for the gate, the CLI and the PM GUI `orchestration-subpackage-with-one-public-interface-and-one-state-model-for-the-gate-the-cli-and-the-pm-gui` — task — **Not Started**
    - `M16.3.2` Fold the cap-driven splits in pickup and finish into their parents `fold-the-cap-driven-splits-in-pickup-and-finish-into-their-parents` — task — **Not Started**
    - `M16.3.3` Nested-repo landing folds into nested_repos, breaking its cycle, and the two session-file readers become one `nested-repo-landing-folds-into-nested-repos-breaking-its-cycle-and-the-two-session-file-readers-become-one` — task — **Not Started**
    - `M16.3.4` One LLM client module replaces the provider code inside review_node `one-llm-client-module-replaces-the-provider-code-inside-review-node` — task — **Not Started**
    - `M16.3.5` The brainstorm CLI becomes two modules and the three managed-block writers share one engine `the-brainstorm-cli-becomes-two-modules-and-the-three-managed-block-writers-share-one-engine` — task — **Not Started**
    - `M16.3.6` Fold the remaining single-importer siblings from the code report's misc list `fold-the-remaining-single-importer-siblings-from-the-code-report-s-misc-list` — task — **Not Started**
    - `M16.3.7` Fold the PM UI server and roadmap CRUD splits, after the orchestration snapshot is fixed `fold-the-pm-ui-server-and-roadmap-crud-splits-after-the-orchestration-snapshot-is-fixed` — task — **Not Started**
  - `M16.4` One command surface and one checks: config (aliases kept for rc5) `one-command-surface-and-one-checks-config-aliases-kept-for-rc5` — milestone — **Not Started**
    - `M16.4.1` doctor --prune is the one cleanup path; branches prune, registry-prune and the grind cleanup become aliases `doctor-prune-is-the-one-cleanup-path-branches-prune-registry-prune-and-the-grind-cleanup-become-aliases` — task — **Not Started**
    - `M16.4.2` upgrade absorbs the refresh commands and prints one report of what changed for the repo; update becomes self-update `upgrade-absorbs-the-refresh-commands-and-prints-one-report-of-what-changed-for-the-repo-update-becomes-self-update` — task — **Not Started**
    - `M16.4.3` review status, review packet, decisions --kind lesson and presence replace handoff status, review list, review-packet, lessons and session `review-status-review-packet-decisions-kind-lesson-and-presence-replace-handoff-status-review-list-review-packet-lessons-and-session` — task — **Not Started**
    - `M16.4.4` milestone and planning command groups, and archive --hard-remove replaces archive-node `milestone-and-planning-command-groups-and-archive-hard-remove-replaces-archive-node` — task — **Not Started**
    - `M16.4.5` One checks: block replaces baseline_cmd, land_check_cmd and verify_cmd with the same commands at the same points `one-checks-block-replaces-baseline-cmd-land-check-cmd-and-verify-cmd-with-the-same-commands-at-the-same-points` — task — **Not Started**
    - `M16.4.6` checks: entries scoped to touch zones block a merge when they fail (held M15.23's purpose) `checks-entries-scoped-to-touch-zones-block-a-merge-when-they-fail-held-m15-23-s-purpose` — task — **Not Started**
  - `M16.5` Orchestration subpackage, roster split and review-gate folds `orchestration-subpackage-roster-split-and-review-gate-folds` — milestone — **Not Started**
    - `M16.5.1` Worker runtime moves into orchestration/workers with import-path edits only `worker-runtime-moves-into-orchestration-workers-with-import-path-edits-only` — task — **Not Started**
    - `M16.5.2` worker_ops parts and the worker siblings fold into their parents, and the module-class swap goes `worker-ops-parts-and-the-worker-siblings-fold-into-their-parents-and-the-module-class-swap-goes` — task — **Not Started**
    - `M16.5.3` Roster, model profiles, harness facts, orchestrate and role prompts move into orchestration `roster-model-profiles-harness-facts-orchestrate-and-role-prompts-move-into-orchestration` — task — **Not Started**
    - `M16.5.4` One check_assignment decides eligibility for every launch and for the gate `one-check-assignment-decides-eligibility-for-every-launch-and-for-the-gate` — task — **Not Started**
    - `M16.5.5` Roster entries split into core fields and a typed run: block, read in both forms `roster-core-and-run-block` — task — **Not Started**
    - `M16.5.6` upgrade migrates rosters to core fields plus run: `roster-upgrade-to-run-block` — task — **Not Started**
    - `M16.5.7` Shared-checkout guard and session presence move into orchestration `shared-checkout-guard-and-session-presence-move-into-orchestration` — task — **Not Started**
    - `M16.5.8` The guard classifier becomes three rule tables with every verdict unchanged `the-guard-classifier-becomes-three-rule-tables-with-every-verdict-unchanged` — task — **Not Started**
    - `M16.5.9` Grind session and its plan move into orchestration, read the index and the snapshot, and fold their cap siblings `grind-session-and-its-plan-move-into-orchestration-read-the-index-and-the-snapshot-and-fold-their-cap-siblings` — task — **Not Started**
    - `M16.5.10` Chore, decision and lesson records share internal adapters and keep their files byte for byte `chore-decision-and-lesson-records-share-internal-adapters-and-keep-their-files-byte-for-byte` — task — **Not Started**
    - `M16.5.11` Grind settings move under grind: in git-workflow.yaml, migrated by upgrade `grind-settings-move-under-grind-in-git-workflow-yaml-migrated-by-upgrade` — task — **Not Started**
    - `M16.5.12` Fold the review gate and escalation fragments, and mark the policies the evidence did not keep as deprecated `fold-the-review-gate-and-escalation-fragments-and-mark-the-policies-the-evidence-did-not-keep-as-deprecated` — task — **Not Started**
    - `M16.5.13` The review packet fragments fold into review_packet `the-review-packet-fragments-fold-into-review-packet` — task — **Not Started**
    - `M16.5.14` Post-fix refactor gate: ready and the review packet report any complexity growth, and policy can block on it `post-fix-refactor-gate-ready-and-the-review-packet-report-any-complexity-growth-and-policy-can-block-on-it` — task — **Not Started**
  - `M16.6` Docs and tests reorganised by topic `docs-and-tests-reorganised-by-topic` — milestone — **Not Started**
    - `M16.6.1` Docs by topic: design notes out of docs/, one workers doc, folded small docs, no pinned release candidate, one GUI extra `docs-by-topic-design-notes-out-of-docs-one-workers-doc-folded-small-docs-no-pinned-release-candidate-one-gui-extra` — task — **Not Started**
    - `M16.6.2` suggested_prompts follow the real formats: CLI authoring, complete deliverables, no restated rules, nested layout `suggested-prompts-follow-the-real-formats-cli-authoring-complete-deliverables-no-restated-rules-nested-layout` — task — **Not Started**
    - `M16.6.3` Tests: tests/support primitives, and the four heaviest cross-imported test files switch to them `tests-tests-support-primitives-and-the-four-heaviest-cross-imported-test-files-switch-to-them` — task — **Not Started**
    - `M16.6.4` Tests: every other cross-file import, copied helper and hand-written manifest moves to tests/support `tests-every-other-cross-file-import-copied-helper-and-hand-written-manifest-moves-to-tests-support` — task — **Not Started**
    - `M16.6.5` Tests: files move into unit, flows, cli, gui and repo lanes, moves only `tests-files-move-into-unit-flows-cli-gui-and-repo-lanes-moves-only` — task — **Not Started**
    - `M16.6.6` Tests: per-leaf and per-round test files fold into the file for the module or flow they test `tests-per-leaf-and-per-round-test-files-fold-into-the-file-for-the-module-or-flow-they-test` — task — **Not Started**
  - `M16.7` Test dedupe, public seams, properties and the smoke lane `test-dedupe-public-seams-properties-and-the-smoke-lane` — milestone — **Not Started**
    - `M16.7.1` Tests: a committed dedupe worklist per subsystem names each removal and the assertion that covers it `tests-a-committed-dedupe-worklist-per-subsystem-names-each-removal-and-the-assertion-that-covers-it` — task — **Not Started**
    - `M16.7.2` Tests: apply the dedupe worklist for review gate `tests-apply-the-dedupe-worklist-for-review-gate` — task — **Not Started**
    - `M16.7.3` Tests: apply the dedupe worklist for worker `tests-apply-the-dedupe-worklist-for-worker` — task — **Not Started**
    - `M16.7.4` Tests: apply the dedupe worklist for pickup and finish `tests-apply-the-dedupe-worklist-for-pickup-and-finish` — task — **Not Started**
    - `M16.7.5` Tests: apply the dedupe worklist for the rest `tests-apply-the-dedupe-worklist-for-the-rest` — task — **Not Started**
    - `M16.7.6` Tests: public seams replace private-name patches, and no test sleeps on the wall clock `tests-public-seams-replace-private-name-patches-and-no-test-sleeps-on-the-wall-clock` — task — **Not Started**
    - `M16.7.7` Tests: five named properties replace the single-input tests they cover `tests-five-named-properties-replace-the-single-input-tests-they-cover` — task — **Not Started**
    - `M16.7.8` Tests: a CLI smoke lane and in-process CLI tests, held to the effectiveness measures the maintainer chooses `tests-a-cli-smoke-lane-and-in-process-cli-tests-held-to-the` — task — **Not Started**
  - `M16.8` rc5 close, alias window, end-to-end pass and the 0.3.1 tag `rc5-close-alias-window-end-to-end-pass-and-the-0-3-1-tag` — milestone — **Not Started**
    - `M16.8.1` rc5 close: lean metrics measured against the baseline `rc5-close-lean-metrics-measured-against-the-baseline` — task — **Not Started**
    - `M16.8.2` Gate: the release that shipped the M16 aliases is out and the maintainer closes the alias window `gate-the-release-that-shipped-the-m16-aliases-is-out-and-the-maintainer-closes-the-alias-window` — gate — **Not Started**
    - `M16.8.3` After the alias window: delete the deprecated command aliases, config-form fallbacks and re-export shims `after-the-alias-window-delete-the-deprecated-command-aliases-config-form-fallbacks-and-re-export-shims` — task — **Not Started**
    - `M16.8.4` End-to-end pass on the toolkit and a feedback-and-fix round before 0.3.1 `e2e-pass-and-fix-round` — task — **Not Started**
    - `M16.8.8` Release docs for 0.3.1: README, docs, prompts and the CHANGELOG brought in line with what ships `release-docs-0-3-1` — task — **Not Started**
    - `M16.8.9` Gate: ready to tag 0.3.1 `ready-to-tag-0-3-1` — gate — **Not Started**
    - `M16.8.10` Gate: 0.3.1 tagged `v0-3-1-tagged` — gate — **Not Started**
- `M21` rc4 stabilization: fixes filed after the themed-milestone rule `rc4-stabilization` — phase — **Not Started**
  - `M21.1` move-node takes a chosen free id or fills the lowest gap; PM GUI moves renumber only the moved subtree `move-node-chosen-id` — task — **Complete**
  - `M21.2` CLI indent, outdent and group-nodes re-level siblings in one transaction validated once `outline-group-cli` — task — **Complete**
  - `M21.3` Opt-in rewrite of prose id references after a move, and a standalone rename-refs `rewrite-id-refs` — task — **Complete**
  - `M21.4` remove-node deletes an empty never-started node and names every blocker otherwise `remove-node` — task — **Complete**
  - `M21.5` apply CHANGES.yaml expresses moves, grouping and removals, rehearsed by --dry-run and validated once `apply-restructure-ops` — task — **Complete**
  - `M21.6` validate and add-dependency catch cycles made through inherited group dependencies `inherited-dep-cycles` — task — **Complete**
  - `M21.8` The queued-message worker test waits for the idle state, not just the second completion event `queue-message-test-waits-for-idle` — task — **Complete**
  - `M21.9` A freshly initialized project passes its own checks `init-passes-own-checks` — task — **Complete**
  - `M21.10` doctor works in a repo with no remote `doctor-without-a-remote` — task — **Complete**
  - `M21.11` Help text names installed commands `help-names-installed-commands` — task — **Complete**
  - `M21.12` A review record is refused for joined observations only when one of them names a defect `joined-observations-need-a-defect` — task — **Complete**
  - `M21.13` move-node changes only the moved subtree's ids; whole-outline renumber becomes explicit `move-node-keeps-other-ids` — task — **Complete**
  - `M21.14` finish resolves roadmap chunk conflicts the branch only inherited `finish-resolves-inherited-roadmap-conflicts` — task — **Complete**
  - `M21.15` Cursor workers launch sandboxed without --force unless the roster opts in `cursor-workers-no-force-by-default` — task — **Complete**
  - `M21.16` upgrade --dry-run never touches the real repo under GIT_DIR, and a real upgrade regenerates drifted generated files `upgrade-scratch-git-and-regen` — task — **Complete**
  - `M21.17` Writers refuse a symlinked target that leads out of the directory they own: init's generated files, review refusal and packet `writers-refuse-links-out` — task — **Complete**
  - `M21.18` A review deferral counts only when its marker is bound to the decision review defer recorded for it and its RCA `deferral-bound-to-its-decision` — task — **Complete**
  - `M21.19` apply --dry-run rehearses on a scratch copy whose links are rebased, so no rehearsal can move or change a live file `apply-dry-run-rebases-links` — task — **Complete**
  - `M21.20` PM GUI Publish regenerates roadmap.md and roadmap-context.md before committing, and refuses before committing when no remote is set `gui-publish-regenerates-and-needs-a-remote` — task — **Complete**
  - `M21.21` review delegate validates the reviewer command as prompt --channel cli does, and the model check splits on newlines only `review-delegate-validates-reviewer-command` — task — **Complete**
  - `M21.22` Small rc4 code fixes: adapter docstring, dead outline writers, pickup hint ignored, land: local wording, unused upgrade helper `rc4-small-code-fixes` — task — **Complete**
  - `M21.23` rc4 doc corrections on WIP: refresh-profiles default, no private roster ids, exact managed-block markers, reviewer mode, file-cap CHANGELOG entry `rc4-docs-corrections` — task — **Complete**
  - `M21.24` review delegate runs a Claude Code reviewer: the inline --json-schema carries no $schema, and a failed run names the harness's error `claude-reviewer-schema-and-error` — task — **Complete**
  - `M21.25` review delegate reads a reviewer's answer when narration precedes its final JSON object `reviewer-answer-after-prose` — task — **Complete**
  - `M21.26` The review gate never counts a record from a model that wrote a READY on the leaf, and review delegate refuses that model `gate-excludes-ready-authors` — task — **Complete**
  - `M21.27` review record and the human approval take the leaf's review lock, so another filing never voids a running reviewer `filings-take-the-review-lock` — task — **Complete**
  - `M21.28` finish-this-task refuses an invalid configuration before any bookkeeping write and never leaves a half-mutated tree `finish-validates-before-bookkeeping` — task — **Complete**
  - `M21.29` worker terminate also ends processes the harness started in their own session `terminate-ends-escaped-descendants` — task — **Complete**
  - `M21.30` A leaf's review policy is pinned at claim: the gate and finish refuse a roster, policy or review-switch change made on the integration branch after it until a human accepts it `review-policy-pinned-at-claim` — task — **Complete**
  - `M21.31` review record files only under the caller's own model: a filing from another harness or worker is refused, and a hand-filed record needs an attestation and counts only when signed or the policy allows it `review-record-files-only-as-the-caller` — task — **Complete**
  - `M21.32` session end ends only your own session: another agent's live record needs --force from a terminal, and the guard's refusal names the rule `session-end-only-your-own` — task — **Complete**
  - `M21.33` The brainstorm skill makes `specy-road brainstorm start` the first tool call, alone in its turn, in every harness's shipped copy `brainstorm-start-is-the-first-call-alone` — task — **Complete**
  - `M21.34` Context regression CR2 asks for a README section the todo app supports, and passes a README-only commit on the agent's own worktree branch `cr2-case-fits-the-todo-app` — task — **Complete**
  - `M21.35` review delegate gives a refused reviewer answer one repair turn with the refusal text, and the reviewer prompt ends with the notes rules `refused-review-gets-one-repair-turn` — task — **Complete**
  - `M21.36` brainstorm verify matches a quote across citation markers, typographic quotes and apostrophes, dashes, non-breaking spaces and soft hyphens `verify-normalizes-real-page-text` — task — **Complete**
  - `M21.37` One safe-write rule: setup and upgrade writers refuse any symlink on the path, and upgrade never writes outside the checkout `safe-write-rule-setup-writers` — task — **Complete**
  - `M21.38` Review writers and the review lock refuse any symlink on the path from the project root `review-writers-refuse-links` — task — **Not Started**
  - `M21.39` Publish, finish's land and reviews copy, and the pickup hint refuse any symlink on the path `ops-writers-refuse-links` — task — **Not Started**
  - `M21.40` upgrade's scratch git drops every GIT_ variable, runs no hook, and times out `upgrade-scratch-git-env-sterile` — task — **Complete**
  - `M21.41` The notes rules name every clause break the checker uses; rework docstring and verify tests fixed `notes-rules-name-every-clause-break` — task — **Complete**
  - `M21.42` review delegate also gives one repair turn when the final answer does not parse, not only when review record refuses it `parse-failure-gets-repair-turn` — task — **Complete**
  - `M21.43` digest refuses cleanly when the roadmap manifest is missing, like export --check `digest-check-no-manifest-clean-error` — task — **Complete**
  - `M21.44` A model observed to bypass specy-road's guidance is excluded from executor and reviewer roles when signed reviews are on, unless the roster entry opts in at its own risk `guidance-bypass-model-excluded-under-signed-reviews` — task — **Complete**
- `M22` rc5 fixes: defects found while preparing rc5 `rc5-fixes` — phase — **Not Started**
  - `M22.1` group-nodes accepts a new parent id held by one of the nodes it groups `group-into-member-id` — task — **Not Started**
  - `M22.2` A move rewrites touch zones that name a renamed planning sheet, and validate warns on a zone naming a missing sheet `move-rewrites-sheet-zones` — task — **Not Started**
  - `M22.3` Moves rewrite decision-ledger node ids, and validate warns on an open entry naming no node `decisions-follow-moves` — task — **Not Started**
  - `M22.4` New planning sheets no longer write the node's display id into their body `sheet-body-without-display-id` — task — **Not Started**
  - `M22.5` Executors cannot change the files that steer harnesses and specy-road unnoticed `steering-file-guard` — task — **Not Started**
  - `M22.6` A queued worker message that cannot be delivered flags the worker and goes out with its next turn `queued-message-undelivered` — task — **Not Started**
  - `M22.7` ready warns when a branch changes product files but adds nothing under the CHANGELOG's [Unreleased] heading `ready-changelog-reminder` — task — **Not Started**
  - `M22.8` init project ends with the next steps: set the integration branch, commit the scaffold, validate `init-next-steps` — task — **Not Started**
  - `M22.9` Local roster entries need allow_local_cli for preflight, cli_resume and harness_bin; a Codex reviewer runs memory-off in its own CODEX_HOME `local-roster-and-codex-reviewer-isolation` — task — **Not Started**
  - `M22.10` reconcile-branch keeps a local-only claim, and a checkout failure after a successful landing does not undo the bookkeeping `finish-keeps-local-claim-and-landing` — task — **Not Started**
  - `M22.11` Reports say what happened: a failed review tally is visible, rename-refs keeps tilde and longer fences, upgrade's ignore notices describe the checkout `reports-say-what-happened` — task — **Not Started**
  - `M22.12` The review gate fails closed with a working set-head command when refs/remotes/<remote>/HEAD is missing `gate-without-remote-head` — task — **Not Started**
  - `M22.13` Worker lows: a shell channels.cli is priced from its -m, and presence sessions stop counting once their worktree, branch or worker is gone `worker-cost-and-stale-presence` — task — **Not Started**
  - `M22.14` Roadmap and finish lows: set-dependencies takes display ids, no leftover briefs in the main checkout, finish says the checkout is on the landed branch `deps-ids-briefs-and-landed-branch` — task — **Not Started**
  - `M22.15` The agentic sandbox runbook states rc4's real results: checks after init, the second claim, tamper outcomes, where staleness shows `sandbox-runbook-rc4-drift` — task — **Not Started**
  - `M22.16` Reviewer run lows: a whole refusal summary, no parse reason after a capacity failure, and the reviewer's process group ended when its run ends `reviewer-run-summary-and-process-tree` — task — **Not Started**
  - `M22.17` brainstorm verify records blocked, not not-found, when a site answers its requests with 404 for pages that exist `verify-tells-a-blocking-404` — task — **Not Started**
  - `M22.18` The reviewer prompt asks for every required change in one pass, not just the first `reviewer-lists-every-required-change` — task — **Not Started**
  - `M22.19` Review inputs: READY identity normalized, unreadable acceptance and FIFO worker records refused cleanly, canonical marker names `review-inputs-identity-and-unreadable` — task — **Not Started**
  - `M22.20` worker terminate handles zombies, early forks and a failed ps; finish rollback keeps bytes, modes and other staging `terminate-and-finish-rollback-robustness` — task — **Not Started**
  - `M22.21` Previews and rollbacks match the real thing: verify brackets, upgrade dry-run digest, apply link rollback `preview-rollback-fidelity` — task — **Not Started**
  - `M22.22` Sandbox polish: planning-sheet save keeps untouched Markdown, and Escape closes only the front-most modal `sandbox-rc4-final-polish` — task — **Not Started**
  - `M22.23` Re-run the guidance-bypass cases through the Cursor harness with Grok, Sol and Opus `guidance-bypass-retest-cursor-grok-sol-opus` — task — **Not Started**
  - `M22.24` The guidance-bypass exclusion catches model-backed human entries, profile access.cli and quoted profile paths `guidance-exclusion-closes-three-bypasses` — task — **Not Started**
  - `M22.25` Upgrade's git calls in the project and planning mirrors share one bounded, cleaned environment `upgrade-git-calls-share-one-environment` — task — **Not Started**
  - `M22.26` The post-run zone check matches zones written from the git root `post-run-zone-check-git-root-zones` — task — **Complete**
  - `M22.27` The old-log review usage test asserts on the run, not on a substring `old-log-test-asserts-on-the-run` — task — **Complete**
  - `M22.28` upgrade does not warn about itself, and export's drift line says how to fix it `upgrade-no-self-warning-export-drift-hint` — task — **Not Started**
  - `M22.29` safe_write and archive moves traverse by directory descriptor `safe-write-directory-descriptors` — task — **Not Started**
  - `M22.30` Executors cannot change harness, policy, registry, review, shell or environment steering files unnoticed `steering-detection-other-classes` — task — **Not Started**
  - `M22.31` finish-this-task refuses a branch that changes a steering file no touch zone names `steering-finish-refusal` — task — **Not Started**
  - `M22.32` Claude Code launch and resume deny edits to steering files `steering-claude-launch-denies` — task — **Not Started**
  - `M22.33` A resumed review runs on the model it was asked for `reviewer-resume-keeps-the-model` — task — **Complete**
  - `M22.34` One accept-policy prompt covers every open claim `accept-policy-for-all-open-claims` — task — **Not Started**
  - `M22.35` upgrade mirrors only what the refreshes need, never ignored files `upgrade-mirror-skips-ignored-files` — task — **Not Started**
  - `M22.36` Each RC publishes its wheel URL and install line, and the package links to the guide `rc-publishes-wheel-url-and-project-urls` — task — **Not Started**
  - `M22.37` Test the Cursor CLI harness on the documented default `cursor-cli-harness-test-pass` — task — **Not Started**
  - `M22.38` doctor --fix never removes a claim that may belong to another clone `doctor-fix-keeps-other-clones-claims` — task — **Not Started**
  - `M22.39` Stalled workers are detected on every run and can be recovered in one command `worker-stall-recovery` — task — **Not Started**
- `M17` 0.3.1: PM GUI shows orchestration and worktree state, built in parallel with M16 `pm-gui-orchestration-view` — phase — **Not Started**
  - `M17.1` Gate: maintainer signs off the orchestration panels' information design and the read-only scope for 0.3.1 `pm-gui-orchestration-plan` — gate — **Complete**
  - `M17.2` PM GUI: orchestration snapshot types, a mock snapshot and a pure view model, tested against the mock `gui-orch-view-model` — task — **Not Started**
  - `M17.3` PM GUI: a read-only Orchestration drawer lists workers per leaf with state, harness and model, account, last activity and flags `gui-orch-drawer` — task — **Not Started**
  - `M17.4` PM GUI: per-leaf orchestration detail shows worktrees with dirty and ahead/behind, the READY commit, review verdicts with fresh-for-head, and the gate state `gui-orch-leaf-detail` — task — **Not Started**
  - `M17.5` PM GUI: the outline shows one orchestration badge per leaf for claims, holds, running or failed workers and review state, linking into the drawer `gui-orch-outline-badges` — task — **Not Started**
  - `M17.6` Orchestration snapshot schema 2: optional fields for the PM GUI (worker account, last activity and flags; worktree ahead/behind; READY, gate summary and holds per leaf) `orch-snapshot-schema-2` — task — **Not Started**
  - `M17.7` PM GUI server: GET /api/orchestration serves the snapshot read-only, with contract tests tying the server fixture and the GUI mock together `gui-api-orchestration` — task — **Not Started**
  - `M17.8` PM GUI orchestration view: docs/pm-gui.md and pm-workflow.md sections, the API table row, the CHANGELOG entry and a live check against the real route `gui-orch-docs-wiring` — task — **Not Started**
  - `M17.9` GUI acceptance on the agentic sandbox: a scripted browser run of the orchestration view against a built wheel and a seeded fixture repo, with a checklist and recorded results `gui-orch-sandbox-acceptance` — task — **Not Started**
  - `M17.10` Gate: maintainer approves using the agentic sandbox for M17.9's GUI acceptance run `gui-orch-sandbox-use-approved` — gate — **Not Started**
  - `M17.11` PM GUI: view and edit a node's acceptance criteria in the node edit dialog, through the existing PATCH and edit-node semantics `gui-acceptance-editing` — task — **Not Started**
  - `M17.12` PM GUI: a group-siblings outline action that calls the existing POST /api/outline/group `gui-group-siblings-action` — task — **Not Started**
  - `M17.13` PM GUI: a row click selects at once, so a toolbar action right after it acts on that row `gui-outline-selection-lag` — task — **Not Started**
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
  - `M19.19` Roadmap guide and template recommend one fixes milestone per release and themed milestones `milestone-conventions-guide` — task — **Not Started**
- `M20` Agent safety and governance posture (after 0.3.1) `agent-safety-posture` — phase — **Not Started**
  - `M20.1` Posture advisor: plan the M20 leaves from the research `plan-m20-from-research` — task — **Not Started**
  - `M20.2` Probe each reviewer harness for instruction-file leakage into fresh sessions `fresh-reviewer-leak-probe` — task — **Not Started**
- `M23` Post-0.3.1 field feedback `post-0-3-1-field-feedback` — phase — **Not Started**

## Open gates

Work behind these is deliberately held back until they clear.

- `M16.8.2 Gate: the release that shipped the M16 aliases is out and the maintainer closes the alias window` — **Not Started**
- `M16.8.9 Gate: ready to tag 0.3.1` — **Not Started**
- `M16.8.10 Gate: 0.3.1 tagged` — **Not Started**
- `M17.10 Gate: maintainer approves using the agentic sandbox for M17.9's GUI acceptance run` — **Not Started**

## Dependencies that were removed

Someone deliberately dropped these. Check why before re-adding one.

- 2026-11-06 `M22.22` stopped depending on `M21.40 upgrade's scratch git drops every GIT_ variable, runs no hook, and times out`
- 2026-11-06 `M22.22` stopped depending on `M21.37 One safe-write rule: setup and upgrade writers refuse any symlink on the path, and upgrade never writes outside the checkout`
- 2026-11-06 `M21.40` stopped depending on `M21.37 One safe-write rule: setup and upgrade writers refuse any symlink on the path, and upgrade never writes outside the checkout`
- 2026-11-06 `M21.43` stopped depending on `M21.37 One safe-write rule: setup and upgrade writers refuse any symlink on the path, and upgrade never writes outside the checkout`
- 2026-11-06 `M21.44` stopped depending on `M21.38 Review writers and the review lock refuse any symlink on the path from the project root`
- 2026-11-05 `M17.5` stopped depending on `M17.3 PM GUI: a read-only Orchestration drawer lists workers per leaf with state, harness and model, account, last activity and flags`
- 2026-11-05 `M19` stopped depending on `M16.8.9 Gate: ready to tag 0.3.1`
- 2026-11-05 `M18` stopped depending on `M16.8.9 Gate: ready to tag 0.3.1`
- 2026-11-05 `M20` stopped depending on `M16.8.9 Gate: ready to tag 0.3.1`
- 2026-11-05 `M17.1` stopped depending on `M16.3.1 Orchestration subpackage with one public interface and one state model for the gate, the CLI and the PM GUI`
- 2026-11-05 `M17.1` stopped depending on `M16.3.7 Fold the PM UI server and roadmap CRUD splits, after the orchestration snapshot is fixed`
- 2026-11-05 `M16.60` stopped depending on `M16.6.1 Docs by topic: design notes out of docs/, one workers doc, folded small docs, no pinned release candidate, one GUI extra`
- 2026-11-05 `M15.30` stopped depending on `2535829e-6a0d-40e3-aa42-9b0506bb9fe9` (no longer live)
- 2026-11-05 `M16.18` stopped depending on `M16.5.4 One check_assignment decides eligibility for every launch and for the gate`
- 2026-11-05 `M16.12` stopped depending on `M16.2.9 Commands run in the CLI's process: no python -m re-launch, no cwd globals`
- 2026-11-05 `M16.12` stopped depending on `M16.3.4 One LLM client module replaces the provider code inside review_node`
- 2026-11-05 `M16.15` stopped depending on `M16.1.2 Parity harness: a review-gate decision table covering every review policy`
- 2026-11-05 `M16.15` stopped depending on `M16.2.5 Library modules imported by the package move out of bundled_scripts`
- 2026-11-05 `M16.15` stopped depending on `M16.2.4 One roadmap index answers every graph query: by id, by key, effective dependencies, unmet, ready`
- 2026-11-05 `M16.33` stopped depending on `M16.4.2 upgrade absorbs the refresh commands and prints one report of what changed for the repo; update becomes self-update`
- 2026-11-05 `M16.33` stopped depending on `M16.4.3 review status, review packet, decisions --kind lesson and presence replace handoff status, review list, review-packet, lessons and session`
- 2026-11-05 `M16.33` stopped depending on `M16.4.1 doctor --prune is the one cleanup path; branches prune, registry-prune and the grind cleanup become aliases`
- 2026-11-05 `M16.33` stopped depending on `M16.5.7 Shared-checkout guard and session presence move into orchestration`
- 2026-11-05 `M16.33` stopped depending on `M16.5.14 Post-fix refactor gate: ready and the review packet report any complexity growth, and policy can block on it`
- 2026-11-05 `M16.33` stopped depending on `M16.4.5 One checks: block replaces baseline_cmd, land_check_cmd and verify_cmd with the same commands at the same points`
- _…and 46 earlier — `specy-road history --json`_

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
- 2026-11-06 `M15` (31 nodes) — `specy-road show-archive M15-94bbba0e-20261106`

## Claimed and in flight

Do not pick these up.

- `M18.13` on `feature/rm-zones-missing-what-acceptance-needs-flagged` since 2026-11-04
- `M18.14` on `feature/rm-stash-changes-attributed-to-the-owning-branch` since 2026-11-05
- `M19.10` on `feature/rm-file-limits-baseline-and-upgrade-report` since 2026-11-05
- `M19.6` on `feature/rm-the-orchestrator-cleans-up-landed-leaves-and-stale-worktrees-automatically-saving-hand-off-files-first` since 2026-11-05
- `M19.7` on `feature/rm-notices-for-how-the-agent-files-fit-together-missing-claude-md-import-two-load-orders-floor-read-twice` since 2026-11-05
- `M21.39` on `feature/rm-ops-writers-refuse-links` since 2026-11-06
- `M22.1` on `feature/rm-group-into-member-id` since 2026-11-06
- `M22.10` on `feature/rm-finish-keeps-local-claim-and-landing` since 2026-11-07
- `M22.15` on `feature/rm-sandbox-runbook-rc4-drift` since 2026-11-07
- `M22.17` on `feature/rm-verify-tells-a-blocking-404` since 2026-11-07
- `M22.18` on `feature/rm-reviewer-lists-every-required-change` since 2026-11-07
- `M22.5` on `feature/rm-steering-file-guard` since 2026-11-05
- `M22.7` on `feature/rm-ready-changelog-reminder` since 2026-11-06
- `M22.8` on `feature/rm-init-next-steps` since 2026-11-07

## Quality by area

Review cost of the last 50 completed leaves, per touch-zone area, from the `Review-tally` trailers on their gate commits. Block rate is the share of tallied leaves with at least one blocking round; areas above 50% are **flagged** and listed first. Plan tighter acceptance there.

| Area | Leaves | No tally | Mean rounds | Block rate | Integrity findings | RCA escalations |
| --- | --- | --- | --- | --- | --- | --- |
| `docs` **flagged** | 32 | 0 | 2.78 | 56% | 34 | 3 |
| `model-profiles` **flagged** | 1 | 0 | 3.00 | 100% | 5 | 0 |
| `roadmap` **flagged** | 1 | 0 | 3.00 | 100% | 1 | 0 |
| `schemas` **flagged** | 1 | 0 | 3.00 | 100% | 5 | 0 |
| `specy_road` **flagged** | 46 | 0 | 2.67 | 54% | 42 | 5 |
| `tests` **flagged** | 49 | 0 | 2.61 | 53% | 42 | 5 |
| `CHANGELOG.md` | 34 | 0 | 2.24 | 41% | 31 | 2 |
| `planning` | 2 | 0 | 2.00 | 50% | 0 | 0 |
| `suggested_prompts` | 3 | 0 | 1.00 | 0% | 3 | 0 |

Leaves with no tally landed before tallies were recorded; they are left out of the rates.

## Reaching the detail behind this

This digest is a summary. The full text of planning sheets, shared contracts and archived work is searchable:

```bash
specy-road search "<query>"                 # live + archived, ranked
specy-road search "<query>" --scope archived  # completed work only
specy-road search <NODE_ID>                  # everything about one node
specy-road history <NODE_ID>                 # how it got to this state
```
