# Roadmap context

<!-- specy-road: generated context digest — do not edit by hand. Regenerate with `specy-road digest`. -->

The current state of this project's roadmap, generated from the merged graph, the archive ledger and git history. Read this before crawling `planning/` or `work/` — it is the authoritative summary, and those directories contain a great deal of duplicated text.

## Live roadmap

Status is the computed rollup: a non-leaf is Complete only when every leaf descendant is.

- `M1` Adopt specy-road `adopt-specy-road` — phase — **Not Started**
  - `M1.1` Set up the project's specy-road basics `project-setup` — task — **Not Started**
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
- `M4` Brainstorm and roadmap editing features `brainstorm-editing-features` — phase — **Not Started**
  - `M4.1` promote carries the converge judgement into sheets and writes an authoring prompt `promote-judgement` — task — **Not Started**
  - `M4.2` Structured promote: target parents, clusters, minimum recommendation, plan file `promote-structured` — task — **Not Started**
  - `M4.3` Batch ideas and verdicts from a file, merge, and gap ideas `brainstorm-batch-io` — task — **Not Started**
  - `M4.4` Policies and decisions as first-class brainstorm outcomes; frame amendments `brainstorm-decisions` — task — **Not Started**
  - `M4.5` Repository files as evidence; null results; quotes on research-born ideas `brainstorm-repo-evidence` — task — **Not Started**
  - `M4.6` Lenses from the frame and a ranked node list in the recommend prompt `brainstorm-lenses` — task — **Not Started**
  - `M4.7` Scriptable graph edits: apply a change file with dry run, acceptance at creation, display-id dependencies `graph-apply` — task — **Complete**
  - `M4.8` list-nodes --json, refresh-stubs --diff, move-node zone rewrite `graph-listing-and-moves` — task — **Complete**
  - `M4.9` Opt-in auto-pick ordering by execution milestone `pick-ordering` — task — **Complete**
  - `M4.10` Clean up merged feature branches after finish `branch-cleanup` — task — **Complete**
  - `M4.11` grind-session --plan keeps ready leaves with overlapping touch zones out of the same parallel wave `grind-session-plan-keeps-ready-leaves-with-overlapping-touch-zones-out-of-the-same-parallel-wave` — task — **Complete**
  - `M4.12` file-limits function-length check covers TypeScript and JavaScript `file-limits-function-length-check-covers-typescript-and-javascript` — task — **Complete**
  - `M4.13` specy-road doctor lists merged or stale feature branches, worktrees, registry rows and stashes `specy-road-doctor-lists-merged-or-stale-feature-branches-worktrees-registry-rows-and-stashes` — task — **Complete**
  - `M4.14` brainstorm promote inherits execution_milestone from the anchor `brainstorm-promote-inherits-execution-milestone-from-the-anchor` — task — **Complete**
  - `M4.15` Session overlap warnings name the other worktree and its edit state `session-overlap-warnings-name-the-other-worktree-and-its-edit-state` — task — **Not Started**
  - `M4.16` Review rounds and elapsed time per leaf, and doctor lists detached worktrees `review-rounds-and-elapsed-time-per-leaf-and-doctor-lists-detached-worktrees` — task — **Not Started**
  - `M4.17` Review-loop escalation: a root-cause analysis runs when reviews keep blocking `review-loop-escalation-a-root-cause-analysis-runs-when-reviews-keep-blocking` — task — **Complete**
  - `M4.18` Further TS/JS syntax forms for the function cap found in M4.12 review `further-ts-js-syntax-forms-for-the-function-cap-found-in-m4-12-review` — task — **Not Started**
- `M5` Agent context and outcomes `context-and-outcomes` — phase — **Not Started**
  - `M5.1` Every managed AGENTS.md rule carries its provenance in the template `rule-provenance` — task — **Complete**
  - `M5.2` validate flags specy-road commands that do not exist in the consumer's agent files `stale-command-check` — task — **Complete**
  - `M5.3` validate reports always-injected context per harness against documented limits `context-budget-meter` — task — **Complete**
  - `M5.4` Rules the CLI or hooks enforce shrink to one-line pointers in the managed block `enforced-rules-pointers` — task — **Not Started**
  - `M5.5` A replayable context regression set for the sandbox runbook `context-regression-set` — task — **Complete**
  - `M5.6` Pilot the context-feedback question in the sandbox before shipping it `context-feedback-pilot` — task — **Not Started**
  - `M5.7` Measure the managed section on and off across the sandbox apps `managed-section-ablation` — task — **Not Started**
  - `M5.8` Further Markdown mention forms for the stale-command check found in M5.2 review `further-markdown-mention-forms-for-the-stale-command-check-found-in-m5-2-review` — task — **Not Started**
- `M6` 0.3.1-rc2 release `release-0-3-1-rc2` — phase — **Not Started**
  - `M6.1` Close out the triage note, changelog and what's-new for rc2 `rc2-closeout-docs` — task — **Not Started**
  - `M6.2` Pre-release checks and the 0.3.1-rc2 cut `rc2-cut` — task — **Not Started**
- `M7` Keeping current: recurring research `keeping-current-recurring-research` — phase — **Not Started**
  - `M7.1` A research register tracks deep-research topics with a refresh cadence `a-research-register-tracks-deep-research-topics-with-a-refresh-cadence` — task — **Not Started**
  - `M7.2` Run the harness-capabilities research and fold its findings `run-the-harness-capabilities-research-and-fold-its-findings` — task — **Not Started**
- `M8` Harness compatibility `harness-compatibility` — phase — **Not Started**
  - `M8.1` Harness facts fixture drives model-profiles and executor templates, with a classified diff on version bumps `harness-facts-fixture-drives-model-profiles-and-executor-templates-with-a-classified-diff-on-version-bumps` — task — **Not Started**
  - `M8.2` Worker adapters harden the launch and run a deterministic post-run check `worker-adapters-harden-the-launch-and-run-a-deterministic-post-run-check` — task — **Not Started**
  - `M8.3` Reviewer runs are read-only and specy-road writes the review record from structured output `reviewer-runs-are-read-only-and-specy-road-writes-the-review-record-from-structured-output` — task — **Not Started**
  - `M8.4` Ship skills once and meter every file each harness injects `ship-skills-once-and-meter-every-file-each-harness-injects` — task — **Not Started**
  - `M8.5` Guard hooks per harness and avoid lists in every model profile `guard-hooks-per-harness-and-avoid-lists-in-every-model-profile` — task — **Not Started**
  - `M8.7` Runtime verification of the harness facts against installed binaries `runtime-verification-of-the-harness-facts-against-installed-binaries` — task — **Not Started**
  - `M8.6` Candidate harness profiles: Copilot CLI reviewer and Antigravity agy generic `candidate-harness-profiles-copilot-cli-reviewer-and-antigravity-agy-generic` — task — **Not Started**

## Claimed and in flight

Do not pick these up.

- `M1.1` on `feature/rm-project-setup` since 2026-10-28

## Reaching the detail behind this

This digest is a summary. The full text of planning sheets, shared contracts and archived work is searchable:

```bash
specy-road search "<query>"                 # live + archived, ranked
specy-road search "<query>" --scope archived  # completed work only
specy-road search <NODE_ID>                  # everything about one node
specy-road history <NODE_ID>                 # how it got to this state
```
