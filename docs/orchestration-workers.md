# Workers: leaves implemented on other harnesses

## Agent quickstart

**Use this doc when:** delegating a claimed leaf to a session on another harness (`specy-road worker …`), or taking one over by hand.
**Not for:** the review gate, roster roles and hand-off files — [`orchestration.md`](orchestration.md).

**Must know without reading on:**
- Run `specy-road worker sync` at the start of every turn; `specy-road worker sync --ack` once you have acted on the events. To wait for a worker, `specy-road worker sync --wait` (see [orchestration-worker-sync.md](orchestration-worker-sync.md) for `--until` and compact output), never a sleep loop.
- One writer per worker (`lease.holder`): `specy-road worker handoff <W>` before a human opens the native session, `specy-road worker reclaim <W>` after. While leased to a human, `message` and `resume` fail with `WORKER_LEASED_BY_HUMAN`.
- `delegate` runs after pickup only: `specy-road worker delegate M2.3 --model claude-opus-5-5` needs the leaf's registry claim and branch. Work outside the roadmap runs as a chore instead: [`orchestration-chores.md`](orchestration-chores.md).
- A `completion` event and a READY file approve nothing; the review path is unchanged. `interrupt` is unsupported on every adapter; `terminate` loses the turn.
- A worker whose wrapper died but whose harness lives is flagged `wrapper_gone_harness_alive` and still owns its leaf: `terminate` it (kills the recorded process group) before delegating again. To take a leaf over when its worker was terminated or cannot be resumed (its model became unavailable, say), `specy-road worker delegate M2.3 --model <another> --rework`: the prompt carries the blocking reviewers' required changes and the previous worker's last message ("The loop").
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
| `state` | `starting → running → idle` (exit 0, no new READY) or `completed` (a READY that appeared or changed during the turn, for this node, on the worker's branch — the one actually checked out — at HEAD), `failed`, `handed_off`, `terminated`, or `paused_by_limit` (the turn stopped at a usage limit, whatever its exit code; `limit_reset_at` holds when it lifts, UTC ISO 8601, `null` when the harness named no time, cleared when the next turn starts; see *Post-run check and usage limits*). A `completed` worker still owns its leaf and its `max_workers` slot until `terminate`, unless its leaf is over (see "Orphaned workers" under the loop); only `failed` and `terminated` are closed, and a `failed` one with a native session id can be reopened by `message` / `resume` (see the command table). A `running` record whose wrapper **and** process group are gone is marked `failed` by the next `delegate` or `sync`, whichever leaf it was on. |
| `pid` / `wrapper_token` / `pgid` / `harness_pid` / `harness_start` | The wrapper, the random token in its argv, their process group (the wrapper's pid: it is a session leader), and the harness child with its start time. A pid is this worker's wrapper only when its command line carries the resolved repo root, the worker id and the token as whole arguments; a pid our user cannot signal is someone else's. The harness pid counts only with its recorded start time. All are cleared when the wrapper records the exit. |
| `limit_reset_at` | While `paused_by_limit`: when the usage limit lifts (UTC ISO 8601), or `null` when the harness named no time; cleared when the next turn starts. |
| `toolkit_version` | The specy-road build that created the record (`__version__`, plus `+<commit>` or `+<commit>.dirty` when run from a toolkit git checkout). |
| `last_output_at` | When the wrapper last read a stdout line from the harness, written at most every 5 s (each write takes the workers lock), and at once by the first line after a `stalled` mark, which that write clears; set to the launch time at the start of every turn, so a new turn starts a new silence. |
| `queued_message` | Follow-up text from `worker message` while a turn was still running (a later message during the same turn is appended, separated by a blank line). The wrapper delivers it as the next turn; when that delivery fails the text stays and the worker is flagged `message_undelivered`. The next `worker message` or `worker resume` sends the stored text, a blank line, then its own prompt, and clears both only after that turn starts. `terminate` drops the text and clears the flag. |
| `lease.holder` | The single writer: `broker` (specy-road sends turns), `human` (handed off), `native` (adopted; observe only), `none`. |
| `instruction_epoch` | +1 for every recorded human intervention. |
| `checkpoint` | Git HEAD and time at the last handoff; `reclaim` and `reconcile` diff from here. |
| `flags` | `possibly_modified_externally` (a human session returned without hook evidence), `needs_reconcile` (changes outside the touch zones, the leaf's contract changed, or the worktree is off the worker's branch), `wrapper_gone_harness_alive` (the wrapper died; the harness or its group did not — the leaf stays owned until `terminate`), `stalled` (`running` with `last_output_at` older than `policy.stall_after_seconds`, default 600: set by `sync` or `list` with one `stalled` event; the next output line clears it, a later silence raises it again, and a worker that stops running loses it), `post_run_findings` (the post-run check after the last turn found something; set or cleared by every turn's check), `message_undelivered` (a queued follow-up could not be delivered; cleared when a later `message` or `resume` sends it, or by `terminate`). |

Events (`seq`, `type`, `source`, `authority`, `summary`, `epoch`): `started`, `launched` (the harness process is up; detail `argv0`, `harness`, `resumed`), `first_output` (its first stdout line), `output`, `turn_completed`,
`completion`, `error`, `message`, `message_queued`, `resumed`, `intervention`, `handoff`, `reclaim`, `terminated`, `adopted`, `reconcile`, `stalled` (detail `silent_seconds`, `last_output_at`, and `last_summary`, the last event parsed from the harness), `usage` (below),
`api_retry`, `permission_denied`, `usage_limited`, `post_run_check`. Summaries are at most 500 characters; a transcript never goes in the log.

The wrapper appends one `usage` event (`worker_suggestion`) per turn end, in the same shape for every harness; a field the harness did not report is `null`, never 0, and a turn that reported nothing (a crash, `turn.failed`, `generic`) still gets one, all `null` (also a harness that could not start). Recorded lines per harness, with provenance: `tests/fixtures/worker_usage/turn_end_lines.json`.

| `usage` detail | Claude Code (`result` line) | Codex (`turn.completed.usage`) | Cursor (`result` line) |
|---|---|---|---|
| `input_tokens` / `cached_input_tokens` | all input: `input_tokens` + cache creation + cache reads (each counted when reported) / cache reads | `input_tokens` / `cached_input_tokens` (`cache_write_input_tokens` is not read); on `codex exec resume` these are the thread's running totals, so the wrapper records them as `session_usage` and subtracts the previous `usage` event's (all four token counts; a lower total counts whole) | `usage` when the line carries one (snake or camel case, read as Claude's), else `null` |
| `output_tokens` / `reasoning_tokens` | `output_tokens` / `output_tokens_details.thinking_tokens` | `output_tokens` / `reasoning_output_tokens` | as above / `null` |
| `cost_usd` / `cost_is_estimate` | this turn's: `total_cost_usd` is the session's running total, so the previous `usage` event's `session_cost_usd` is subtracted (a lower total counts whole); `true`, a client-side estimate | neither reports a cost: estimated from the token counts and the pinned roster profile's `cost_usd_per_mtok` for the launch's `--model` / `-m` (Codex's as `session_cost_usd` too, so a resumed turn's is the difference) / `true`; `null` / `null` when the profile has no prices or the launch names no model | estimated from the profile's `cost_usd_per_mtok` as for Codex / `true`; else `null` / `null` |
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
sensitivity (the same rules as `orchestrate plan`). While `policy.signed_reviews`
is on it also refuses an entry whose model's profile records guidance bypass
(the shipped one: **composer-2.5**, a finding about that model, not the Cursor
harness) unless the committed entry sets `allow_guidance_bypass_model: true`:
before the preflight and the harness, for chores, `message` and `resume` too.
An opted-in entry prints one `warning: <id> (model <api_id>) opted in at its own
risk: …` per launch. See [orchestration-roster.md](orchestration-roster.md#models-observed-to-bypass-the-guidance-allow_guidance_bypass_model).

```yaml
roster:
  - id: claude-opus-5-5
    family: anthropic
    roles: [executor, reviewer]
    harness: claude-code            # claude-code | codex | cursor | generic
    billing_route: claude_subscription   # a label, recorded on the worker; a claude_subscription reviewer runs in explicit mode. channels.cli is still needed for a command other than that default
    # Optional: your own command. {prompt} is the prompt file path; {session}
    # is the native session id; {session_flag} (claude-code only) is the
    # harness's own argument for it: `--session-id <id>` on launch,
    # `--resume <id>` on resume. A command that names {session} or
    # {session_flag} serves launch AND `message` / `resume` (the same line, run
    # again with the recorded id). `cli_resume` (it must name {session} or {session_flag}) is what
    # `message` / `resume` run instead, for Codex and Cursor, whose resume is its own command; a launch
    # command with neither and no cli_resume makes `delegate` warn, and its resumes run the default
    # command with the default's permissions. `delegate` also notes a command printing text, not stream-json.
    # {reviews_dir} is the main checkout's work/reviews/<ID>, for your harness's
    # writable-root flag (`--add-dir {reviews_dir}`), so a worktree executor can
    # write READY there. No channels.cli: the default command.
    # channels:
    #   (a placeholder must be a whole argument, bare or in one pair of quotes —
    #   `--session-id={session}` and `"prefix <prompt>"` are refused; `< {prompt}` feeds the file on stdin)
    #   cli: "claude -p --output-format stream-json --verbose --permission-mode acceptEdits {session_flag} < {prompt}"
    # Codex (the launch's own policy, repeated: `exec resume` carries only the conversation):
    #   cli: "codex exec --json -c sandbox_mode=workspace-write -c sandbox_workspace_write.network_access=true -c approval_policy=never - < {prompt}"
    #   cli_resume: "codex exec resume --json -c sandbox_mode=workspace-write -c sandbox_workspace_write.network_access=true -c approval_policy=never {session} - < {prompt}"
    # Cursor (the default's permissions, sandbox on and no --force, as your own command; "<prompt>" puts the text
    # on the command line, so a prompt over 128 KiB is refused before launch: docs/orchestration-harness-launch.md):
    #   cli: "agent -p --output-format stream-json --trust --sandbox enabled --add-dir {reviews_dir} \"<prompt>\""
    #   cli_resume: "agent -p --resume {session} --output-format stream-json --trust --sandbox enabled --add-dir {reviews_dir} \"<prompt>\""
policy:
  max_workers: 2                    # each worker draws on a plan quota
```

**Known limitation: a Codex executor cannot commit under the default command.** codex-cli's `workspace-write` sandbox keeps git metadata read-only: a linked worktree's gitdir (`<main checkout>/.git/worktrees/<codename>/`) and the common `.git` that receives its objects and refs are outside the writable roots, and so is a plain checkout's own `.git`. The worker implements and runs the tests, then `git add` fails (`Unable to create '…/index.lock': Operation not permitted`), nothing is committed and no READY is written; from a worktree it cannot write the main checkout's `work/.sessions/` either. The default launch policy stays as it is: a Codex executor needs a `channels.cli` (and `cli_resume`) that grants git writes. The narrowest grant the CLI offers is both git directories as writable roots, as config, which `exec` and `exec resume` both take: `cli: 'codex exec --json -m <model> -c sandbox_mode=workspace-write -c approval_policy=never -c "sandbox_workspace_write.writable_roots=[\"$(git rev-parse --absolute-git-dir)\",\"$(git rev-parse --path-format=absolute --git-common-dir)\"]" --add-dir {reviews_dir} - < {prompt}'`, and `cli_resume:` the same with `codex exec resume --json -m <model>`, the same three `-c`, then `{session} - < {prompt}` (YAML single quotes; the command runs in the worktree, so `git rev-parse` names its own directories). Checked with `codex sandbox` on codex-cli 0.165.0 (2026-11-04): with both roots `git add` and `git commit` succeed in a linked worktree and in a plain clone (where both resolve to its `.git`); the common `.git` alone is not enough (the worktree's own gitdir stays read-only, `--add-dir` of it included), nor is the worktree's gitdir alone (the objects go into the common one). A `channels.cli` gets neither the default's memory switches nor its profile `CODEX_HOME` (see the adapter table); add the `-c` memory switches if you want them.

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
(Cursor permissions: see Permissions below). Cursor's model ids carry the effort (`agent
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

**Claude and `{session}`.** Claude Code refuses `--session-id` for a session that already exists ("Session ID … is already in use", exit 1), so a `channels.cli` of the form `claude -p … --session-id {session} < {prompt}` launches fine and then fails every `message` / `resume`, closing the worker as `failed`. Use `{session_flag}` instead: it expands to `--session-id <id>` when the worker is launched and to `--resume <id>` on every `message` / `resume`, so one command line, with your permission flags, serves the whole leaf (the roster example above). It is defined for `claude-code` only; on another harness a `{session_flag}` command is refused rather than guessed. `prompt --channel cli` has no session, so there it expands to nothing. An older alternative is a small wrapper that resumes when the session exists:

```sh
#!/bin/sh
# claude-worker.sh <session> <prompt file>: start the session, or resume it.
sid=$1 prompt=$2
set -- -p --output-format stream-json --verbose --dangerously-skip-permissions --model claude-opus-5-5
if ls "${CLAUDE_CONFIG_DIR:-$HOME/.claude}"/projects/*/"$sid".jsonl >/dev/null 2>&1; then
  exec claude "$@" --resume "$sid" < "$prompt"
fi
exec claude "$@" --session-id "$sid" < "$prompt"
```

It looks for Claude Code's own transcript of the session (checked on Claude Code 2.1.312; re-check after upgrading), in the account `CLAUDE_CONFIG_DIR` selects, and `exec` keeps `claude` itself as the worker's harness process.

**Permissions in the harness's settings file.** The other way to keep a worker's permissions across resumes is to leave the command alone and put them where every `claude` run in the worktree reads them: `.claude/settings.json` (committed, shared) or `.claude/settings.local.json` (yours), with `permissions.allow` / `permissions.deny` rules and `permissions.defaultMode`. Claude Code reads them from the working directory on launch and on resume alike, so the default command and a custom one run under the same rules, and a linked worktree sees the committed file once its branch has it. Command-line flags still win over the file for that run.

**A hands-off Claude Code executor.** Keep the rules in one file outside the repository (here `~/.config/specy-road/claude-worker.json`) and pass it with `--settings` on a `{session_flag}` command, so launch and every resume load it. `acceptEdits` lets the worker edit files in its working directory and the `--add-dir` hand-off directory only; the allow list adds the shell commands an executor runs, and the deny list (prefix rules: a trailing ` *` matches any arguments) keeps it off the remote:

```json
{"permissions": {
  "allow": ["Bash(git status *)", "Bash(git diff *)", "Bash(git log *)", "Bash(git add *)", "Bash(git commit *)", "Bash(pytest *)", "Bash(specy-road *)"],
  "deny": ["Bash(git push *)", "Bash(gh pr *)", "Bash(git reset *)", "Bash(git checkout *)", "Bash(git switch *)"]}}
```

```yaml
    channels:
      cli: "claude -p --output-format stream-json --verbose {effort} --permission-mode acceptEdits --settings ~/.config/specy-road/claude-worker.json --add-dir {reviews_dir} {session_flag} < {prompt}"
```

Do not add a bare `Edit` or `Write` allow rule: in `dontAsk` mode it lets the worker write anywhere on disk, the main checkout included. Relative deny rules such as `Edit(./roadmap/**)` resolve against the worker's own worktree, so they protect only that tree, never the main checkout.

**Permissions.** The Claude Code default passes its permissions explicitly, the same on launch and resume: `--allowedTools Read,Edit,Write,Glob,Grep,Bash --permission-prompts none --permission-mode acceptEdits`. Since 2.1.302 `claude -p` silently denies a tool nothing approved, so the allow-list is what lets an executor run its tests and commit; with no prompts, anything else is denied and Claude is told not to retry. Under `-p` a denial does not stop the run: it appears as a `permission_denied` message in the stream and in the result's `permission_denials`, and the turn exits 0, so read those, not the exit code (the post-run check records each one as a finding). To narrow or widen the default, set `channels.cli` on the roster entry to the command you want (for Claude, a `{session_flag}` command as above, or `message` breaks). **Cursor permissions:** `agent -p` already has write and shell tools; the default launch and resume commands pass `--trust` (accepts the new worktree as a workspace) and `--sandbox enabled` (Cursor's sandbox confines its shell commands), never `--force`. `cursor_force: true` on a roster entry (boolean, default `false`, `cursor` entries only) passes `--trust --force` instead, on launch and resume alike: `--force` (alias `--yolo`) force-allows every command that is not explicitly denied, so that worker runs everything it decides to. `orchestrate plan` and `doctor` print one `! cursor --force:` warning per entry that sets it, assigned or not, and per `cursor` entry whose `channels.cli` or `cli_resume` passes `--force`, `-f` or `--yolo` (a custom command keeps the flags it is written with; `cursor_force` does not change it), and every Cursor worker's `launched` event records the permission flags actually passed (`detail.permissions`). A custom command is read by POSIX quoting alone, running and expanding nothing: quotes, backslashes and line continuations count as `sh` takes them, an unquoted operator ends a word (`--force; true` passes `--force`), short switches may cluster (`-pf`), and every word of the line counts, so `rm -f x; agent ...` also warns, while a word built at run time (`$FLAGS`, `--fo$(:)rce`, bash's `$'--force'`, a wrapper script, a quoted `sh -c '...'`) is not seen. A malformed `channels.cli` is an error, never a silent fall-back to the default. **Known limitation: Cursor's sandbox may not start.** On Ubuntu 24.04 with `kernel.apparmor_restrict_unprivileged_userns = 1` (its default), `agent -p --sandbox enabled` exits 1 before its first event: `Sandbox mode is enabled but not available on this system. Sandbox failed to start, possibly due to AppArmor configuration.` (agent 2026.11.05-86047df, a fresh linked worktree, 2026-11-05). The default stays sandboxed: fix the host (https://cursor.com/docs/agent/terminal), or set `cursor_force: true` on the entry and accept the warning; the same turn under `--trust --force` edited a file, ran `pytest` and committed. A roster that hits this can opt the affected `cursor` entries in with `cursor_force: true`. Codex runs with `-c sandbox_mode=workspace-write -c approval_policy=never`, as config overrides because `codex exec` and `exec resume` take no `--ask-for-approval` (and `exec resume` no `--sandbox` or `-C`), as the codex-cli 0.166.0 capture under `model-profiles/harness-captures/codex/` shows.

## The loop

```bash
specy-road worker sync                 # start of every turn: what changed (--wait: block until something does)
specy-road worker delegate M2.3 --model claude-opus-5-5
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
directory the worker is told to work from). **Rework and takeover.** When the leaf has blocking review records (each reviewer's current `REVIEW-<model>.md` with `verdict: block`, at the branch tip or an earlier commit), the executor prompt (`delegate` and `specy-road prompt --role executor` alike) has a `## Rework` section listing each blocking reviewer's `required_changes` (its failing acceptance ids when it listed none) and telling the executor to build on the commits already on the branch, not reset or rewrite them; when the leaf's latest worker is `terminated` or `failed`, the section also carries that worker's last final message (the last harness message in its event log), so a takeover by another model loses nothing. `delegate --rework` is the documented path when the previous worker was terminated or cannot be resumed: it makes the takeover explicit, refusing while the leaf still has a running or resumable-in-progress worker (`message` or `resume` it, or `terminate` it first), treating a **`completed`** worker as ended, or when there is neither a blocking record nor a stopped worker to rework from, and says on stderr what the prompt carries. A worker that can still be resumed keeps its session: send the findings with `worker message` instead.

**What `max_workers` counts.** `delegate`, `message` and `resume` each refuse a turn when the workers already counted reach `policy.max_workers` (a resumed worker does not count itself, so an `idle` worker resumes in its own slot). Counted are this checkout's active records (any state but `failed` and `terminated`, less the orphaned `idle` or `completed` ones, below) in `work/.workers/`, which the main checkout and all its linked worktrees share, plus every **lease ref** on the integration remote (`remote` in `roadmap/git-workflow.yaml`) whose checkout id is not this one's, fetched (and pruned) into `refs/specy-road/known-leases/<remote>/` by every online `delegate`, `message`, `resume` and `worker sync` (a plain `git fetch` does not fetch them). Each launch or resume pushes `refs/specy-road/leases/<checkout-id>/<worker-id>` (a parentless empty-tree commit naming the worker) and counts again after the push, so of two checkouts launching at once neither goes over the limit (both may be refused). `adopt` pushes one too, with no recount (the session already runs); an adopt whose lease cannot be pushed is refused and its record closed. A `delegate` whose leaf already has a worker here returns it before any remote read, so a retry is answered while the remote is down. The checkout id is a uuid written once to `<git-common-dir>/specy-road-checkout-id`: linked worktrees share it with their main checkout, and a separate clone has its own. It is written to a temporary file and hard-linked into place, so it is never seen half-written and concurrent first calls agree on one. A file holding a valid id is only ever read, never moved or rewritten, so an id once returned stays the id. A missing, empty, unreadable or malformed file is uninitialized, never "no id": under the workers lock, after reading it again, a new id is installed from a temporary file (`os.link` when absent, which fails if the file appeared; `os.replace` over an invalid one; no lease can have been pushed under it); after any failure the file is read again and a valid id there is used, and a call that still has no usable id refuses the launch or resume. Branch names and claim owners play no part: a clone's worker counts wherever its branch also exists and whoever holds the claim. The lease follows the record: kept while `idle`, `completed` or `handed_off` (an `idle` or `completed` worker whose leaf is over has its lease deleted by the next `worker sync`), deleted when the record goes `failed` or `terminated`; `failed` is written and its lease deleted as one step under the workers lock (the wrapper's nonzero exit and harness-start failure, and a dead wrapper's close), so a resume, which pushes its lease under that lock, never has its new lease deleted by the old turn's cleanup. `worker sync` makes this checkout's lease refs match its active records: it deletes refs whose worker is no longer active here (a crashed wrapper, a delete that failed) and, best effort, pushes one for each active worker without one (registered before leases existed, launched `--offline`, a push that failed); it reads the remote first, then rechecks each record and deletes and pushes under the workers lock, the lock every launch and resume pushes its lease under, so it cannot remove a lease being acquired. A repository without that remote pushes and reads no leases. Otherwise the turn is refused, and nothing is launched, when the remote rejects the lease push (`<remote> rejected the lease for W`) or cannot be reached (`cannot reach <remote> …; retry, or pass --offline`). `--offline` on `delegate`, `message` or `resume` is the explicit local-only escape: it neither fetches nor pushes, counts this checkout's workers plus the lease refs as last fetched into `known-leases` (refusing at that count), and prints one warning that the global limit was not verified, since a worker another checkout started after that fetch is not seen; other checkouts count its worker once a later online turn or `worker sync` pushes the lease. `--offline` is part of what an `--op-id` is bound to. Cost: a launch is one fetch, one push and one more fetch; a resume a push and a fetch; a close a push; `sync` one fetch (plus a push for any lease it repairs).

**Orphaned workers.** An `idle` or `completed` worker keeps its slot so a review `block` can resume it for a fix round. It is **orphaned**, and no longer counts toward `max_workers`, on any one of three causes, the same for the slot count, `list`/`sync` and `terminate --orphaned`: **unclaimed**, when at every integration ref that exists (the local integration branch and `<remote>/<branch>`) the registry is readable and has no claim on the leaf under any branch, whatever its status (a landed finish, `registry-prune --remove`, an abandoned leaf; only for a record that names the branch it was delegated under, as delegate and adopt always do); **Complete**, when at every such ref the roadmap is readable and says the leaf is Complete; or **worktree gone**, when the record's worktree is no longer a directory. The two ref causes need every existing ref to agree, so a stale snapshot can only keep a worker: a stale `<remote>/<branch>` still saying Complete or unclaimed for a leaf reopened and claimed since, or a landing not yet pushed and fetched, keeps it, and with no such ref, or one whose registry (roadmap) cannot be read, the unclaimed (Complete) cause is not judged. The caller's working tree is never read, since linked worktrees share the records and an older lane's registry is no authority. The reason lists every cause that holds. A `running` worker is never orphaned. Nothing is stored: each `list`, `sync`, launch and resume judges it afresh. At the limit the refusal names running and held workers apart, for example `` 3 workers active, policy max_workers is 3; 2 running: w-0002, w-0003; 1 completed: w-0001; `specy-road worker terminate w-0001` frees it, or wait for a running one to finish or raise the limit ``. `finish-this-task` terminates the finished leaf's own `idle` and `completed` workers; `worker terminate --orphaned` ends the rest.

**Waiting.** See [orchestration-worker-sync.md](orchestration-worker-sync.md) for `--wait`, `--until`, `--verbose`, and tool-use collapsing. In short: call `specy-road worker sync --wait` rather than sleeping; use `--wait --until completion` when you need the turn to end, not every tool-use line.

The worker's job is the executor's as before: implement, commit, write
`work/implementation-summary-<ID>.md` and `work/reviews/<ID>/READY-*.md`,
stop. A `completion` event says it stopped and whether READY exists; it is
**not** an approval. From there the review path is unchanged:
`review-packet`, reviewer prompts, `review record`, `handoff status`,
`mark-implementation-reviewed`, `finish-this-task`.

**Backgrounded tests.** A `completion` with exit 0 and READY missing, after a final reply saying a test or verifier run is still going in the background ("I'll be notified when it finishes"), is a lost turn: a headless turn ends when the agent replies, and nothing resumes the session when the background job finishes. The executor prompt tells the executor to run the verifier and tests in the foreground for this reason. To recover, `worker message W --text` telling the executor to rerun them in the foreground, wait for them to finish, and then complete its steps. Claude Code launches set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in the harness environment, executors (with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`) and reviewers alike (`review delegate` and the default reviewer command, bare or explicit): otherwise `claude -p` stays open up to 10 minutes of idle after its reply for background work it started (harness-facts).

**Post-run check and usage limits.** After every turn, whatever its exit code, the wrapper reads the turn's events and the worktree's git state against the state at the turn's start (`specy_road/worker_turn_check.py`). Findings: permission denials (Claude's result `permission_denials`, one `permission_denied` event each), a failed turn (an error no completed turn followed, or a non-zero exit, a SIGKILL included, that no usage limit explains; the check is written before the turn's exit event, so it names the exit itself), api retries (`system/api_retry`), a branch change, a HEAD that is not a descendant of the turn's start (reset, rebase, amend), commits outside the leaf's touch zones, a changed stash list (the stack is shared by every worktree of the repository, so another session's stash shows too), and dirty paths beyond the leaf's bookkeeping that are new, changed or gone during the turn (a file already dirty at the start and edited again counts, and so does pre-turn work the turn restores, deletes or commits). Every turn records exactly one `post_run_check` event, a clean turn included (empty `findings`, summary `post-run check: clean`); findings flag the worker `post_run_findings`, which `worker sync` and `list` show, and a clean turn clears the flag. A usage limit is read from the text, never the exit code: a Claude result whose text names a limit (a successful one only with a reset time), a Claude turn that exited non-zero with no result line whose session transcript (`~/.claude/projects/<project>/<session-id>.jsonl`) ends in an assistant message naming a limit (the prompt is never read), a Codex `turn.failed`/`error` with limit wording and its "try again in/at" time, or a turn that ended after `rate_limit` retries with no completed turn. The **retry watchdog** stops a harness whose `rate_limit` retries announce more than 600 s of waiting in one turn (SIGTERM; Claude exits 143 and the turn is lost, the session kept) rather than letting it wait out a usage limit. Such a turn ends in `paused_by_limit` with `limit_reset_at`, even when it exits 0 with a fresh READY (its `completion` event still records `ready`); the worker keeps its slot and lease, and `resume` / `message` refuse it until that time (at once when no time was named), then resume the same session with the same launch flags.

**Killing by pattern.** An executor clearing its own stray test run with `pkill -f "pytest -q"` also ended the coordinator's and other leaves' pytest runs (SIGTERM, no failure reported), since sessions share the machine. The executor prompt forbids kills by name or pattern and allows stopping only a process the executor started, by the pid it recorded.

**Parallel tests.** Concurrent executors and reviewers share the machine's CPU, and each one running the full suite with one test worker per core (`pytest -n auto`) oversubscribes it: with several of them the load average runs well past the core count, the landing suite takes several times as long, and a reviewer's run can outlast its harness's background-task limit and be killed. Set **`verify_cmd`** in `roadmap/git-workflow.yaml` to the leaf-level test command with a small worker count (for example `python -m pytest -n 4 -p no:cacheprovider`): executor briefs and reviewer prompts give it as the command to run the leaf's tests, with the test paths appended. Keep the full parallel suite in **`land_check_cmd`**, which runs once per landing on the merge commit ([git-workflow.md](git-workflow.md)). Without `verify_cmd` the prompts only say to cap parallel test workers when other workers share the machine.

| Command | Does |
|---|---|
| `list [--all]`, `status W`, `events W [--since N]`, `open W` | Read. `open` prints the worktree, the log, and the native resume command. `list` marks each orphaned worker `orphaned: <why>` (`orphaned` in `--json`, `null` otherwise). |
| `sync [--ack] [--wait [--until TYPES] [--timeout S]] [--verbose]` | Every worker's events after the last acknowledged one (`work/.workers/sync.yaml`, per worker the acked `seq` and `acked_at`); compact, with state, lease, epoch and flags. When a follow-up is waiting for the current turn to finish, the worker's `queued_message` is shown too. A sequence number between the last acknowledged one and the record's `last_event_seq` that no readable line carries (lost or unreadable, the final event included) is reported as a gap (`! gap: event(s) #4–#5 …`; `gaps` in `--json`); a worker whose new events are all unreadable is still listed, and `--ack` moves past its gaps. `--wait` blocks until there is something to report ([orchestration-worker-sync.md](orchestration-worker-sync.md): `--until`, `--verbose`, READY-only hint); exit 2 when `--timeout` passes with nothing. Every orphaned worker is listed after the events, new events or not (`orphaned`, worker id to why, in `--json`). |
| `message W --text\|--file` | A follow-up: resumes the native session with the text when the wrapper is stopped. While a turn is still running, the text is stored on the record as `queued_message` and delivered as the next turn when the wrapper finishes (`message_queued` in the log); a second message during the same turn is appended, separated by a blank line, and the event summary says `appended`. When that delivery fails, the text stays and `message_undelivered` is set; the next `message` or `resume` sends the stored text, a blank line, then its own prompt. `list` and `sync` show it. `--no-queue` keeps the old refusal for a live turn. Needs the `broker` lease. |
| `resume W [--ready-only]` | `message` with a "continue from where you stopped" prompt, or with **`--ready-only`** a short prompt to write READY for HEAD only (after a completion reported READY missing). Both resume a worker in `idle`, `completed` (a review `block` goes back as a message) or `failed` **with** a `provider_session_id` (a crashed or hand-killed turn keeps its session, and is refused while another worker holds the leaf). Every resumed turn takes a `max_workers` slot like a launch: refused when the other counted workers already reach the limit. Refused: `failed` with no session id and `terminated` ("delegate again instead"), `handed_off` (`WORKER_LEASED_BY_HUMAN`), and a live process — `stalled` included, which becomes resumable once its harness exits or is stopped (the wrapper then records `failed`; `terminate` instead closes it for good). `--no-queue` applies only to `message`, not `resume`. |
| `interrupt W` | **Unsupported** by every CLI adapter: exit 2 and the reason. A kill is not an interrupt; use `terminate` and say so. |
| `terminate W` | SIGTERM the recorded process group (wrapper, harness and children), SIGKILL after 5 s, and confirm the group is gone — also when the wrapper itself already died, while the harness still matches its start time and the verified wrapper or harness is still in the recorded group; state `terminated`. The turn is lost. Any `queued_message` is dropped and `message_undelivered` is cleared; the `terminated` summary notes the dropped text. `terminate --orphaned` (no `W`, no `--op-id`) ends every orphaned worker in one step and prints each with its reason. |
| `handoff W` / `reclaim W [--note]` | Lease to a human and back; below. |
| `adopt --node ID --harness H --session SID` | Register a session the user started natively; lease `native`, observe only. Refused while the leaf has an active worker, and for an id that is not the harness's own shape (a UUID for Claude Code and Codex; shell-safe characters for all). |
| `reconcile W` | Paths changed since the checkpoint, and over the worker's whole lifetime (from the HEAD it started at), vs the leaf's touch zones as its claim row holds them now (`edit-node` keeps the row in step) — a rename or copy counts on both sides, so a `git mv` into the zone is still a change outside it, while a path that no commit on the branch's own (first-parent) line changed, nor the uncommitted tree, came in only through a merge and is not counted (a merge's own edits do count: what it changed against its first parent, less what another parent brought in and it kept unchanged, both sides of a rename included); and whether the leaf's own contract changed: its execution target (goal, acceptance, touch zones) and its planning sheet in the brief, not statuses or the sections that move with the integration branch (a prompt that can no longer be built for this model counts as changed). Sets or clears `needs_reconcile`. The leaf's brief, summary and prompts, the toolkit's state under `work/`, and `roadmap/registry.yaml` never count; any other `work/` file does. |
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

**Processes outside the group.** The recorded group covers the wrapper, the harness and what the harness forks directly, not what it
puts in a group or session of its own (Claude Code's Bash tool, Cursor's shell tool). `terminate` snapshots the group's descendants
before its first signal and also ends those outside the group once the group is gone (SIGTERM, then SIGKILL; each only while its
start time still matches, so a reused pid is never signalled); a survivor, or a failed `ps` listing, makes it fail instead of
reporting terminated. It cannot see a process already re-parented before that snapshot: after a `kill -9` of the harness or the
group, or a crash, what the tool was running (a test suite, a server) keeps running with ppid 1. Stop workers with `terminate`
rather than `kill -9`; after any SIGKILL, list what still runs in the worker's worktree (`lsof -d cwd | grep <worktree>`) and kill
it by hand.

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
the hook trusted. `UserPromptSubmit` fires for a human's interactive
session, which is the case the hook exists for, and was observed to fire for
every headless `claude -p --resume <id> "<prompt>"` run too (Claude Code
2.1.312 in the 2026-11-04 sandbox replay; also seen in the 2026-10-28 one).

## What each adapter supports

| Harness | Launch | Session id | Resume (`message`) | Interrupt / steer | Handoff command |
|---|---|---|---|---|---|
| `claude-code` | `claude -p --output-format stream-json --verbose --session-id <uuid> --model … --allowedTools Read,Edit,Write,Glob,Grep,Bash --permission-prompts none --permission-mode acceptEdits` (prompt on stdin: a brief can exceed Linux's 128 KiB per-argument limit). In a **linked** worktree the default also passes `--add-dir` pointing at the main checkout's `work/reviews/<ID>/` so the executor can write its READY hand-off under `acceptEdits` (launch and resume). | chosen up front | `claude -p --resume <id> …` | unsupported | `claude --resume <id>` |
| `codex` | `codex exec --json -m … -c sandbox_mode=workspace-write -c approval_policy=never -c features.memories=false -c memories.use_memories=false -c memories.generate_memories=false -C <worktree> -` (prompt on stdin), with `CODEX_HOME` set to the profile's own `~/.specy-road/codex-home/<model id>/` (none of your `~/.codex` config, memories or global AGENTS.md; your `auth.json` is linked in, so the login carries over; a `channels.cli` command gets neither). In a **linked** worktree it also passes `--add-dir` with the main checkout's `work/reviews/<ID>/` (a writable root beside the workspace, from `codex exec --help`, codex-cli 0.166.0). | `thread.started` | `codex exec resume --json -c sandbox_mode=workspace-write -c approval_policy=never <memory switches> <id> -` (same policy and `CODEX_HOME`, the profile home that holds the thread, run in the worktree, prompt on stdin; no `--add-dir`: the captured help documents none for `exec resume`, so a resumed turn may not reach the hand-off directory) | unsupported | `env CODEX_HOME=<profile home> codex resume <id>` |
| `cursor` | `agent create-chat` first (in the worktree), then `agent -p --resume <chat> --output-format stream-json --trust --sandbox enabled --model … --workspace <worktree> "<instruction naming the prompt file>"`: `agent -p` documents no stdin, so the prompt stays in its file and the one short argument tells the agent to read it, on launch, resume and the `--mode ask` reviewer alike ([`orchestration-harness-launch.md`](orchestration-harness-launch.md)); never `-w`/`--worktree` (a `channels.cli` that passes it is refused). In a **linked** worktree it also passes `--add-dir` with the main checkout's `work/reviews/<ID>/` (an extra workspace root, from `agent --help`, 2026.10.22), on launch and resume. | chosen up front (`create-chat`) | `agent -p --resume <id> … --trust --sandbox enabled …` (print-mode resume with a new prompt is undocumented; verify on your install; the prompt file is named, as on launch) | unsupported | `agent --resume <id>` |
| `generic` | `channels.cli` / profile `access.cli` with `{prompt}` (the prompt file path) or `<prompt>` (the prompt text, as the shipped profiles write it): a command whose one argument would exceed the OS limit of **128 KiB** is refused before it runs, naming the size and the `{prompt}` fix ([`orchestration-harness-launch.md`](orchestration-harness-launch.md)); `{reviews_dir}` as for any `channels.cli` | none | unsupported | unsupported | none |

**Known limitation (Codex inside Codex).** A `codex` worker delegated from inside a coordinator's own `codex exec --sandbox workspace-write` session exits 1 before its first event (`failed to initialize in-process app-server client: Operation not permitted`, codex-cli 0.165.0, 2026-11-04 replay).
Run a Codex coordinator outside that sandbox, or delegate Codex workers from a terminal or another harness.

Whatever the harness, the wrapper's own command line carries only the repo
root, the worker id, a token and the path of a mode-0600 launch file under
`work/.workers/` (argv and the stdin prompt), which the wrapper reads once
and deletes; a brief of any size reaches a stdin-reading harness.

Flags match the accepted `--version`/`--help` captures under `model-profiles/harness-captures/` (Claude Code 2.1.312, codex-cli 0.166.0, Cursor agent 2026.10.22-27dcf5f, all captured 2026-11-02) and will drift; `refresh-profiles --capture <harness>` classifies a newer capture, and
`tests/test_worker_adapters.py` and `tests/test_worker_turn_check.py` pin the command shapes. The long-lived protocols (Codex app-server, Cursor ACP, Claude Agent SDK) are what would add interrupt and steer; they are later adapters behind the same
interface, not emulated here.

## Checks that need a real installation

None of these is claimed by the test suite; run them before relying on the
feature in your own setup.

1. **Permission denials.** Delegate a trivial leaf on each harness you use with the default command. Pass: the worker reaches
   `completion`; on Claude Code, any `permission_denied` lines in `<id>.log` (the run does not stop on them) name rules `channels.cli` then resolves.
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

## Worker sandbox

**Off unless you opt in.** Without `worker_sandbox`, a worker's harness runs as your OS user with your
permissions. It can write the main checkout and its `.git/config` and hooks (which the coordinator's next git
command runs), your home directory and shell startup files, your harness settings and hooks, other leaves'
`work/reviews/` hand-offs and `work/.workers/` records, and it can use your SSH keys and `gh` login to push.
Only the review gate and finish's checks stand between such a turn and your integration branch.

To opt in, set it in `roadmap/git-workflow.yaml`:

```yaml
worker_sandbox: auto   # bwrap on Linux where it is installed; elsewhere a warning on each launch
```

| Value | Effect |
|---|---|
| omitted, `off` (or YAML `false`) | Unsandboxed, as before. |
| `auto` | [bubblewrap](https://github.com/containers/bubblewrap) (`bwrap`) on Linux where it is installed. Elsewhere (macOS, Windows, Linux without bwrap) every unattended launch logs `[wrapper] warning: no worker sandbox on this host …` and puts it in the `launched` event, then runs unsandboxed. |
| `bwrap` | Required: a host without bwrap refuses the turn. |

It covers turns started by `worker delegate`, `message` and `resume`. Reviewer turns and your own sessions are
not wrapped. In a sandboxed turn (`bwrap`, or `auto` with bwrap present):

- **A linked worktree is required.** A worker in the main checkout is refused before its harness starts,
  naming the need for a separate `--worktree`: the common git dir would otherwise have to be writable.
- **Writable:** the leaf's worktree; in the common git dir `objects/`, `refs/`, `logs/` and `worktrees/<name>/`
  (what a commit needs); a private tmpfs on `/tmp`.
- **Read-only:** everything else. That includes the common `config`, `hooks/` and `info/`, the main checkout,
  your home and the harness binaries. Inside the writable parts, whatever points git at a repository or its
  config is read-only again: the worktree's `.git` file, `worktrees/<name>/commondir` and `gitdir`, and
  `worktrees/<name>/config.worktree`. When you have no `config.worktree`, the worker sees an empty, read-only one.
  A worktree without its `gitdir` file is refused.
- **Harness state: one rule.** No directory in your home is writable from the sandbox; only the named auth
  files are. Any writable directory is an open namespace: a transcript directory would take a
  `projects/<project>/memory/MEMORY.md` that Claude reads as instructions just as readily as a transcript. So
  each state directory the harness uses is replaced by the worker's own (`work/.workers/<id>.state/`, kept
  across its turns). Only the entries below reach your copy. The table in `specy_road/worker_sandbox.py`
  (`HARNESS_STATE`) is authoritative.

  | Harness | Directories replaced | Files written through to yours | Yours, read-only (when you have them) |
  |---|---|---|---|
  | `claude-code` | `$CLAUDE_CONFIG_DIR` or `~/.claude`; `~/.cache` | `.credentials.json` | `settings.json`, `settings.local.json`, `hooks/`, `plugins/`, `skills/`, `agents/`, `commands/`, `output-styles/`, `CLAUDE.md` |
  | `cursor` | `~/.cursor`, `~/.config/cursor`, `~/.cache` | `auth.json` (in `~/.config/cursor`) | `hooks/`, `hooks.json`, `mcp.json`, `plugins/`, `rules/`, `skills/`, `skills-cursor/`, `extensions/` |
  | `codex` | the profile's `CODEX_HOME` | `auth.json` (the file it links to) | `config.toml`, `AGENTS.md`, `hooks/`, `plugins/`, `rules/`, `skills/` |

  Anything else the harness writes stays the worker's: its transcripts and sessions, and the steering names
  above when you have none. A worker can configure and remember only for its own later turns, never yours. An
  auth name that is a directory in your home is not bound. Two files must stay writable but can carry launch
  instructions: `~/.claude.json` (or `$CLAUDE_CONFIG_DIR/.claude.json`) and Cursor's `cli-config.json`. Each
  worker gets its own copy of these, made from yours on its first turn. A copy of a file inside a replaced
  directory (Cursor's `cli-config.json`, `$CLAUDE_CONFIG_DIR/.claude.json`) is a plain file in the worker's own
  directory, so the harness can replace it by rename (Cursor does on every start); `~/.claude.json` is bound
  over yours.

  The cost is that a sandboxed worker's sessions live only in its state directory. Its own resumes find them
  (the runner also reads Claude's transcript there for a usage limit). A human `claude --resume`, `agent
  --resume` or `codex resume` from your home does not find them, so `worker handoff` of a sandboxed worker
  cannot be resumed natively. Do not point a harness at the worker's state directory to get around this: the
  worker could have put settings and hooks there.
- **Hidden:** `~/.ssh` and `~/.config/gh` (an empty tmpfs), and `SSH_AUTH_SOCK`, `GH_TOKEN` and `GITHUB_TOKEN`
  in the environment. This blocks the default push routes. It does not isolate other secrets.
- **Hand-off:** `work/reviews/<ID>/` is a per-worker outbox (`work/.workers/<id>.outbox`). At each turn's start
  it holds a copy of the regular files already in the real directory (REVIEW, notes and `history/` records;
  links are not copied), so a fix round can read its blocking review. When the turn ends the runner moves only
  `READY-*` files from it into the real directory. Anything else written there, such as a new `REVIEW-` file or
  an edited copy of a record, is discarded.
- **Failures stop the turn.** If the sandbox cannot be set up (no linked worktree, an unwritable mount point)
  or `bwrap` exits before starting the harness, the worker ends `failed`, with the reason in an `error` event
  and bwrap's message in `<id>.log`. To run such a project unsandboxed, set `worker_sandbox: off`.

**Known limits.** The network stays open, because harnesses need their APIs. The git directories a commit
needs are shared and writable, so they are open namespaces too:
- Refs stay writable, so a worker can move a local branch other than its own.
- `objects/` takes any object, and an `info/alternates` file.
- `worktrees/<name>/` takes in-progress rebase or merge state. A coordinator that runs `git rebase --continue`
  in the worker's tree would carry out its todo list.

Only the files git reads as configuration or as a pointer to a repository are held read-only there. A nested repository's common git dir is not carved out, so a sandboxed
commit there fails. Codex's own `workspace-write` sandbox may still refuse git writes inside ours. Whether each
harness refreshes its login under these binds is a smoke check, not a test: before relying on it, run a trivial
leaf on Claude Code and on Cursor with `worker_sandbox: bwrap` and check that the turn authenticates, commits and
hands off READY. A resumed turn should find its session.

## Optional: refuse push from a linked worktree

`specyrd init --install-pre-push-hook` installs `specy_road/templates/specyrd/hooks/pre-push` as `.git/hooks/pre-push`; it refuses push when the repo toplevel is under `work/.worktrees/` and allows push from the main checkout. `worker delegate` and `review delegate` export `SPECY_ROAD_ORCHESTRATION_ROLE` (`executor` / `reviewer`) into the harness environment so the shipped orchestration hooks apply without pinning the role in the command.

## Working alongside sessions and the gate

`handoff status` prints active workers beside live sessions. A worker in a linked worktree does not touch the coordinator's branch; one in the same checkout (the claim's branch was checked out here) does, so the coordinator must not edit files in that leaf's touch zones while the worker runs — the presence guard (`session guard`) already refuses the git operations that would collide. Finishing the leaf is still `finish-this-task` from the leaf's branch after the gate; it terminates the leaf's own `idle` and `completed` workers (a `terminated` event each; a running one is left alone), so their records close and their slots free. With `--on-complete merge`, finish merges into the integration branch and **pushes that branch** (after stating how many local integration commits are not on the remote yet); `--push` only pushes the feature branch. From a linked worktree with `on_complete: merge`, finish cannot check the integration branch out while the coordinator's checkout holds it, so it merges and pushes **in that checkout** instead. That checkout must have no uncommitted changes to tracked files (untracked files are fine): otherwise finish refuses before its bookkeeping commit and names the checkout to commit or stash in.
