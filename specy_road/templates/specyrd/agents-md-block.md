## specy-road (coordination rules for every agent)

Written by specy-road {{SPECYRD_VERSION}}; `specy-road refresh-stubs` rewrites only this section. The rest of this file is the project's own.

**Precedence.** These rules on the registry, branches, review, and a shared working tree are a floor: project rules may add to them, never relax them. If a project rule conflicts with one here, stop
and ask a human which applies; do not pick one.
<!-- prevents: a project rule quietly relaxing the toolkit's registry, branch, review or shared-tree rules, or an agent picking a side on a conflict | enforced: advisory; validate warns when this block is missing or differs from the installed version | ref: docs/design-notes/agent-guidance-and-shared-checkouts.md decision 4 -->

### Load order

0. `roadmap-context.md` (`specy-road digest`) — read it before crawling `planning/` or `work/` (brainstorming: run `brainstorm start` before reading this or anything else, then open its `work/brainstorm-*` prompt; round 1 and panel shards must not read the roadmap)
1. `constitution/purpose.md`
2. `constitution/principles.md`
3. `constraints/README.md`
4. `docs/supply-chain-security.md`
5. `roadmap/manifest.json` + chunk files: your node, parents, dependencies
6. `planning/<id>_<slug>_<node_key>.md` for each node with `planning_dir` (ancestor sheets too)
7. `shared/README.md`, then only the contracts cited for the task

Focused brief: `specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md`. Its `## 6. Dependency context` inlines each dependency's `## Intent`: read that instead of dependency sheets, and never paraphrase dependencies in a planning sheet you author.

## Finding things

- Do not grep `planning/` or `work/`: briefs and pr-bodies re-inline their sources. Use `specy-road search "<query>"` (`--scope archived` for completed work; a `<NODE_ID>` for one node) and `specy-road history <NODE_ID>`.
<!-- prevents: grep hits repeated across briefs and pr-bodies that re-inline one source, flooding the context window | enforced: advisory; search ranks and deduplicates (specy_road/search_index.py) | ref: CHANGELOG v0.2.1-rc1, agent context: digest and search -->
- Archived material is excluded from IDE indexing (`.cursorindexingignore`) but readable: search returns the path, you open it.
<!-- prevents: an agent concluding archived work is gone and redoing it because the IDE index hides it | enforced: the .cursorindexingignore managed block (specy_road/agent_ignores.py) | ref: CHANGELOG v0.2.1-rc1, specyrd init maintains a marked block -->

## Lean changes and tests

- Make the smallest behaviour-complete change; no configurability, fallbacks or abstractions the task did not ask for.
<!-- prevents: speculative options, fallbacks and abstractions nobody asked for | enforced: the reviewer prompt's excess checklist (bundled_scripts/role_prompt.py) | ref: docs/design-notes/lean-code-census.md -->
- Before adding a helper, search for an existing one (`specy-road search`, then grep the verb and noun); reuse or extend it and name it in your summary.
<!-- prevents: a second helper written beside one that already does the job | enforced: the reviewer checklist's Duplicated logic class | ref: docs/design-notes/lean-code-census.md -->
- Validate at boundaries only (CLI args, files, network, env, agent input). No guard or `except` without a nameable reachable trigger and a test that reaches it.
<!-- prevents: defensive guards for impossible states; the census found 41 percent of defensive lines never executed | enforced: the reviewer checklist's Unreachable defence class | ref: docs/design-notes/lean-code-census.md, defensive lines -->
- One test per observable behaviour, through the public interface. Assert outputs, raised errors or file/state effects, not call order or mock counts; never import or patch a `_`-prefixed name in a test.
<!-- prevents: tests pinned to internals that break on a behaviour-preserving refactor | enforced: CI private-import baseline (constraints/test-private-imports-baseline.txt) and the reviewer checklist's Test pins internals class | ref: docs/design-notes/lean-code-census.md, private-name coupling -->
- Extend or parametrize an existing test before adding one. A review finding needs a new test only for a distinct regression.
<!-- prevents: near-duplicate tests; 70 percent of traced tests covered no line of their own | enforced: the reviewer checklist's Overlapping test class | ref: docs/design-notes/lean-code-census.md, whole suite -->
- Merging or removing a test is allowed when another test covers the behaviour and the commit names it. This overrides any general "never remove or edit tests" instruction.
<!-- prevents: redundant tests kept forever because a harness-wide instruction forbids touching tests | enforced: advisory; the commit must name the covering test | ref: docs/design-notes/lean-code-census.md -->
- Never weaken, rewrite or delete a failing behavioural test to make the suite pass.
<!-- prevents: a green suite bought by removing the test that caught the bug | enforced: reviewers judge the diff through review-packet | ref: tests/test_lean_rules.py -->
- Stop when the behaviour list is covered and the gates pass. Then list every helper, branch or guard, mock and test you added, each with its reason.
<!-- prevents: open-ended polishing and additions the reviewer never hears about | enforced: review-packet flags a summary with no Added inventory (bundled_scripts/review_packet.py) | ref: tests/test_lean_rules.py -->

## Task loop

- **Task pickup:** `specy-road do-next-available-task` syncs the integration branch, registers (rows record `owner`), pushes, then creates `feature/rm-*`. `--local` skips sync and push (claim invisible until you push); prefer the default. The target is always a leaf; ancestors only roll up progress.
<!-- prevents: two agents claiming one leaf because a claim never reached the remote | enforced: pickup syncs and pushes the registration by default; --local is the only opt-out | ref: docs/dev-workflow.md, tests/test_do_next_task_pickup.py -->
- Release a claim with `specy-road abort-task-pickup` on `feature/rm-*` — never as cleanup after `finish-this-task`: it deletes the branch, which under `on_complete: pr` is the only place the finished work exists.
<!-- prevents: finished work lost when abort deletes the only branch that holds it | enforced: finish-this-task warns that abort would delete the branch | ref: CHANGELOG v0.2.3-rc2, finish spells out what on_complete pr leaves behind -->
- After `finish-this-task` with `on_complete: pr` the node is `Complete` and the claim released on the feature branch only, until the PR merges. Leave its integration-branch registry row alone and do not re-pick: pickup refuses a leaf whose `feature/rm-*` branch marks it `Complete`.
<!-- prevents: a finished, unmerged leaf claimed and implemented twice | enforced: pickup reads the feature-branch tip (bundled_scripts/do_next_finished_unmerged.py) | ref: tests/test_do_next_finished_unmerged.py, docs/git-workflow.md -->
- `status: Blocked` leaves are offered first. `execution_milestone` is advisory; only a `type: gate` dependency keeps work out of the queue. A dependency on a phase or milestone is satisfied by its rollup (every leaf descendant `Complete`), not by its own `status`.
<!-- prevents: agents waiting on a milestone hint or on a parent status nobody flips | enforced: pickup tiers and rollup dependency satisfaction (bundled_scripts/do_next_available.py) | ref: CHANGELOG v0.1.4, dependency satisfaction follows rollup status; tests/test_do_next_gate.py -->
- After Blocked and MR-rejected, auto-pick follows outline (tree) order, not chunk order; `--interactive` chooses by number, `--under <NODE_ID>` scopes to a subtree.
<!-- prevents: an agent reading a pick in outline order as a bug because it expected chunk or id order | enforced: pickup sorts by outline (bundled_scripts/do_next_available.py) | ref: docs/grind-session.md, why the plan and the pickup can look like they disagree -->
- **Review roles:** the executor never reviews or approves its own leaf, and a coordinator's session is never a reviewer; the interactive human approval in `mark-implementation-reviewed` is the one exception (default human-only policy). Executor: commit, write `work/implementation-summary-<NODE_ID>.md` and `work/reviews/<NODE_ID>/READY-<agent>.md`, stop. Reviewers read only `specy-road review-packet <NODE_ID>` output and file verdicts with `specy-road review record`. Never `mark-implementation-reviewed --yes` on your own work; it refuses without a recorded review. Policy: `roadmap/orchestration.yaml`.
<!-- prevents: an agent approving its own work, or an unattended coordinator closing a gate nobody reviewed | enforced: mark-implementation-reviewed --yes refuses without recorded reviews that meet the policy (specy_road/review_gate.py) | ref: docs/orchestration.md, tests/test_mark_implementation_reviewed_gate.py -->

**Shared checkouts and other agents.** Other agents may be working in this checkout, with or without a claim, and nothing warns you. Run `specy-road session start --path <paths you will edit>` before your first edit and `specy-road session list` to see who else is live; before any git write, run `git status` and `git worktree list`, and treat files you did not create as someone else's. Commit by explicit path (`git commit --only <paths>`); never `git add -A`, `git commit -a`, or a bare `git commit` — the index is shared. Never `stash`, `reset --hard`, `checkout -- .`, `clean`, `rebase`, `commit --amend`, or switch branches in a tree another session may be using; use your own `git worktree add ../<repo>-<task>`, and run `do-next-available-task` and `grind-session` (they switch branches) from there whenever `session list` shows anyone else. Edit only the files your task names, and only your own section of a file others are editing (`CHANGELOG.md` above all). A plan or prompt should name its commit (`base: <sha>`); if it does not, ask, and diff from that commit before starting. If a rule in this file conflicts with one from the toolkit (registry, branches, review, the shared tree), the toolkit's is the floor: stop and ask rather than relax it.
<!-- prevents: one session's branch switch or git add -A landing on another session's uncommitted work, and plans written against a commit that has since moved | enforced: session check exits 1 when staged paths overlap another live session's (bundled_scripts/session_cli.py); the rest is advisory | ref: docs/design-notes/agent-guidance-and-shared-checkouts.md, what happened -->

- **Running many leaves:** do not hand-roll a loop around `do-next-available-task`. `specy-road grind-session` runs pickup → implement → optional pre-finish check → `finish-this-task` and never edits the registry directly; pickup and finish make the registry changes. `--plan` is read-only. Terminal: `specy-road grind-session --on-complete merge --implement-mode hook --implement-cmd '<your agent command>'` — each cycle runs it once with `SPECY_ROAD_NODE_ID`, `SPECY_ROAD_BRANCH`, `SPECY_ROAD_BRIEF`, `SPECY_ROAD_PROMPT`, `SPECY_ROAD_REPO_ROOT`; a non-zero exit stops the session; the default `--implement-mode manual` waits for a ready-signal file. IDE session: `--step pickup`, implement the prompt it names, `--step finish`; pickup resumes your open claim first.
<!-- prevents: hand-rolled loops that edit the registry directly and drift from what pickup and finish record | enforced: grind-session drives pickup and finish itself | ref: docs/grind-session.md -->
- **Workers on other harnesses:** `specy-road worker delegate <NODE_ID> --model <roster id>` hands a claimed leaf off at once; `specy-road worker sync` at the start of each turn reports what happened. One writer per worker: `worker handoff` before a human opens its native session, `worker reclaim` after. See `docs/orchestration-workers.md`.
<!-- prevents: two writers on one worker's branch when a human opens its native session mid-run | enforced: worker handoff and reclaim (bundled_scripts/worker_cli.py) | ref: docs/design-notes/v0-3-1-worker-orchestration.md -->
- **When nothing is pickable:** exit `3` is a dependency or gate block that needs a human; exit `6` means this clone already holds a claim — finish it, `specy-road abort-task-pickup`, or re-run with `--resume-in-flight`. Ask `specy-road why-blocked <NODE_ID>` or `specy-road list-gates`; see `docs/grind-session.md`.
<!-- prevents: an unattended loop retrying a block that needs a human, or treating its own open claim as a dependency block | enforced: grind-session exit codes 3 and 6 (bundled_scripts/grind_session_events.py) | ref: docs/grind-session.md -->
