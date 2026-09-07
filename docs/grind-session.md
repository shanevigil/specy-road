# Agent-driven loop: `specy-road grind-session`

`grind-session` orchestrates the **task loop** over many leaves so a human or a
coding agent does not have to re-invoke pickup/finish by hand. It also exposes a
**read-only planner** (`--plan`) that tells an orchestrator what is ready, what
is blocked, and how work parallelizes — so sub-agent orchestration can dispatch
independent work safely and skip waves whose dependencies are not met yet.

> **It orchestrates approved commands — it does not implement code and never
> edits `roadmap/registry.yaml` itself.** Every cycle shells out to
> `specy-road do-next-available-task` and `specy-road finish-this-task`. Use the
> approved commands; do not hand-edit the registry. See
> [dev-workflow.md](dev-workflow.md) for the underlying primitives.

## When to use it

| Goal | Use |
| --- | --- |
| Plan sub-agent batches / see what is ready vs blocked | `grind-session --plan [--json]` |
| One agent grinds many leaves autonomously | `grind-session --implement-mode hook --implement-cmd …` |
| A human drives the loop, implementing between cycles | `grind-session` (manual mode, default) |
| One integration PR for a whole milestone subtree | `start-milestone-session` + `--milestone-subtree` (see dev-workflow.md) |

The loop lands each finished leaf on the integration branch, so run it with
**`--on-complete merge`** (or `auto`). `pr` mode does not merge between cycles,
so downstream dependencies stay blocked and the loop cannot continue
autonomously — use `--plan` + per-leaf runs instead.

**This is enforced, not just advised.** `grind-session` resolves the effective
mode before the first pickup and exits 1 if it is `pr` — including the case
where nothing declared a mode at all and `pr` came from the built-in default.
Set it once in `roadmap/git-workflow.yaml` (`on_complete: merge`) or pass
`--on-complete merge` per run. `--plan` is read-only and always allowed.

---

## Planner first: `--plan`

```bash
specy-road grind-session --plan --json            # machine-readable
specy-road grind-session --plan                   # human-readable report
specy-road grind-session --plan --under M10       # scope to a subtree
```

`--plan` is **read-only**: it reads the local roadmap + registry and prints a
classification plus a dependency **wave** layout. No git, no pickup.

### What the planner reports

- **`ready`** — leaves whose dependencies are satisfied and that are unclaimed.
  This is exactly the set/order `do-next-available-task` would claim.
- **`blocked`** — leaves with unmet effective dependencies. Each entry has
  `waiting_on` (the blocking node **display ids**) and a `reason`:
  `dependency` (waiting on other work) or `gate` (waiting on a human `type: gate`).
- **`active`** — leaves already claimed in the registry or marked *In Progress*
  (in flight; do **not** re-dispatch).
- **`waves`** — all schedulable leaves layered by dependency depth. Wave `k`
  unlocks only when **every** leaf in waves `< k` is `Complete`.
- **`parallel_batches`** — per wave, the ready+unclaimed leaves you can dispatch
  **in parallel right now**, in the order pickup will claim them (the same order
  as `ready`). `waves` stay sorted by id, because they are the dependency
  layering you read rather than a dispatch order.
- **`gated`** / **`gates_open`** — leaves stuck behind an open human gate, and
  the gate ids that need a PM decision.

### Orchestration pattern (sub-agents)

The planner is designed so a parent agent can parallelize without trial and
error. A worked example — `M10.3, M10.4` are ready, `M10.5` depends on both, and
`M11.1` depends on `M10.5`:

```text
## Suggested sub-agent batches

**Dispatch now (parallel, in pickup order):** M10.3, M10.4  — 2 independent leaf/leaves, all dependencies satisfied, listed in the order the loop will claim them.

**Later waves (do NOT start until every leaf in the prior wave is Complete):**
- wave 1: M10.5
- wave 2: M11.1
```

Recommended orchestration prompt:

> Run `specy-road grind-session --plan --json`. Spawn one sub-agent per node in
> `parallel_batches[0]` (they are independent — run them concurrently). Do **not**
> start any node in a later wave until every node in the previous wave is
> `Complete`. Re-run the planner after each wave to pick up the next batch.
> Never start a node listed under `blocked`/`gated`; gates require a human.

This is the fix for the common failure where an orchestrator spawns a sub-agent
for `M11.1` while `M10.5` is still in flight: the planner shows `M11.1` in a
later wave and under `blocked` with `waiting_on: ["M10.5"]`, so it is not
dispatched until `M10.5` completes.

### `--plan --json` shape

```json
{
  "event": "plan",
  "ts": "2026-09-06T12:00:00Z",
  "under": null,
  "ready": ["M10.3", "M10.4"],
  "blocked": [
    {"node_id": "M10.5", "codename": "…", "waiting_on": ["M10.3", "M10.4"], "reason": "dependency"},
    {"node_id": "M11.1", "codename": "…", "waiting_on": ["M10.5"], "reason": "dependency"}
  ],
  "active": [],
  "closed": ["M10.1", "M10.2"],
  "gated": [],
  "gates_open": [],
  "needs_codename": [],
  "waves": [
    {"index": 0, "node_ids": ["M10.3", "M10.4"]},
    {"index": 1, "node_ids": ["M10.5"]},
    {"index": 2, "node_ids": ["M11.1"]}
  ],
  "parallel_batches": [["M10.3", "M10.4"]],
  "totals": {"ready": 2, "blocked": 2, "active": 0, "closed": 2, "gated": 0, "gates_open": 0, "needs_codename": 0, "waves": 3}
}
```

---

## The loop

Each cycle:

```mermaid
flowchart LR
  plan[compute plan] --> ready{ready leaf?}
  ready -- no --> blocked[own claim? -> resume or exit 6\nblocked? -> exit 3\nelse no work -> exit 0/2]
  ready -- yes --> pickup[do-next-available-task]
  pickup --> impl[implement: manual signal | hook cmd]
  impl --> pre[pre-finish-cmd?]
  pre --> finish[finish-this-task]
  finish --> stop{stop condition?}
  stop -- no --> plan
  stop -- yes --> tidy[checkout integration branch\n+ optional branch cleanup]
  tidy --> done[exit 0]
```

Before each pickup the planner re-runs, so the loop **stops at blocked work and
gates instead of failing a pickup**: if nothing is ready but leaves are blocked
(dependency or gate), it stops with exit code `3`.

### Blocked, or just already busy?

Running out of ready leaves has two very different causes, reported separately.
An **open claim of your own** — you picked a leaf up and never finished it — is
exit `6` and an `in_flight` event naming the node and its branch:

```text
[grind-session] in_flight: nothing pickable — this worktree already holds a claim on M1.3.2 (feature/rm-tradelog-rest-complete).
  finish it (specy-road finish-this-task), release it (specy-road abort-task-pickup), or re-run with --resume-in-flight.
```

A **dependency or gate block** is exit `3`, and genuinely needs a human to go
and complete something else first.

The two are checked in that order, and the order matters: they are not mutually
exclusive. Every leaf downstream of your in-flight one is blocked *on it*, so in
a normal grind both buckets are non-empty when the loop stops, and only the claim
tells you what to do next.

**`--resume-in-flight`** turns the first case into a resumed cycle: the branch is
checked out, the brief and prompt are restored if they went missing, and the leaf
goes straight to implement and finish without a second pickup. Only claims
registered to a branch that **exists in this clone** qualify — a claim held by
another lane reaches `active` through the shared registry or an *In Progress*
status, and resuming one would put two implementers on the same node.

### Asking about one node (`why-blocked`, `list-gates`)

`--plan` answers for the whole session; these two answer narrower questions
without rendering the plan and reading it back.

**`specy-road why-blocked <NODE_ID>`** explains why one node is not pickable.
Unlike the plan's `waiting_on`, which lists only immediate dependencies, it walks
the chain **transitively** — the item actually worth working is usually two or
three hops down — and covers the reasons that are not dependencies at all: an
open gate, an existing claim (naming the branch holding it), a container node
that is never picked up directly, or a missing codename.

```text
M2.4 is waiting on 1 unmet dependency/dependencies.

waiting on:
  - M2.3 [Not Started] Ledger export
    - M2.1 [In Progress] Trade log REST — claimed on feature/rm-tradelog-rest
```

It exits `1` when the node really is blocked or gated, `0` when it is pickable or
already closed, and `2` for an unknown id, so a supervisor can branch on the
answer without parsing prose. `--json` returns the same structure.

**`specy-road list-gates`** lists gate nodes that are not `Complete` and what each
blocks. `--under <NODE_ID>` scopes by the **work being blocked**, not by where the
gate is defined, because a phase is routinely held by a gate defined elsewhere.

### Implement modes

- **`manual`** (default): after pickup the loop waits for a *ready signal*. Create
  the signal file (`--ready-signal`, default `work/.session-ready`) — or press
  Enter on a TTY — once implementation is done. Best for a human in the loop.
- **`hook`**: runs `--implement-cmd` per cycle (autonomous). The command receives
  env vars: `SPECY_ROAD_NODE_ID`, `SPECY_ROAD_BRANCH`, `SPECY_ROAD_BRIEF`,
  `SPECY_ROAD_PROMPT`, `SPECY_ROAD_REPO_ROOT`. A non-zero exit stops the session.

### Pre-finish hook

`--pre-finish-cmd "make test && specy-road validate"` runs after implementation,
before `finish-this-task`. A non-zero exit stops the session (exit `4`) and leaves
the feature branch intact so you can fix and resume.

### Running Claude as the implementer

Claude Code is a valid `--implement-cmd`, with one wrinkle no other agent has: a
Claude account hits **timed session limits**, and the hook then exits non-zero
through no fault of the implementation. An overnight grind should not end there,
so when the command is the Claude CLI the loop reads its output, waits for the
stated reset, and resumes **the same Claude session**:

```bash
specy-road grind-session --until M7.6 --on-complete merge --json \
  --implement-mode hook \
  --implement-cmd 'claude -p --permission-mode acceptEdits "$(cat "$SPECY_ROAD_PROMPT")"'
```

Detection is by the command itself — the first word must be `claude`. Cursor and
every other agent keep today's behaviour exactly: one run, and a non-zero exit
stops the session.

What the loop will and will not wait for:

| Claude said | grind-session does |
| --- | --- |
| a limit with a reset time | emits `usage_limited`, waits until it lifts (plus two minutes), resumes the session |
| a spend limit | stops — no reset time exists to wait for |
| a limit it cannot parse | stops **loudly**, saying the output format may have changed |
| nothing at all, on a signal-shaped exit | emits `implementer_vanished`, re-runs the command after a short backoff — a fresh run, never a `--resume`, because there is no session id to trust |
| anything else non-zero | stops as it always has |

That second-to-last row is deliberately narrow: it needs **both** empty output
**and** a signal-shaped exit code (negative, or 128+). A task that fails and
explains itself still stops the run on the first attempt. What it catches is
something outside the run killing the process — an OOM kill, a machine that
slept, a closed terminal.

Your own flags are passed through untouched. The loop splices `--resume <id>` in
behind the executable and copies the rest of your command byte for byte, so a
`"$(cat "$SPECY_ROAD_PROMPT")"` is re-evaluated on the resumed attempt — the
prompt file is still on disk, because `finish-this-task` has not run. It never
adds `--dangerously-skip-permissions`.

Bounds — CLI flag wins over `roadmap/git-workflow.yaml`, which wins over the
default:

| Bound | CLI flag | `roadmap/git-workflow.yaml` | Default |
| --- | --- | --- | --- |
| waits per leaf | `--max-limit-waits N` | `grind_session_max_limit_waits` | 3 |
| ceiling on any one wait | `--max-limit-wait-hours H` | `grind_session_max_limit_wait_hours` | 6 |
| grace after the stated reset | `--limit-wait-grace-seconds S` | `grind_session_limit_wait_grace_seconds` | 120 |
| re-runs when it dies silently | `--max-empty-retries N` | `grind_session_max_empty_retries` | 2 |

If your plan's limit resets on an **8-hour** cadence, the 6h default ceiling
stops the run rather than waiting the extra two hours. Pass
`--max-limit-wait-hours 9`.

**Run it in a terminal, not in an IDE agent pane.** An unattended grind needs a
process that can be waited on and resumed; a chat panel cannot be. The machine
also has to stay awake for the wait — use `caffeinate`, and `tmux` if you detach.

If you are on Claude Code 2.1.234 or later with *"Continue automatically at usage
limit"* enabled, Claude may ride out the limit itself and exit 0. That is fine:
the loop treats a zero exit as success and does not resume a second time.

### Ending the session

A session that stops on its own terms — a bound reached, or no work left — ends by
checking out the **integration branch**. `finish-this-task` deliberately leaves you
on the feature branch, which is right for one task by hand and wrong for a loop that
merged a dozen.

`--delete-merged-branches` also deletes the `feature/rm-*` branches the session
finished: locally with `git branch -d`, and on the remote too when `--push` was
given. A branch is deleted only if the integration branch already contains it, so a
leaf that fell back to a PR keeps its branch. Without the flag the loop prints the
exact command instead.

Nothing here changes the exit code, and none of it runs after a failed cycle — a
failure leaves the feature branch exactly as it was so you can fix and resume.

### Requirements for autonomous (hook) runs

For an unattended loop to keep cycling:

- **Leave a clean working tree.** Your `--implement-cmd` (and `--pre-finish-cmd`)
  must **commit** their changes and not leave untracked/uncommitted files — the
  next pickup refuses to run on a dirty tree. Gitignore build artifacts (e.g.
  `__pycache__/`, coverage files) so tools you run in the pre-finish hook do not
  dirty the tree.
- **Land work on the integration branch each cycle** with `--on-complete merge`
  (or `auto`). With `pr`, the just-finished work never reaches the integration
  branch, so the next cycle re-evaluates the same state and downstream stays
  blocked.
- **Implementation review gate.** If `roadmap/git-workflow.yaml` sets
  `require_implementation_review_before_finish: true`, `finish-this-task` requires
  a recorded review. For a fully autonomous loop either set it to `false`, or have
  your `--implement-cmd` write `work/implementation-summary-<NODE_ID>.md` and run
  `specy-road mark-implementation-reviewed --yes` before the loop calls finish.

### Examples

```bash
# Autonomous: implement each leaf under M7 with an agent CLI, gate on tests,
# land per-leaf merges, stop after finishing M7.6 (machine-readable events).
specy-road grind-session \
  --under M7 --until M7.6 --on-complete merge --json \
  --implement-mode hook --implement-cmd 'my-agent --prompt "$SPECY_ROAD_PROMPT"' \
  --pre-finish-cmd 'make test && specy-road validate'

# Human-in-the-loop: pick one leaf, implement, then `touch work/.session-ready`.
specy-road grind-session --max-leaves 1 --on-complete merge
```

---

## Stop conditions

| Flag | Stops when |
| --- | --- |
| `--until NODE_ID` | that node has been finished (inclusive) |
| `--max-leaves N` | N leaves have been finished this session |
| `--under NODE_ID` | only leaves under `NODE_ID` are considered — a parent scopes to its subtree, a leaf id targets exactly that leaf |
| `--max-cycles N` | safety bound on iterations (default 100) |
| *(default)* | no actionable leaves remain |

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Ended normally (bound reached, or no actionable work left) |
| `1` | Generic failure — implement hook or `finish-this-task` failed, or the resolved `on_complete` was `pr` and the loop refused to start |
| `2` | No actionable leaves at start |
| `3` | Blocked on a dependency or gate — human action required |
| `4` | `--pre-finish-cmd` failed |
| `5` | Pickup (`do-next-available-task`) register/commit/git failed |
| `6` | Nothing pickable because **this worktree already holds a claim** |

## JSON events (`--json`)

One JSON object per line. `event` is one of: `plan`, `picked`, `resumed`,
`implementing`, `pre_finish`, `finished`, `blocked`, `in_flight`, `hook_failed`,
`stopped`, `cleanup`, `usage_limited`, `implementer_vanished`. Every event carries
`ts`, UTC to the second, right after `event`.

**stdout is only JSON.** In `--json` mode the sub-commands' own output — the pickup
banner, the finish log, git — is redirected to **stderr**, so the stream stays
parseable as JSONL. Redirect stderr to a file if you want to keep it.

```json
{"event":"picked","ts":"2026-09-06T12:00:04Z","node_id":"M10.2","branch":"feature/rm-vault-mcp-secrets","brief":"work/brief-M10.2.md","prompt":"work/prompt-M10.2.md"}
{"event":"finished","ts":"2026-09-06T12:31:18Z","node_id":"M10.2"}
{"event":"blocked","ts":"2026-09-06T12:31:20Z","reason":"dependency","waiting_on":["M10.5"],"count":1,"node_id":"M11.1"}
{"event":"in_flight","ts":"2026-09-06T12:31:20Z","node_id":"M1.3.2","codename":"tradelog-rest-complete","branch":"feature/rm-tradelog-rest-complete","count":1,"others":[]}
{"event":"stopped","ts":"2026-09-06T12:31:20Z","reason":"until_reached","node_id":"M11.6"}
{"event":"usage_limited","ts":"2026-09-06T12:10:05Z","node_id":"M10.2","reset_at":"2026-09-06T23:20:00Z","wait_seconds":40620,"attempt":1}
{"event":"implementer_vanished","ts":"2026-09-06T12:12:00Z","node_id":"M10.2","rc":137,"attempt":1,"max_retries":2,"retry_in_seconds":30}
{"event":"cleanup","ts":"2026-09-06T12:31:22Z","integration_branch":"dev","remote":"origin","checked_out":true,"deleted_local":["feature/rm-vault-mcp-secrets"],"deleted_remote":["feature/rm-vault-mcp-secrets"],"failed":[],"warnings":[],"hint":null}
```

---

## Registry / pre-commit (yamllint) compatibility

Unattended pickup commits `roadmap/registry.yaml` on the integration branch.
specy-road writes that file **yamllint-clean** (block sequences indented), so a
default `yamllint` pre-commit hook does not break the loop. A recommended
consumer `.yamllint`:

```yaml
extends: default
rules:
  document-start: disable   # specy-road files omit the '---' marker
  line-length: disable      # touch zones / paths can be long
```

If you add other YAML to the same hook, keep `roadmap/registry.yaml` writes going
through `specy-road` (do not hand-edit) so the indentation stays consistent.

---

## Relationship to milestone sessions

- **`grind-session`** drives the *per-leaf* loop (each leaf lands on integration
  via `on_complete`), and `--plan` helps you parallelize across leaves.
- **`start-milestone-session` + `--milestone-subtree`** collects a whole subtree
  onto one rollup branch for a *single* integration PR. Use that when you want one
  PR per milestone instead of per leaf. `grind-session --milestone-subtree` passes
  the flag through to pickup. See [dev-workflow.md](dev-workflow.md#milestone-scoped-execution-rollup-branch).
