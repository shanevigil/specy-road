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
- `M3` 0.3.1 pre-final fixes from rc1 feedback `pre-final-fixes` — phase — **Not Started**
  - `M3.1` Refuse to pick up leaves whose planning sheet is still a placeholder `unauthored-leaf-guard` — task — **Complete**
  - `M3.2` handoff status reports review records without a claim `handoff-local-records` — task — **Complete**
  - `M3.3` Document the canonical chunk key order and offer a deliberate normalisation `chunk-key-order` — task — **Complete**
  - `M3.4` Brainstorm prompts: shards from the allocation, per-pass files, framing with proposed answers `brainstorm-prompt-fixes` — task — **Complete**
  - `M3.5` Converge and evidence passes that cannot silently skip work `brainstorm-converge-checks` — task — **Not Started**
  - `M3.6` Triage commands: realize, append-why, summary, consistent reasons, all-or-nothing accept `brainstorm-triage-cli` — task — **Not Started**
  - `M3.7` promote writes usable nodes once, with short codenames `promote-node-quality` — task — **Not Started**
  - `M3.8` Upgrade and validate report drift and migrations plainly `upgrade-and-validate-checks` — task — **Complete**
  - `M3.9` Worker and session CLI: resume permissions, roster provenance, event gaps `worker-cli-fixes` — task — **Not Started**
  - `M3.10` Worker hand-off, reconcile and finish report what actually happened `worker-reconcile-and-status` — task — **Not Started**
  - `M3.11` Roster ids with effort suffixes, packet path, stale sessions `roster-profiles-and-packet-path` — task — **Not Started**
- `M4` Brainstorm and roadmap editing features `brainstorm-editing-features` — phase — **Not Started**
  - `M4.1` promote carries the converge judgement into sheets and writes an authoring prompt `promote-judgement` — task — **Not Started**
  - `M4.2` Structured promote: target parents, clusters, minimum recommendation, plan file `promote-structured` — task — **Not Started**
  - `M4.3` Batch ideas and verdicts from a file, merge, and gap ideas `brainstorm-batch-io` — task — **Not Started**
  - `M4.4` Policies and decisions as first-class brainstorm outcomes; frame amendments `brainstorm-decisions` — task — **Not Started**
  - `M4.5` Repository files as evidence; null results; quotes on research-born ideas `brainstorm-repo-evidence` — task — **Not Started**
  - `M4.6` Lenses from the frame and a ranked node list in the recommend prompt `brainstorm-lenses` — task — **Not Started**
  - `M4.7` Scriptable graph edits: apply a change file with dry run, acceptance at creation, display-id dependencies `graph-apply` — task — **Not Started**
  - `M4.8` list-nodes --json, refresh-stubs --diff, move-node zone rewrite `graph-listing-and-moves` — task — **Not Started**
  - `M4.9` Opt-in auto-pick ordering by execution milestone `pick-ordering` — task — **Not Started**
- `M5` Agent context and outcomes `context-and-outcomes` — phase — **Not Started**
  - `M5.1` Every managed AGENTS.md rule carries its provenance in the template `rule-provenance` — task — **Complete**
  - `M5.2` validate flags specy-road commands that do not exist in the consumer's agent files `stale-command-check` — task — **Not Started**
  - `M5.3` validate reports always-injected context per harness against documented limits `context-budget-meter` — task — **Not Started**
  - `M5.4` Rules the CLI or hooks enforce shrink to one-line pointers in the managed block `enforced-rules-pointers` — task — **Not Started**
  - `M5.5` A replayable context regression set for the sandbox runbook `context-regression-set` — task — **Not Started**
  - `M5.6` Pilot the context-feedback question in the sandbox before shipping it `context-feedback-pilot` — task — **Not Started**
  - `M5.7` Measure the managed section on and off across the sandbox apps `managed-section-ablation` — task — **Not Started**
- `M6` 0.3.1-rc2 release `release-0-3-1-rc2` — phase — **Not Started**
  - `M6.1` Close out the triage note, changelog and what's-new for rc2 `rc2-closeout-docs` — task — **Not Started**
  - `M6.2` Pre-release checks and the 0.3.1-rc2 cut `rc2-cut` — task — **Not Started**

## Claimed and in flight

Do not pick these up.

- `M3.9` on `feature/rm-worker-cli-fixes` since 2026-10-28
- `M4.7` on `feature/rm-graph-apply` since 2026-10-28
- `M4.8` on `feature/rm-graph-listing-and-moves` since 2026-10-28
- `M4.9` on `feature/rm-pick-ordering` since 2026-10-28

## Reaching the detail behind this

This digest is a summary. The full text of planning sheets, shared contracts and archived work is searchable:

```bash
specy-road search "<query>"                 # live + archived, ranked
specy-road search "<query>" --scope archived  # completed work only
specy-road search <NODE_ID>                  # everything about one node
specy-road history <NODE_ID>                 # how it got to this state
```
