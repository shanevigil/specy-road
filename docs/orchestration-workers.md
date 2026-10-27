# Workers: leaves implemented on other harnesses

`specy-road worker` lets the coordinator — the model in whatever IDE chat you
are already in — hand a roadmap leaf to a session on another harness, keep
talking to you while it runs, and find out what happened at the start of its
next turn. It is the delegation layer under
[orchestration.md](orchestration.md): the review gate, hand-off files, and
roster are unchanged; this adds the launching, watching, and taking-back.

Design: [design-notes/v0-3-1-worker-orchestration.md](design-notes/v0-3-1-worker-orchestration.md).
Three decisions shape everything here: the surface is the CLI (every harness
can run a shell; there is no MCP server); workers run on each vendor's
documented one-shot CLI with resume; and there is no daemon — a detached
wrapper process per worker writes files that the commands read.

## The model

A **worker** is one leaf, one session, one harness. Its record lives at
`work/.workers/<id>.yaml` (`w-0001`, …) beside an append-only event log
`<id>.events.jsonl`, a raw output log `<id>.log`, and an ops outbox; all in
the **main** worktree, like presence files and review records, and
gitignored. The event log is authoritative for orchestration state: the
harness's transcript is evidence, the log is what the coordinator may assume.

| Field | Meaning |
|---|---|
| `harness` / `model` | Which vendor CLI runs it, and which roster model it was asked for. Distinct on purpose: a Claude model under Cursor's agent is a `cursor` worker. |
| `provider_session_id` | The harness's own session/thread/chat id, once seen; what `message`, `resume` and `handoff` use. |
| `state` | `starting → running → idle` (exit 0, no READY file) or `completed` (READY present), `failed`, `handed_off`, `terminated`. |
| `lease.holder` | The single writer: `broker` (specy-road sends turns), `human` (handed off), `native` (adopted; observe only), `none`. |
| `instruction_epoch` | +1 for every recorded human intervention. |
| `checkpoint` | Git HEAD and time at the last handoff; `reclaim` and `reconcile` diff from here. |
| `flags` | `possibly_modified_externally` (a human session returned without hook evidence), `needs_reconcile` (changes outside the touch zones, or the brief changed). |

Events (`seq`, `type`, `source`, `authority`, `summary`, `epoch`): `started`,
`output`, `turn_completed`, `completion`, `error`, `message`, `resumed`,
`intervention`, `handoff`, `reclaim`, `terminated`, `adopted`, `reconcile`.
Summaries are at most 500 characters; a transcript never goes in the log.

## Roster setup

A roster entry names its harness; `delegate` refuses a model without the
executor role, outside its availability, or that may not process the leaf's
sensitivity (the same rules as `orchestrate plan`).

```yaml
roster:
  - id: claude-opus-5.5
    family: anthropic
    roles: [executor, reviewer]
    harness: claude-code            # claude-code | codex | cursor | generic
    billing_route: claude_subscription   # a label, recorded on the worker
    # Optional: your own launch command. {prompt} is the prompt file path;
    # {session} is the native session id and makes the same command serve
    # `message` / `resume`. Without it, the default command is used.
    # channels:
    #   cli: "claude -p --output-format stream-json --verbose --dangerously-skip-permissions --session-id {session} \"$(cat {prompt})\""
policy:
  max_workers: 2                    # each worker draws on a plan quota
```

**Permissions.** The Claude Code default asks for the narrowest unattended mode it documents (`--permission-mode acceptEdits`), so a first worker on a new repo may stop at a shell permission — set `channels.cli` on the roster entry to the command you want. The Cursor default is the opposite: `agent -p` applies no change without `--force`, and `--force` is Cursor's full auto-run (alias `--yolo`), so a `cursor` worker runs everything it decides to. Codex runs in `--sandbox workspace-write --ask-for-approval never`; that flag pair is in OpenAI's reference but was not run here.

## The loop

```bash
specy-road worker sync                 # start of every turn: what changed
specy-road worker delegate M2.3 --model claude-opus-5.5
specy-road worker sync --ack           # once you have acted on the events
```

`delegate` runs **after pickup**: the leaf must hold a registry claim with a
branch (`do-next-available-task --under M2.3`). It writes the executor prompt
(`work/prompt-M2.3-executor-<model>.md`, the same text `specy-road prompt`
writes), chooses the worktree — this checkout when it has the claim's branch
checked out, otherwise a linked worktree at `work/.worktrees/<codename>` —
hashes the prompt as the worker's `contract_hash`, launches the harness
detached, and returns the worker id. Delegating the same leaf again returns
the existing worker; more than `max_workers` active is refused; `--op-id`
makes a retried call answer from its first result (an op id is bound to its
kind and target: a replay naming another leaf or worker is refused). A roster
entry's `preflight` runs first, as `prompt --channel cli` runs it. Into a
linked worktree the brief is copied too, since `work/` is gitignored and the
executor's precondition looks for it there.

The worker's job is the executor's as before: implement, commit, write
`work/implementation-summary-<ID>.md` and `work/reviews/<ID>/READY-*.md`,
stop. A `completion` event says it stopped and whether READY exists; it is
**not** an approval. From there the review path is unchanged:
`review-packet`, reviewer prompts, `review record`, `handoff status`,
`mark-implementation-reviewed`, `finish-this-task`.

| Command | Does |
|---|---|
| `list [--all]`, `status W`, `events W [--since N]`, `open W` | Read. `open` prints the worktree, the log, and the native resume command. |
| `sync [--ack]` | Every worker's events after the last acknowledged one (`work/.workers/sync.yaml`); compact, with state, lease, epoch and flags. |
| `message W --text\|--file` | A follow-up: resumes the native session with the text. Needs the `broker` lease and a stopped wrapper; a running one-shot turn cannot be steered. |
| `resume W` | `message` with a "continue from where you stopped" prompt. Both work on `idle` **and** `completed` workers (a review `block` goes back as a message); only `failed` and `terminated` are closed. |
| `interrupt W` | **Unsupported** by every CLI adapter: exit 2 and the reason. A kill is not an interrupt; use `terminate` and say so. |
| `terminate W` | SIGTERM the wrapper's process group (harness and children); state `terminated`. The turn is lost. |
| `handoff W` / `reclaim W [--note]` | Lease to a human and back; below. |
| `adopt --node ID --harness H --session SID` | Register a session the user started natively; lease `native`, observe only. Refused while the leaf has an active worker. |
| `reconcile W` | Paths changed since the checkpoint vs the leaf's touch zones, and whether the brief changed (a prompt that can no longer be built for this model counts as changed); sets or clears `needs_reconcile`. |
| `hook --format H [--print-config]` | The prompt-submit hook body; below. |

## Handing a worker to a human

No local harness documents two writers on one session: Claude Code warns
that resuming a session in two places interleaves messages, Codex has no
attach to a UI-owned thread, Cursor's SDK none at all. So a human takes a
worker over by **handoff**, and gives it back by **reclaim**:

```bash
specy-road worker handoff w-0003
#   w-0003: leased to you (epoch 0). In /…/work/.worktrees/payments run:
#     claude --resume 7f1c…
#   Then `specy-road worker reclaim w-0003` when you are done.
```

`handoff` refuses while the wrapper is running (wait for idle, or
`terminate`), takes a checkpoint, sets the lease to `human`, and prints the
harness's own resume command. While the lease is `human`, `message` and
`resume` fail with `WORKER_LEASED_BY_HUMAN`; the coordinator sees the lease in
`sync`. `reclaim` diffs the worktree from the checkpoint, reads any prompts
the hook recorded, writes **one** `intervention` event
(`authority: human_authoritative`, epoch +1) with the prompts and the diff
stat, and returns the lease. Without hook evidence the worker is flagged
`possibly_modified_externally`: specy-road does not pretend to know what was
said. Precedence when a human direction conflicts with the leaf's contract:
hard constraints (touch zones, dependencies, the gate) → an explicit
amendment the human confirms in the coordinator chat → the human's direction
→ the coordinator's plan → the worker's own ideas. `reconcile` is how the
coordinator checks; `needs_reconcile` is the state that waits for the human.

### The intervention hook

The harness's project-level prompt-submit hook fires in the human's resumed
session too. `specy-road worker hook` is its body: it reads the payload,
matches the session id to a worker **whose lease is `human`** (the broker's
own prompts are not interventions), appends the prompt to
`<id>.interventions.jsonl`, and exits 0. It never blocks a prompt. `reclaim`
reads the lines appended since the hand-off, not the timestamps.

```bash
specy-road worker hook --format claude-code --print-config   # .claude/settings.json
specy-road worker hook --format codex --print-config         # .codex/hooks.json
specy-road worker hook --format cursor --print-config        # .cursor/hooks.json
```

Claude Code and Codex `UserPromptSubmit` carry `session_id` and `prompt`;
Cursor `beforeSubmitPrompt` carries `conversation_id` and `prompt` and gets
`{"continue": true}` back. Codex hooks need the project's `.codex/` layer and
the hook trusted. Whether `UserPromptSubmit` fires for the prompt of a
`claude -p` run itself is unverified; it fires for a human's interactive
session, which is the case the hook exists for.

## What each adapter supports

| Harness | Launch | Session id | Resume (`message`) | Interrupt / steer | Handoff command |
|---|---|---|---|---|---|
| `claude-code` | `claude -p --output-format stream-json --verbose --session-id <uuid> --model … --permission-mode acceptEdits` (prompt on stdin: a brief can exceed Linux's 128 KiB per-argument limit) | chosen up front | `claude -p --resume <id> …` | unsupported | `claude --resume <id>` |
| `codex` | `codex exec --json -m … --sandbox workspace-write --ask-for-approval never -C <worktree> -` (prompt on stdin) | `thread.started` | `codex exec resume --json --sandbox workspace-write --ask-for-approval never -C <worktree> <id> -` (same flags, prompt on stdin) | unsupported | `codex resume <id>` |
| `cursor` | `agent -p --output-format stream-json --force --model … --workspace <worktree> "<prompt>"` | first event | `agent -p --resume <id> …` (print-mode resume with a new prompt is undocumented; verify on your install; the prompt is an argument, so keep Cursor briefs under 128 KiB on Linux) | unsupported | `agent --resume <id>` |
| `generic` | `channels.cli` / profile `access.cli` with `{prompt}` (the prompt file path) or `<prompt>` (the prompt text, as the shipped profiles write it) | none | unsupported | unsupported | none |

Flags were verified against each vendor's documentation on 2026-10-27 and
will drift; `tests/test_worker_adapters.py` pins the command shapes. The
long-lived protocols (Codex app-server, Cursor ACP, Claude Agent SDK) are
what would add interrupt and steer; they are later adapters behind the same
interface, not emulated here.

## Checks that need a real installation

None of these is claimed by the test suite; run them before relying on the
feature in your own setup.

1. **Permission stop.** Delegate a trivial leaf on each harness you use with
   the default command. Pass: the worker reaches `completion` or stops at a
   named permission in `<id>.log` that `channels.cli` then resolves.
2. **Double-open.** Delegate on Claude Code, wait for `idle`, then
   `claude --resume <id>` *without* `handoff` while sending `worker message`.
   Expect interleaving — that is the failure the lease prevents. Pass: with
   `handoff`, `message` is refused until `reclaim`.
3. **Hook witness.** Hand off, send two prompts in the native session,
   reclaim. Pass: the `intervention` event lists both prompts verbatim and the
   worker is not flagged `possibly_modified_externally`.
4. **Quota.** Note which plan or API key a `-p` / `exec` worker draws from on
   your subscription; record it as `billing_route`.
5. **Cursor resume.** `worker message` on a `cursor` worker. Pass: the
   resumed run carries the same `session_id`; if not, set `channels.cli` with
   `{session}` to a command that works, or treat Cursor workers as one-shot.

## Working alongside sessions and the gate

`handoff status` prints active workers beside live sessions. A worker in a
linked worktree does not touch the coordinator's branch; one in the same
checkout (the claim's branch was checked out here) does, so the coordinator
must not edit files in that leaf's touch zones while the worker runs — the
presence guard (`session guard`) already refuses the git operations that
would collide. Finishing the leaf is still `finish-this-task` from the
leaf's branch after the gate; `terminate` the idle worker afterwards so its
record closes and the slot frees.
