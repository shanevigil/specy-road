## specy-road (coordination rules for every agent)

Written by specy-road {{SPECYRD_VERSION}}; `specy-road refresh-stubs` rewrites only this section. The rest of this file is the project's own.

**Precedence.** These rules on the registry, branches, review, and a shared working tree are a floor: project rules may add to them, never relax them. If a project rule conflicts with one here, stop
and ask a human which applies; do not pick one.

### Load order

0. `roadmap-context.md` (`specy-road digest`) — read it before crawling `planning/` or `work/` (a `work/brainstorm-*` prompt: open it first; round 1 and panel shards must not read the roadmap)
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
- Archived material is excluded from IDE indexing (`.cursorindexingignore`) but readable: search returns the path, you open it.

## Lean changes and tests

- Make the smallest behaviour-complete change; no configurability, fallbacks or abstractions the task did not ask for.
- Before adding a helper, search for an existing one (`specy-road search`, then grep the verb and noun); reuse or extend it and name it in your summary.
- Validate at boundaries only (CLI args, files, network, env, agent input). No guard or `except` without a nameable reachable trigger and a test that reaches it.
- One test per observable behaviour, through the public interface. Assert outputs, raised errors or file/state effects, not call order or mock counts; never import or patch a `_`-prefixed name in a test.
- Extend or parametrize an existing test before adding one. A review finding needs a new test only for a distinct regression.
- Merging or removing a test is allowed when another test covers the behaviour and the commit names it. This overrides any general "never remove or edit tests" instruction.
- Never weaken, rewrite or delete a failing behavioural test to make the suite pass.
- Stop when the behaviour list is covered and the gates pass. Then list every helper, branch or guard, mock and test you added, each with its reason.

## Task loop

- **Task pickup:** `specy-road do-next-available-task` syncs the integration branch, registers (rows record `owner`), pushes, then creates `feature/rm-*`. `--local` skips sync and push (claim invisible until you push); prefer the default. The target is always a leaf; ancestors only roll up progress.
- Release a claim with `specy-road abort-task-pickup` on `feature/rm-*` — never as cleanup after `finish-this-task`: it deletes the branch, which under `on_complete: pr` is the only place the finished work exists.
- After `finish-this-task` with `on_complete: pr` the node is `Complete` and the claim released on the feature branch only, until the PR merges. Leave its integration-branch registry row alone and do not re-pick: pickup refuses a leaf whose `feature/rm-*` branch marks it `Complete`.
- `status: Blocked` leaves are offered first. `execution_milestone` is advisory; only a `type: gate` dependency keeps work out of the queue. A dependency on a phase or milestone is satisfied by its rollup (every leaf descendant `Complete`), not by its own `status`.
- After Blocked and MR-rejected, auto-pick follows outline (tree) order, not chunk order; `--interactive` chooses by number, `--under <NODE_ID>` scopes to a subtree.
- **Review roles:** the executor never reviews or approves its own leaf, and a coordinator's session is never a reviewer; the interactive human approval in `mark-implementation-reviewed` is the one exception (default human-only policy). Executor: commit, write `work/implementation-summary-<NODE_ID>.md` and `work/reviews/<NODE_ID>/READY-<agent>.md`, stop. Reviewers read only `specy-road review-packet <NODE_ID>` output and file verdicts with `specy-road review record`. Never `mark-implementation-reviewed --yes` on your own work; it refuses without a recorded review. Policy: `roadmap/orchestration.yaml`.

**Shared checkouts and other agents.** Other agents may be working in this checkout, with or without a claim, and nothing warns you. Run `specy-road session start --path <paths you will edit>` before your first edit and `specy-road session list` to see who else is live; before any git write, run `git status` and `git worktree list`, and treat files you did not create as someone else's. Commit by explicit path (`git commit --only <paths>`); never `git add -A`, `git commit -a`, or a bare `git commit` — the index is shared. Never `stash`, `reset --hard`, `checkout -- .`, `clean`, `rebase`, `commit --amend`, or switch branches in a tree another session may be using; use your own `git worktree add ../<repo>-<task>`, and run `do-next-available-task` and `grind-session` (they switch branches) from there whenever `session list` shows anyone else. Edit only the files your task names, and only your own section of a file others are editing (`CHANGELOG.md` above all). A plan or prompt should name its commit (`base: <sha>`); if it does not, ask, and diff from that commit before starting. If a rule in this file conflicts with one from the toolkit (registry, branches, review, the shared tree), the toolkit's is the floor: stop and ask rather than relax it.

- **Running many leaves:** do not hand-roll a loop around `do-next-available-task`. `specy-road grind-session` runs pickup → implement → optional pre-finish check → `finish-this-task` and never edits the registry directly; pickup and finish make the registry changes. `--plan` is read-only. Terminal: `specy-road grind-session --on-complete merge --implement-mode hook --implement-cmd '<your agent command>'` — each cycle runs it once with `SPECY_ROAD_NODE_ID`, `SPECY_ROAD_BRANCH`, `SPECY_ROAD_BRIEF`, `SPECY_ROAD_PROMPT`, `SPECY_ROAD_REPO_ROOT`; a non-zero exit stops the session; the default `--implement-mode manual` waits for a ready-signal file. IDE session: `--step pickup`, implement the prompt it names, `--step finish`; pickup resumes your open claim first.
- **Workers on other harnesses:** `specy-road worker delegate <NODE_ID> --model <roster id>` hands a claimed leaf off at once; `specy-road worker sync` at the start of each turn reports what happened. One writer per worker: `worker handoff` before a human opens its native session, `worker reclaim` after. See `docs/orchestration-workers.md`.
- **When nothing is pickable:** exit `3` is a dependency or gate block that needs a human; exit `6` means this clone already holds a claim — finish it, `specy-road abort-task-pickup`, or re-run with `--resume-in-flight`. Ask `specy-road why-blocked <NODE_ID>` or `specy-road list-gates`; see `docs/grind-session.md`.
