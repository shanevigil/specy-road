# Workers: leaves implemented on other harnesses

## Agent quickstart

**Use this doc when:** delegating a claimed leaf to a session on another harness (`specy-road worker …`), or taking one over by hand.
**Not for:** the review gate, roster roles and hand-off files — [`orchestration.md`](orchestration.md).

**Must know without reading on:**
- Run `specy-road worker sync` at the start of every turn; `specy-road worker sync --ack` once you have acted on the events. To wait for a worker, `specy-road worker sync --wait`, never a sleep loop.
- One writer per worker (`lease.holder`): `specy-road worker handoff <W>` before a human opens the native session, `specy-road worker reclaim <W>` after. While leased to a human, `message` and `resume` fail with `WORKER_LEASED_BY_HUMAN`.
- `delegate` runs after pickup only: `specy-road worker delegate M2.3 --model claude-opus-5.5` needs the leaf's registry claim and branch.
- A `completion` event and a READY file approve nothing; the review path is unchanged. `interrupt` is unsupported on every adapter; `terminate` loses the turn.
- A worker whose wrapper died but whose harness lives is flagged `wrapper_gone_harness_alive` and still owns its leaf: `terminate` it (kills the recorded process group) before delegating again.
- Records live in `work/.workers/` (gitignored); the event log is authoritative, the transcript is evidence. With `track_worker_logs: "events"` (or `"full"`) in `roadmap/git-workflow.yaml`, each turn's end also copies the event log (and, under `full`, the raw log) to `work/worker-logs/<NODE_ID>/` in the worker's checkout, which `finish-this-task` commits with the leaf; the default `"off"` writes nothing outside `work/.workers/`.

**Read further for:**
- record fields, states and events → "The model"
- `harness`, `channels.cli` and permissions per vendor → "Roster setup"
- what `delegate` does and the command table → "The loop"
- handoff, reclaim and the intervention hook → "Handing a worker to a human"
- launch, resume and handoff commands per harness → "What each adapter supports"
- manual checks before relying on it → "Checks that need a real installation"
- the presence guard and finishing the leaf → "Working alongside sessions and the gate"

**Related:** [`orchestration.md`](orchestration.md), [`agentic-sandbox-runbook.md`](agentic-sandbox-runbook.md), [`grind-session.md`](grind-session.md), [`design-notes/v0-3-1-worker-orchestration.md`](design-notes/v0-3-1-worker-orchestration.md).

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
the **main** worktree, like presence files and review records, and gitignored
(tracked copies in `work/worker-logs/` only by opt-in, see above). The event log is authoritative for orchestration state: the
harness's transcript is evidence, the log is what the coordinator may assume.
Authoritative is not authenticated: the worker runs as the same OS user and
can write `work/.workers/` itself, so `source` and `authority` labels are
bookkeeping under a cooperative worker, not a boundary against a compromised
one. The review gate is the boundary: READY and `completed` approve nothing.

| Field | Meaning |
|---|---|
| `harness` / `model` | Which vendor CLI runs it, and which roster model it was asked for. Distinct on purpose: a Claude model under Cursor's agent is a `cursor` worker. |
| `provider_session_id` | The harness's own session/thread/chat id, once seen; what `message`, `resume` and `handoff` use. |
| `state` | `starting → running → idle` (exit 0, no new READY) or `completed` (a READY that appeared or changed during the turn, for this node, on the worker's branch — the one actually checked out — at HEAD), `failed`, `handed_off`, `terminated`. A `completed` worker still owns its leaf and its `max_workers` slot until `terminate`; only `failed` and `terminated` are closed, and a `failed` one with a native session id can be reopened by `message` / `resume` (see the command table). A `running` record whose wrapper **and** process group are gone is marked `failed` by the next `delegate` or `sync`, whichever leaf it was on. |
| `pid` / `wrapper_token` / `pgid` / `harness_pid` / `harness_start` | The wrapper, the random token in its argv, their process group (the wrapper's pid: it is a session leader), and the harness child with its start time. A pid is this worker's wrapper only when its command line carries the resolved repo root, the worker id and the token as whole arguments; a pid our user cannot signal is someone else's. The harness pid counts only with its recorded start time. All are cleared when the wrapper records the exit. |
| `last_output_at` | When the wrapper last read a stdout line from the harness, written at most every 5 s (each write takes the workers lock), and at once by the first line after a `stalled` mark, which that write clears; set to the launch time at the start of every turn, so a new turn starts a new silence. |
| `lease.holder` | The single writer: `broker` (specy-road sends turns), `human` (handed off), `native` (adopted; observe only), `none`. |
| `instruction_epoch` | +1 for every recorded human intervention. |
| `checkpoint` | Git HEAD and time at the last handoff; `reclaim` and `reconcile` diff from here. |
| `flags` | `possibly_modified_externally` (a human session returned without hook evidence), `needs_reconcile` (changes outside the touch zones, the brief changed, or the worktree is off the worker's branch), `wrapper_gone_harness_alive` (the wrapper died; the harness or its group did not — the leaf stays owned until `terminate`), `stalled` (`running` with `last_output_at` older than `policy.stall_after_seconds`, default 600: set by `sync` or `list` with one `stalled` event; the next output line clears it, a later silence raises it again, and a worker that stops running loses it). |

Events (`seq`, `type`, `source`, `authority`, `summary`, `epoch`): `started`,
`launched` (the harness process is up; detail `argv0`, `harness`, `resumed`),
`first_output` (its first stdout line), `output`, `turn_completed`,
`completion`, `error`, `message`, `resumed`, `intervention`, `handoff`,
`reclaim`, `terminated`, `adopted`, `reconcile`, `stalled` (detail `silent_seconds`, `last_output_at`, and
`last_summary`, the last event parsed from the harness), `usage` (below). Summaries are at most 500
characters; a transcript never goes in the log.

The wrapper appends one `usage` event (`worker_suggestion`) per turn end, in the same shape for every harness; a field the harness did not report is `null`, never 0, and a turn that reported nothing (a crash, `turn.failed`, `generic`) still gets one, all `null` (also a harness that could not start). Recorded lines per harness, with provenance: `tests/fixtures/worker_usage/turn_end_lines.json`.

| `usage` detail | Claude Code (`result` line) | Codex (`turn.completed.usage`) | Cursor (`result` line) |
|---|---|---|---|
| `input_tokens` / `cached_input_tokens` | all input: `input_tokens` + cache creation + cache reads (each counted when reported) / cache reads | `input_tokens` / `cached_input_tokens` (`cache_write_input_tokens` is not read) | `usage` when the line carries one (snake or camel case, read as Claude's), else `null` |
| `output_tokens` / `reasoning_tokens` | `output_tokens` / `output_tokens_details.thinking_tokens` | `output_tokens` / `reasoning_output_tokens` | as above / `null` |
| `cost_usd` / `cost_is_estimate` | this turn's: `total_cost_usd` is the session's running total, so the previous `usage` event's `session_cost_usd` is subtracted (a lower total counts whole); `true`, a client-side estimate | `null` / `null` | `null` / `null` (no cost documented) |
| `num_turns` / `harness_version` | `num_turns` / the `system/init` line's version | `null` / `null` | `num_turns` if present / `null` |

`authority` says who vouches for an event. `system` is a fact the toolkit
itself observed: the launch, the exit code, whether a new READY exists, a
wrapper found dead. `worker_suggestion` is anything parsed from the
harness's stdout — its session id line, assistant text, tool summaries, its
own `result` line — which the model controls. `orchestrator` is the
coordinator's own commands; `human_authoritative` is a recorded
intervention. A `turn_completed` is the harness's claim; the `completion`
that follows is the wrapper's.

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
    # Optional: your own command. {prompt} is the prompt file path; {session}
    # is the native session id; {session_flag} (claude-code only) is the
    # harness's own argument for it: `--session-id <id>` on launch,
    # `--resume <id>` on resume. A command that names {session} or
    # {session_flag} serves launch AND `message` / `resume` (the same line, run
    # again with the recorded id); one without either is used for launch only,
    # and resumes run the default command with the default's permissions. No
    # channels.cli: the default command (Claude: --session-id on launch,
    # --resume on resume).
    # channels:
    #   (a placeholder must be a whole argument, bare or in one pair of quotes —
    #   `--session-id={session}` and `"prefix <prompt>"` are refused; `< {prompt}` feeds the file on stdin)
    #   cli: "claude -p --output-format stream-json --verbose --permission-mode acceptEdits {session_flag} < {prompt}"
policy:
  max_workers: 2                    # each worker draws on a plan quota
```

**Cursor's CLI.** The `cursor` harness runs Cursor's agent CLI. Its binary is
`agent` (`cursor agent` runs the same; `cursor-agent` is an older alias), not
the `cursor` command, which launches the editor: a `channels.cli` or
`preflight` naming `cursor -p …` starts no agent and the worker fails with no
output to explain it. Log in once with `agent login` (a browser sign-in;
`NO_OPEN_BROWSER=1` prints the link instead), or set `CURSOR_API_KEY` on a
machine without a browser. The default command passes `--trust`: in a
workspace it has not trusted yet, which every new worktree is, `agent -p`
exits 1 asking to trust it unless given `--trust` or `--force` (checked on
agent 2026.10.22 with a fresh worktree); keep `--trust` in a `channels.cli`
that drops `--force`. Cursor's model ids carry the effort (`agent
--list-models`: `gpt-5.6-sol-high`, `claude-opus-5-5-high`); list them in the
profile's `aliases` so the prompt still carries the model notes
([orchestration-models.md](orchestration-models.md#model-profiles-models-and-prompt)).

```yaml
  - id: gpt-5.6-sol-high            # Cursor's id for GPT-5.6 Sol at high effort
    family: openai
    roles: [reviewer]
    harness: cursor
    preflight: agent status         # fails (exit 127) when `agent` is not installed
```

`agent status` prints `Not logged in` but still exits 0 when signed out (agent
2026.10.22), so it catches a missing binary, not a lapsed login; `preflight:
agent status | grep -q "Logged in"` stops on both.

**Claude and `{session}`.** Claude Code refuses `--session-id` for a session
that already exists ("Session ID … is already in use", exit 1), so a
`channels.cli` of the form `claude -p … --session-id {session} < {prompt}`
launches fine and then fails every `message` / `resume`, closing the worker as
`failed`. Use `{session_flag}` instead: it expands to `--session-id <id>` when
the worker is launched and to `--resume <id>` on every `message` / `resume`, so
one command line, with your permission flags, serves the whole leaf (the
roster example above). It is defined for `claude-code` only; on another
harness a `{session_flag}` command is refused rather than guessed. `prompt
--channel cli` has no session, so there it expands to nothing. An older
alternative is a small wrapper that resumes when the session exists:

```sh
#!/bin/sh
# claude-worker.sh <session> <prompt file>: start the session, or resume it.
sid=$1 prompt=$2
set -- -p --output-format stream-json --verbose --dangerously-skip-permissions --model claude-opus-5-5
if ls "$HOME"/.claude/projects/*/"$sid".jsonl >/dev/null 2>&1; then
  exec claude "$@" --resume "$sid" < "$prompt"
fi
exec claude "$@" --session-id "$sid" < "$prompt"
```

It looks for Claude Code's own transcript of the session (checked on Claude
Code 2.1.312; re-check after upgrading), and `exec` keeps `claude` itself as
the worker's harness process.

**Permissions in the harness's settings file.** The other way to keep a
worker's permissions across resumes is to leave the command alone and put them
where every `claude` run in the worktree reads them: `.claude/settings.json`
(committed, shared) or `.claude/settings.local.json` (yours), with
`permissions.allow` / `permissions.deny` rules and `permissions.defaultMode`.
Claude Code reads them from the working directory on launch and on resume
alike, so the default command and a custom one run under the same rules, and
a linked worktree sees the committed file once its branch has it. Command-line
flags still win over the file for that run.

**Permissions.** The Claude Code default asks for the narrowest mode that lets it edit unattended (`--permission-mode acceptEdits`; `dontAsk` is stricter but denies every tool not allow-listed), so a first worker on a new repo may stop at a shell permission — set `channels.cli` on the roster entry to the command you want (for Claude, a create-or-resume wrapper as above, or `message` breaks). The Cursor default is the opposite: `agent -p` already has write and shell tools, `--force` (alias `--yolo`) force-allows every command that is not explicitly denied, and `--trust` accepts the new worktree as a workspace, so a `cursor` worker runs everything it decides to — a malformed `channels.cli` is an error, never a silent fall-back to that default. Codex runs with `-c sandbox_mode=workspace-write -c approval_policy=never`, as config overrides because `codex exec` and `exec resume` take no `--ask-for-approval` (and `exec resume` no `--sandbox` or `-C`); run on codex-cli 0.165.0.

## The loop

```bash
specy-road worker sync                 # start of every turn: what changed (--wait: block until something does)
specy-road worker delegate M2.3 --model claude-opus-5.5
specy-road worker sync --ack           # once you have acted on the events
```

`delegate` runs **after pickup**: the leaf must hold a registry claim with a
branch (`do-next-available-task --under M2.3`). It builds the executor prompt
(`work/prompt-M2.3-executor-<model>.md`, the same text `specy-road prompt`
writes), chooses the worktree — this checkout's git root when it has the
claim's branch checked out, otherwise a linked worktree at
`work/.worktrees/<codename>`; the harness runs there, and that is the
`worktree` the record keeps —
refuses that worktree while it has uncommitted changes other than the leaf's own untracked bookkeeping (`work/brief-<ID>.md`, `work/implementation-summary-<ID>.md`, its prompts, its own `work/worker-logs/<ID>/`, and `work/reviews/`, `.workers/`, `.sessions/`, `.worktrees/`), or while `git status` cannot read it (it names
them: the worker would edit the same files, and `reconcile` could not tell its
edits from yours; commit or stash them first; nothing is written then), writes the prompt, hashes it as the
worker's `contract_hash`, launches the harness detached, and returns the worker id. Delegating the same leaf again returns
the existing worker; a launch that would exceed `max_workers` is refused (see
"What `max_workers` counts" below); `--op-id`
makes a retried call answer from its first result (an op id is bound to its
kind, target and arguments — for `message --file`, the file's text — so a
replay naming another leaf, worker or message is refused). A roster
entry's `preflight` runs first, as `prompt --channel cli` runs it. Into a
linked worktree the brief is copied too, since `work/` is gitignored and the
executor's precondition looks for it there: under the worktree's project root
(`sr/work/brief-<ID>.md` in the nested layout, where the prompt and brief name
the project root and give the summary and hand-off paths from the git root, the
directory the worker is told to work from).

**What `max_workers` counts.** `delegate`, `message` and `resume` each refuse a turn when the workers already counted reach `policy.max_workers` (a resumed worker does not count itself, so an `idle` worker resumes in its own slot). Counted are this checkout's active records (any state but `failed` and `terminated`) in `work/.workers/`, which the main checkout and all its linked worktrees share, plus every **lease ref** on the integration remote (`remote` in `roadmap/git-workflow.yaml`) whose checkout id is not this one's, read with `git ls-remote`. Each launch or resume pushes `refs/specy-road/leases/<checkout-id>/<worker-id>` (a parentless empty-tree commit naming the worker) and counts again after the push, so of two checkouts launching at once neither goes over the limit (both may be refused). `adopt` pushes one too, with no recount (the session already runs); an adopt whose lease cannot be pushed is refused and its record closed. A `delegate` whose leaf already has a worker here returns it before any remote read, so a retry is answered while the remote is down. The checkout id is a uuid written once to `<git-common-dir>/specy-road-checkout-id`: linked worktrees share it with their main checkout, and a separate clone has its own. It is written to a temporary file and hard-linked into place, so it is never seen half-written and concurrent first calls agree on one; a file that exists but holds no uuid refuses `delegate`, `message` and `resume` (never read as "no id") until it is removed, and the next of them writes a new one. Branch names and claim owners play no part: a clone's worker counts wherever its branch also exists and whoever holds the claim. The lease follows the record: kept while `idle`, `completed` or `handed_off`, deleted when the record goes `failed` or `terminated`. `worker sync` makes this checkout's lease refs match its active records: it deletes refs whose worker is no longer active here (a crashed wrapper, a delete that failed) and, best effort, pushes one for each active worker without one (registered before leases existed, launched `--offline`, a push that failed); it reads the remote first, then rechecks each record and deletes and pushes under the workers lock, the lock every launch and resume pushes its lease under, so it cannot remove a lease being acquired. A repository without that remote pushes and reads no leases. Otherwise the turn is refused, and nothing is launched, when the remote rejects the lease push (`<remote> rejected the lease for W`) or cannot be reached (`cannot reach <remote> …; retry, or pass --offline`). `--offline` on `delegate`, `message` or `resume` counts this checkout's workers only, reads and pushes no lease, and prints one warning; other checkouts then do not count that worker until a later turn without `--offline`, or the next `worker sync` that reaches the remote, pushes its lease. `--offline` is part of what an `--op-id` is bound to. Cost: a launch is one `ls-remote`, one push and one more `ls-remote`; a resume a push and an `ls-remote`; a close a push; `sync` one `ls-remote`.

**Waiting.** When there is nothing to do until a worker reports, call `specy-road worker sync --wait` rather than sleeping and re-running `sync`. Every event appended to any worker's log also replaces one file, `work/.workers/FLAG`; `--wait` stats it every 250 ms (no OS watch API) and prints the usual `sync` output as soon as it changes, or at once when an unacknowledged event is already there. After `--timeout` seconds (default 600) with nothing new it prints the empty delta and exits 2. The wait is the command itself, in the foreground: nothing runs on after it returns, and Ctrl-C ends it with exit 130 and no acknowledgement.

The worker's job is the executor's as before: implement, commit, write
`work/implementation-summary-<ID>.md` and `work/reviews/<ID>/READY-*.md`,
stop. A `completion` event says it stopped and whether READY exists; it is
**not** an approval. From there the review path is unchanged:
`review-packet`, reviewer prompts, `review record`, `handoff status`,
`mark-implementation-reviewed`, `finish-this-task`.

**Backgrounded tests.** A `completion` with exit 0 and READY missing, after a final reply saying a test or verifier run is still going in the background ("I'll be notified when it finishes"), is a lost turn: a headless turn ends when the agent replies, and nothing resumes the session when the background job finishes. The executor prompt tells the executor to run the verifier and tests in the foreground for this reason. To recover, `worker message W --text` telling the executor to rerun them in the foreground, wait for them to finish, and then complete its steps.

**Killing by pattern.** An executor clearing its own stray test run with `pkill -f "pytest -q"` also ended the coordinator's and other leaves' pytest runs (SIGTERM, no failure reported), since sessions share the machine. The executor prompt forbids kills by name or pattern and allows stopping only a process the executor started, by the pid it recorded.

| Command | Does |
|---|---|
| `list [--all]`, `status W`, `events W [--since N]`, `open W` | Read. `open` prints the worktree, the log, and the native resume command. |
| `sync [--ack] [--wait [--timeout S]]` | Every worker's events after the last acknowledged one (`work/.workers/sync.yaml`, per worker the acked `seq` and `acked_at`); compact, with state, lease, epoch and flags. A sequence number between the last acknowledged one and the record's `last_event_seq` that no readable line carries (lost or unreadable, the final event included) is reported as a gap (`! gap: event(s) #4–#5 …`; `gaps` in `--json`); a worker whose new events are all unreadable is still listed, and `--ack` moves past its gaps. `--wait` first blocks until there is something to report (see "Waiting" above); exit 2 when `--timeout` passes with nothing. |
| `message W --text\|--file` | A follow-up: resumes the native session with the text. Needs the `broker` lease and a stopped wrapper; a running one-shot turn cannot be steered. |
| `resume W` | `message` with a "continue from where you stopped" prompt. Both resume a worker in `idle`, `completed` (a review `block` goes back as a message) or `failed` **with** a `provider_session_id` (a crashed or hand-killed turn keeps its session, and is refused while another worker holds the leaf). Every resumed turn takes a `max_workers` slot like a launch: refused when the other counted workers already reach the limit. Refused: `failed` with no session id and `terminated` ("delegate again instead"), `handed_off` (`WORKER_LEASED_BY_HUMAN`), and a live process — `stalled` included, which becomes resumable once its harness exits or is stopped (the wrapper then records `failed`; `terminate` instead closes it for good). |
| `interrupt W` | **Unsupported** by every CLI adapter: exit 2 and the reason. A kill is not an interrupt; use `terminate` and say so. |
| `terminate W` | SIGTERM the recorded process group (wrapper, harness and children), SIGKILL after 5 s, and confirm the group is gone — also when the wrapper itself already died, while the harness still matches its start time and the verified wrapper or harness is still in the recorded group; state `terminated`. The turn is lost. |
| `handoff W` / `reclaim W [--note]` | Lease to a human and back; below. |
| `adopt --node ID --harness H --session SID` | Register a session the user started natively; lease `native`, observe only. Refused while the leaf has an active worker, and for an id that is not the harness's own shape (a UUID for Claude Code and Codex; shell-safe characters for all). |
| `reconcile W` | Paths changed since the checkpoint, and over the worker's whole lifetime (from the HEAD it started at), vs the leaf's touch zones — a rename or copy counts on both sides, so a `git mv` into the zone is still a change outside it; and whether the brief changed (a prompt that can no longer be built for this model counts as changed). Sets or clears `needs_reconcile`. The leaf's brief, summary and prompts, the toolkit's state under `work/`, and `roadmap/registry.yaml` never count; any other `work/` file does. |
| `timeline W\|NODE_ID` | Seconds per phase of the latest turn (a node id means its latest worker): delegated → `launched`, `launched` → `first_output`, `first_output` → turn end (`turn_completed`, `completion`, or an `error` carrying `detail.exit`, which includes a harness that could not start), end → the `sync --ack` that covered it; `unknown` when a boundary event is missing. `--json` prints the same object. |
| `usage W\|NODE_ID` | Per attempt (a node id means every worker on it): model, harness and version, `usage` events counted as turns, and each figure summed over the turns that reported it (`?` when none did; partial sums are lower bounds), then the node's total. `--json` prints the same object. To browse the timeline, usage and event log per worker instead, open the PM GUI's read-only **Workers** drawer ([pm-gui.md](pm-gui.md)). |
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

Every transition (`message`, `resume`, `handoff`, `reclaim`, `terminate`,
`adopt`, the hook) runs under the workers lock as one transaction (`delegate`
runs the roster `preflight` and the prompt build between two lock sections, so
nothing queues behind them): two
coordinators sending at once launch one turn, and a second `reclaim` finds
the lease already returned. `terminate` signals only a pid whose command line
names this worker's wrapper (resolved repo root, worker id and the spawn's
random token as whole arguments); when `ps` cannot say, it refuses rather than
signal a stranger. When the wrapper is gone, `terminate` signals the group
only while the harness pid is alive with its recorded start time; a group
with members but neither identity is refused (a group id can be reused):
kill this worker's processes in it by hand, then run `terminate` again. On an adopted (`native`) record it closes the record and
says the session was not signalled.

**Processes outside the group.** The recorded group covers the wrapper, the
harness and what the harness forks directly, not what it puts in a group of
its own. Claude Code runs each Bash-tool command in its own process group: on
SIGTERM (what `terminate` sends first) claude stops those commands itself, but
after a SIGKILL — `terminate`'s escalation after 5 s, `kill -9` of the harness
or the group, a crash — whatever the tool was running (a test suite, a server)
keeps running with ppid 1, and no `worker` command sees it. Stop workers with
`terminate` rather than `kill -9`; after any SIGKILL, list what still runs in
the worker's worktree (`lsof -d cwd | grep <worktree>`) and kill it by hand.

`reclaim` always returns the worker to `idle`, even one that was
`completed`: the coordinator re-verifies READY against the branch after a
human touched it rather than trusting the earlier completion.

The record's `last_event_seq` is repaired from the log when they disagree
(a crash between the append and the save), so sequences never repeat. On a
platform with neither `fcntl` nor `msvcrt`, worker mutations refuse rather
than run unserialised.

`handoff` refuses while the wrapper is running (wait for idle, or
`terminate`), takes a checkpoint, sets the lease to `human`, and prints the
harness's own resume command. While the lease is `human`, `message` and
`resume` fail with `WORKER_LEASED_BY_HUMAN`; the coordinator sees the lease in
`sync`. `reclaim` diffs the worktree from the checkpoint, reads any prompts
the hook recorded, moves the record in one write (epoch +1, lease back,
state `idle`), then writes **one** `intervention` event
(`authority: human_authoritative`) with the prompts and the diff stat; a
reclaim that crashed between the two is repaired by the next call, never
counted twice. `resume`, `message`, `reclaim` and the completion check all
refuse (or ignore the READY, with an `error` event saying why) when the
worktree no longer has the worker's branch checked out: check it out again,
or `terminate`. Without hook evidence the worker is flagged
`possibly_modified_externally`: specy-road does not pretend to know what was
said. Precedence when a human direction conflicts with the leaf's contract:
hard constraints (touch zones, dependencies, the gate) → an explicit
amendment the human confirms in the coordinator chat → the human's direction
→ the coordinator's plan → the worker's own ideas. `reconcile` is how the
coordinator checks; `needs_reconcile` is the state that waits for the human.

### The intervention hook

The harness's project-level prompt-submit hook fires in the human's resumed
session too. `specy-road worker hook` is its body: it reads the payload,
matches the harness **and** session id to a worker **whose lease is
`human`** (the broker's own prompts are not interventions; two harnesses
handing out the same id is refused as ambiguous), appends the prompt to
`<id>.interventions.jsonl`, and exits 0. It never blocks a prompt, and it
never waits more than two seconds for the workers lock: a busy lock means no
witness for that prompt, which `reclaim` then reports as missing evidence. `reclaim`
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
| `claude-code` | `claude -p --output-format stream-json --verbose --session-id <uuid> --model … --permission-mode acceptEdits` (prompt on stdin: a brief can exceed Linux's 128 KiB per-argument limit). In a **linked** worktree the default also passes `--add-dir` pointing at the main checkout's `work/reviews/<ID>/` so the executor can write its READY hand-off under `acceptEdits`. | chosen up front | `claude -p --resume <id> …` | unsupported | `claude --resume <id>` |
| `codex` | `codex exec --json -m … -c sandbox_mode=workspace-write -c approval_policy=never -C <worktree> -` (prompt on stdin). The harness runs in the worktree; write READY under the main checkout's `work/reviews/<ID>/` (same path `reviews_root` resolves to from any linked worktree). | `thread.started` | `codex exec resume --json -c sandbox_mode=workspace-write -c approval_policy=never <id> -` (same policy, run in the worktree, prompt on stdin) | unsupported | `codex resume <id>` |
| `cursor` | `agent -p --output-format stream-json --force --trust --model … --workspace <worktree> "<prompt>"`. The agent's workspace is the linked worktree; READY still belongs in the main checkout's `work/reviews/<ID>/` (open or copy that path explicitly if the harness cannot reach it). | first event | `agent -p --resume <id> … --force --trust …` (print-mode resume with a new prompt is undocumented; verify on your install; the prompt is an argument, so a launch whose arguments exceed **100 KiB** is refused with the reason and the record marked `failed`) | unsupported | `agent --resume <id>` |
| `generic` | `channels.cli` / profile `access.cli` with `{prompt}` (the prompt file path) or `<prompt>` (the prompt text, as the shipped profiles write it; the same 100 KiB argument limit applies) | none | unsupported | unsupported | none |

Whatever the harness, the wrapper's own command line carries only the repo
root, the worker id, a token and the path of a mode-0600 launch file under
`work/.workers/` (argv and the stdin prompt), which the wrapper reads once
and deletes; a brief of any size reaches a stdin-reading harness.

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
record closes and the slot frees. With `--on-complete merge`, finish merges
into the integration branch and **pushes that branch** (after stating how many
local integration commits are not on the remote yet); `--push` only pushes
the feature branch. From a linked worktree with
`on_complete: merge`, finish cannot check the integration branch out while
the coordinator's checkout holds it, so it merges and pushes **in that
checkout** instead. That checkout must have no uncommitted changes to tracked
files (untracked files are fine): otherwise finish refuses before its
bookkeeping commit and names the checkout to commit or stash in.
