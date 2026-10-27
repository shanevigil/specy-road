## specy-road (coordination rules for every agent)

Written by specy-road {{SPECYRD_VERSION}}; `specy-road refresh-stubs` rewrites
this section and touches nothing outside its markers. Everything else in this
file is the project's own.

**Precedence.** The rules in this section on the registry, branches, review,
and a shared working tree are a floor. A project's own rules in this file may
add to them, never relax them. If a project rule conflicts with one here, stop
and ask a human which applies; do not pick one.

### Load order

0. `roadmap-context.md` — the current state of the roadmap in one file: what is
   done, what was decided, which gates are open, which dependencies were dropped,
   and what has been archived. Read this before crawling `planning/` or `work/`.
   Regenerate with `specy-road digest`.
1. `constitution/purpose.md` — why this exists
2. `constitution/principles.md` — how we decide
3. `constraints/README.md` — enforced rules
4. `docs/supply-chain-security.md` — dependency and supply-chain verification policy (adopt what matches your stack)
5. Merged roadmap (`roadmap/manifest.json` + chunk files): your node, parents, and dependencies
6. `planning/<id>_<slug>_<node_key>.md` feature sheet for each node that has `planning_dir` (read ancestor sheets for context)
7. `shared/README.md`, then only contract files cited for the task

Focused brief:

```bash
specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md
```

## Finding things

Do not grep `planning/` or `work/` directly. Those directories hold a great deal
of duplicated text — a brief inlines its ancestor planning sheets and every
`shared/*.md` file it cites, and a pr-body re-inlines the whole brief — so a raw
search returns the same passage many times over. Use the ranked, deduplicated
index instead:

```bash
specy-road search "<query>"                    # live + archived, current work first
specy-road search "<query>" --scope archived   # completed work, hidden from IDE indexing
specy-road search <NODE_ID>                    # everything about one node
specy-road history <NODE_ID>                   # how it reached its current state
```

Archived roadmap material is deliberately excluded from IDE indexing (see
`.cursorindexingignore`) so it cannot crowd out current decisions. It is still
fully readable — search returns a path, and you open it.

The brief inlines each effective dependency's `## Intent` block under `## 6. Dependency context (intent of upstream work)` — read it before opening dependency planning sheets directly. When **authoring** a planning sheet, do not paraphrase what dependencies deliver; the brief carries that for the coding agent automatically.

**Task pickup:** When using `specy-road do-next-available-task`, the command by default **syncs** the integration branch, **registers**, **pushes** it, then creates `feature/rm-*` so the team sees the claim on the remote (`--local` skips sync and push for offline or private work — then the claim is invisible to peers until you push the integration branch, so prefer the default; every row records `owner`). The pickup target is always an actionable **leaf**; ancestors are context containers and roll up progress from descendants. To release a claim without finishing, use `specy-road abort-task-pickup` on `feature/rm-*` (see `docs/dev-workflow.md`) — but **never as cleanup after `finish-this-task`**: abort deletes the feature branch, and under `on_complete: pr` that branch is the only place the finished work exists.

**After `finish-this-task` with `on_complete: pr`:** the node is `Complete` and the claim released **on the feature branch**, while the integration branch still shows neither until the PR merges. Both are true at once. Leave the registry row on the integration branch alone — it is what keeps the leaf off the available list — and do not re-pick the node. Pickup also refuses a leaf whose `feature/rm-*` branch already marks it `Complete`, so a missing row is not a second chance.

Three selection rules that are easy to read backwards:

- **`status: Blocked` leaves are offered FIRST**, not skipped — a blocked leaf is the one most worth unblocking. Pickup prints `status: Blocked` when it hands you one. To keep work out of the queue entirely, give it a `type: gate` dependency instead of marking it Blocked.
- **`execution_milestone` (`Human-led` / …) is advisory.** It documents intent; it does not gate pickup. `type: gate` is the enforcing mechanism.
- **A dependency on a phase or milestone is satisfied by its rollup** — every leaf descendant `Complete` — not by that node's own `status` field.

After Blocked and MR-rejected, auto-pick follows **outline (tree) order**, not raw merged chunk order (`docs/roadmap-authoring.md`). That is delivery order, not the order you would choose to *design* in — if you want to cut a seam first, use `--interactive` to choose by number, or `--under <NODE_ID>` to scope to one subtree.

**Review roles:** the session that implements a leaf (executor) never reviews or approves it, and an agent coordinator's own session is never a reviewer (the interactive human approval in `mark-implementation-reviewed` is the one exception, under the default human-only policy). An executor commits, writes `work/implementation-summary-<NODE_ID>.md` and `work/reviews/<NODE_ID>/READY-<agent>.md`, and stops. Reviewers read only `specy-road review-packet <NODE_ID>` output and file verdicts with `specy-road review record`. Do not run `mark-implementation-reviewed --yes` to approve your own work; it refuses without a recorded review. Policy: `roadmap/orchestration.yaml`.

**Shared checkouts and other agents.** Several agents may be working in this checkout at once, with or without a roadmap claim, and nothing warns you. Run `specy-road session start --path <paths you will edit>` before your first edit and `specy-road session list` to see who else is live; before any git write, run `git status` and `git worktree list` and treat files you did not create as someone else's. Commit by explicit path (`git commit --only <paths>`); never `git add -A`, `git commit -a`, or a bare `git commit` — the index is shared, so a bare commit sweeps in whatever another session staged. Never `stash`, `reset --hard`, `checkout -- .`, `clean`, `rebase`, `commit --amend`, or switch branches in a tree another session may be using; do that in your own `git worktree add ../<repo>-<task>` instead — and since `do-next-available-task` and `grind-session` switch branches, run them from your own worktree whenever `session list` shows anyone else. Edit only the files your task names, and only your own section of a file others are editing (`CHANGELOG.md` above all). A plan or prompt you are given should name the commit it was written against (`base: <sha>`); if it does not, ask, and diff from that commit before starting. If a rule in this file conflicts with one from the toolkit (registry, branches, review, the shared tree), the toolkit's is the floor: stop and ask rather than relax it.

**Running many leaves:** do not hand-roll an orchestrator around `do-next-available-task`. **`specy-road grind-session`** already runs the loop — pickup → implement → optional pre-finish check → `finish-this-task` — with stable exit codes and `--json` events, and it never edits the registry itself.

```bash
specy-road grind-session --plan                 # read-only: ready/blocked leaves, dependency waves
specy-road grind-session --on-complete merge \
    --implement-mode hook --implement-cmd '<your agent command>'
```

**From an IDE agent session** (Claude Code, Cursor), drive the loop yourself with **`specy-road grind-session --step pickup`**, implement the prompt it names, then **`--step finish`**. Each step runs one phase and exits, and pickup resumes your open claim first; see the installed `specyrd-grind-session` command. Hook mode below runs in a terminal.

**Hook mode** is how an agent CLI plugs in. Each cycle runs `--implement-cmd` once with `SPECY_ROAD_NODE_ID`, `SPECY_ROAD_BRANCH`, `SPECY_ROAD_BRIEF`, `SPECY_ROAD_PROMPT` and `SPECY_ROAD_REPO_ROOT` in the environment; a non-zero exit stops the session rather than finishing a leaf that failed. Without it (`--implement-mode manual`, the default) the loop waits for a ready-signal file between cycles.

**Workers on other harnesses:** a coordinator may hand a *claimed* leaf to a session on another harness with `specy-road worker delegate <NODE_ID> --model <roster id>`; it returns at once, and `specy-road worker sync` at the start of each turn is how you learn what happened. One writer per worker: `worker handoff` before a human opens its native session, `worker reclaim` after. See `docs/orchestration-workers.md`.

**When nothing is pickable:** exit `3` is a real dependency or gate block and needs a human elsewhere. Exit `6` means this clone already holds a claim — finish it, `specy-road abort-task-pickup`, or re-run with `--resume-in-flight`. Ask about one node with **`specy-road why-blocked <NODE_ID>`**, or list what gates are holding work with **`specy-road list-gates`**. See `docs/grind-session.md`.
