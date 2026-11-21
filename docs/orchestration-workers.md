# Workers: leaves and chores on other harnesses, and the roster

## Agent quickstart

**Use this doc when:** delegating a claimed leaf or a chore to a session on another harness (`specy-road worker …`), taking one over by hand, or building and trying the roster (`models roster`, `roster_add`, `orchestrate plan --spread`).
**Not for:** the review gate, roster roles and hand-off files — [`orchestration.md`](orchestration.md).

**Must know without reading on:**
- Run `specy-road worker sync` at the start of every turn; `specy-road worker sync --ack` once you have acted on the events. To wait for a worker, `specy-road worker sync --wait` (see [orchestration-worker-sync.md](orchestration-worker-sync.md) for `--until` and compact output), never a sleep loop.
- One writer per worker (`lease.holder`): `specy-road worker handoff <W>` before a human opens the native session, `specy-road worker reclaim <W>` after. While leased to a human, `message` and `resume` fail with `WORKER_LEASED_BY_HUMAN`.
- `delegate` runs after pickup only: `specy-road worker delegate M2.3 --model claude-opus-5-5` needs the leaf's registry claim and branch. Work outside the roadmap runs as a chore instead ("Chores" below).
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
- stalled workers and `worker recover` → "Stalled workers"
- the presence guard and finishing the leaf → "Working alongside sessions and the gate"
- `worker list` / `worker status` JSON for watchers, and what a claim locks → "Interfaces and limits"
- dry-run plans, `roster_add`, `models roster`, the coordinator and `--spread` → "The roster: building and trying it"
- chores (`chore start|close|garden`) → "Chores: worker-run work outside the roadmap"

**Related:** [`orchestration.md`](orchestration.md), [`agentic-sandbox-runbook.md`](agentic-sandbox-runbook.md), [`grind-session.md`](grind-session.md).

`specy-road worker` lets the coordinator — the model in whatever IDE chat you
are already in — hand a roadmap leaf to a session on another harness, keep
talking to you while it runs, and find out what happened at the start of its
next turn. It is the delegation layer under
[orchestration.md](orchestration.md): the review gate, hand-off files, and
roster are unchanged; this adds the launching, watching, and taking-back.

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
| `recoveries` | How many times `worker recover` has ended this stalled worker and resumed it; never reset, so separate `recover` calls count toward one limit (`policy.max_fix_rounds`, default 3). |
| `lease.holder` | The single writer: `broker` (specy-road sends turns), `human` (handed off), `native` (adopted; observe only), `none`. |
| `instruction_epoch` | +1 for every recorded human intervention. |
| `checkpoint` | Git HEAD and time at the last handoff; `reclaim` and `reconcile` diff from here. |
| `flags` | `possibly_modified_externally` (a human session returned without hook evidence), `needs_reconcile` (changes outside the touch zones, the leaf's contract changed, or the worktree is off the worker's branch), `wrapper_gone_harness_alive` (the wrapper died; the harness or its group did not — the leaf stays owned until `terminate`), `stalled` (`running` and silent for `policy.stall_after_seconds`, default 600, where silence runs from the newest of `last_output_at` and the `message` or `resumed` event that started the current follow-up turn, so a resumed or recovered turn never inherits the last turn's silence, and with neither from the first turn's launch: set by `sync`, `list`, `doctor` or `recover` with one `stalled` event; the next output line clears it, a later silence raises it again, and a worker that stops running loses it), `needs_person` (stalled after `recover` already ran the limit on it; cleared once it is no longer stalled), `post_run_findings` (the post-run check after the last turn found something; set or cleared by every turn's check), `message_undelivered` (a queued follow-up could not be delivered; cleared when a later `message` or `resume` sends it, or by `terminate`). |

Events (`seq`, `type`, `source`, `authority`, `summary`, `epoch`): `started`, `launched` (the harness process is up; detail `argv0`, `harness`, `resumed`), `first_output` (its first stdout line), `output`, `turn_completed`,
`completion`, `error`, `message`, `message_queued`, `resumed`, `intervention`, `handoff`, `reclaim`, `terminated`, `adopted`, `reconcile`, `stalled` (detail `silent_seconds`, `last_output_at`, and `last_summary`, the last event parsed from the harness), `usage` (below),
`api_retry`, `permission_denied`, `interactive_tool` (a Cursor question-tool `tool_call`), `usage_limited`, `post_run_check`. Summaries are at most 500 characters; a transcript never goes in the log.

The wrapper appends one `usage` event (`worker_suggestion`) per turn end, in the same shape for every harness; a field the harness did not report is `null`, never 0, and a turn that reported nothing (a crash, `turn.failed`, `generic`) still gets one, all `null` (also a harness that could not start). Recorded lines per harness, with provenance: `tests/fixtures/worker_usage/turn_end_lines.json`.

| `usage` detail | Claude Code (`result` line) | Codex (`turn.completed.usage`) | Cursor (`result` line) |
|---|---|---|---|
| `input_tokens` / `cached_input_tokens` | all input: `input_tokens` + cache creation + cache reads (each counted when reported) / cache reads | `input_tokens` / `cached_input_tokens` (`cache_write_input_tokens` is not read); on `codex exec resume` these are the thread's running totals, so the wrapper records them as `session_usage` and subtracts the previous `usage` event's (all four token counts; a lower total counts whole) | `usage` when the line carries one (snake or camel case, read as Claude's), else `null` |
| `output_tokens` / `reasoning_tokens` | `output_tokens` / `output_tokens_details.thinking_tokens` | `output_tokens` / `reasoning_output_tokens` | as above / `null` |
| `cost_usd` / `cost_is_estimate` | this turn's: `total_cost_usd` is the session's running total, so the previous `usage` event's `session_cost_usd` is subtracted (a lower total counts whole); `true`, a client-side estimate | neither reports a cost: estimated from the token counts and the pinned roster profile's `cost_usd_per_mtok` for the launch's `--model` / `-m` (Codex's as `session_cost_usd` too, so a resumed turn's is the difference) / `true`; a `channels.cli` runs as `sh -c <command>`, so its `-m` counts only when the command is one simple command (redirections allowed) and the value is literal, the rule the review gate uses: a list, a pipeline, a quoted or unquoted `$(…)` anywhere in it (the git-roots grant below) or `-m "$MODEL"` leaves it unpriced (`$?`); `null` / `null` when the profile has no prices or the launch names no model | estimated from the profile's `cost_usd_per_mtok` as for Codex / `true`; else `null` / `null` |
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
risk: …` per launch. See [Models observed to bypass the guidance](#models-observed-to-bypass-the-guidance-allow_guidance_bypass_model).

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

**Codex project trust.** codex-cli 0.166.0 loads a project's `.codex/` hooks only when that project is trusted, and skips an untrusted hook silently. Trust is kept per path in Codex's `config.toml` (`trust_level` under `[projects]`); 0.166.0 has no command-line flag that trusts a project (its one trust flag, `--dangerously-bypass-hook-trust`, covers hook definitions for one run). No specy-road Codex launch, resume or reviewer turn passes a trust flag or override, so a reviewer stays untrusted and its project hooks do not load. For an executor, the session guard in `.codex/hooks.json` fires only once you trust that worktree yourself; an untrusted one runs unguarded with no warning. From codex-cli 0.169.0 (CX-TRUST in the 2026-11-19 harness-facts report) `codex exec` keeps project configuration and MCP servers disabled in an untrusted directory even with `--sandbox workspace-write`, and `--trust` on `codex exec` or `codex review` saves that trust. The grant persists with `--ephemeral`, cannot be combined with `--ignore-user-config`, and refuses an explicitly untrusted project. specy-road's launch argv is unchanged and still passes no `--trust`. From codex-cli 0.168.0 (CX-FLAG-MULTI) the `multi_agent` feature flag is deprecated in favour of `agents.enabled`; the launch still leaves that feature on, and the report does not give the command-line form of `agents.enabled`.

**Claude Code's opt-in Bash sandbox blocks worktree lifecycle commands.** With `sandbox.enabled` on (and `allowUnsandboxedCommands: false`), the sandbox makes `.git/worktrees/` read-only even when `.git` is inside the session's directory. In a throwaway repository on Claude Code 2.1.329 (2026-11-19), `git worktree add` failed with `could not create directory of '.git/worktrees/<name>': Read-only file system` (exit 128) for a path outside the directory and one inside it, after creating the new branch, and `git worktree remove` failed the same way. `git worktree prune` printed the failure but exited 0. `git branch` and edits inside the directory worked. Run `specy-road` commands that create, remove or prune worktrees outside such a session, or allow them unsandboxed. On Linux the sandbox also needs `bubblewrap` and `socat`: when one is missing, Claude Code 2.1.329 warns `Sandbox disabled` and runs every command unsandboxed.

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

**Permissions.** The Claude Code default passes its permissions explicitly, the same on launch and resume: `--allowedTools Read,Edit,Write,Glob,Grep,Bash --permission-prompts none --permission-mode acceptEdits`. Since 2.1.302 `claude -p` silently denies a tool nothing approved, so the allow-list is what lets an executor run its tests and commit; with no prompts, anything else is denied and Claude is told not to retry. Under `-p` a denial does not stop the run: it appears as a `permission_denied` message in the stream and in the result's `permission_denials`, and the turn exits 0, so read those, not the exit code (the post-run check records each one as a finding). To narrow or widen the default, set `channels.cli` on the roster entry to the command you want (for Claude, a `{session_flag}` command as above, or `message` breaks). **Cursor permissions:** `agent -p` already has write and shell tools; the default launch and resume commands pass `--trust` (accepts the new worktree as a workspace) and `--sandbox enabled` (Cursor's sandbox confines its shell commands), never `--force`. `cursor_force: true` on a roster entry (boolean, default `false`, `cursor` entries only) passes `--trust --force` instead, on launch and resume alike: `--force` (alias `--yolo`) force-allows every command that is not explicitly denied, so that worker runs everything it decides to. `orchestrate plan` and `doctor` print one `! cursor --force:` warning per entry that sets it, assigned or not, and per `cursor` entry whose `channels.cli` or `cli_resume` passes `--force`, `-f` or `--yolo` (a custom command keeps the flags it is written with; `cursor_force` does not change it), and every Cursor worker's `launched` event records the permission flags actually passed (`detail.permissions`). A custom command is read by POSIX quoting alone, running and expanding nothing: quotes, backslashes and line continuations count as `sh` takes them, an unquoted operator ends a word (`--force; true` passes `--force`), short switches may cluster (`-pf`), and every word of the line counts, so `rm -f x; agent ...` also warns, while a word built at run time (`$FLAGS`, `--fo$(:)rce`, bash's `$'--force'`, a wrapper script, a quoted `sh -c '...'`) is not seen. A malformed `channels.cli` is an error, never a silent fall-back to the default. **Known limitation: Cursor's sandbox may not start.** On Ubuntu 24.04, which restricts unprivileged user namespaces by default (the `kernel.apparmor_restrict_unprivileged_userns` sysctl is on), `agent -p --sandbox enabled` exits 1 before its first event: `Sandbox mode is enabled but not available on this system. Sandbox failed to start, possibly due to AppArmor configuration.` (agent 2026.11.05-86047df, a fresh linked worktree, 2026-11-05). On 2026-11-08 that same agent build started on a host where the sysctl was still 1: the turn reached `system/init` and exited 0. The AppArmor exit remains the failure mode of a host where the sandbox does not start. The default stays sandboxed: fix the host (https://cursor.com/docs/agent/terminal), or set `cursor_force: true` on the entry and accept the warning; the same turn under `--trust --force` edited a file, ran `pytest` and committed. A roster that hits this can opt the affected `cursor` entries in with `cursor_force: true`. Codex runs with `-c sandbox_mode=workspace-write -c approval_policy=never`, as config overrides because `codex exec` and `exec resume` take no `--ask-for-approval` (and `exec resume` no `--sandbox` or `-C`), as the codex-cli 0.166.0 capture under `model-profiles/harness-captures/codex/` shows.

**Cursor CLI, checked 2026-11-08** (agent 2026.11.05-86047df). These results are from the `agent` CLI. Findings about the Cursor IDE, including the composer-2.5 guidance-bypass replay, stay in the roster and model docs.

- **Model.** `system/init` carries `model`. `--model composer-2.5` reports `Composer 2.5`; `--model composer-2.5-fast` reports `Composer 2.5 Fast`. `same_model` treats each pair as the same model, and the fast display name does not match the plain id. A launch that omits `--model` still reports a model (on this account, `Composer 2.5 Fast`). Every turn in this check printed one. What the review gate does with a missing model stays the decision scheduled after 0.3.1.
- **Resume.** `agent create-chat` prints the chat id. `agent -p --resume <id> --trust --sandbox enabled` with a new prompt keeps that `session_id` and answers the new prompt (two prompts on one chat).
- **`--mode ask`.** The reviewer launch passes `--mode ask` and `--trust`, and passes neither `--sandbox` nor `--force`. Told to create a file, and told again to run a shell redirect, the turn wrote nothing and called no tool. It answered that Ask mode blocks writes, and it printed a command a person could run. That suits a reviewer: the turn stays read-only.
- **Commit in a linked worktree.** The documented default (`--sandbox enabled`, no `--force`) commits there. The shell policy is `TYPE_WORKSPACE_READWRITE` with the worktree as its writable root. In that same turn a path outside the workspace failed with `Permission denied`, so the commit ran inside the sandbox. The worktree gitdir and the common git dir's `objects`, `refs`, `logs` and a new file in the common dir were writable; `.git/config` returned `Read-only file system`. The default executor launch keeps its one `--add-dir`, the reviews directory. Cursor's sandbox already allows the commit, so the launch adds no git directory. M22.44's worker sandbox is the separate carve-out (objects, refs, logs, and `worktrees/<name>` only).
- **A denial is an event.** The CLI records the refusal on the shell tool result (`result.failure` when the command exits non-zero, or `result.success` stderr when the script continues) and the turn's own `result` line stays `success`. The adapter emits one `permission_denied` for a shell result whose stderr contains `Permission denied`, `Read-only file system` or `Operation not permitted`. The post-run check flags the worker from that event.

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

**What `max_workers` counts.** `delegate`, `message` and `resume` each refuse a turn when the workers already counted reach `policy.max_workers` (a resumed worker does not count itself, so an `idle` worker resumes in its own slot). Counted are this checkout's active records (any state but `failed` and `terminated`, less the orphaned `idle` or `completed` ones, below) in `work/.workers/`, which the main checkout and all its linked worktrees share, plus every **lease ref** on the integration remote (`remote` in `roadmap/git-workflow.yaml`) whose checkout id is not this one's, fetched (and pruned) into `refs/specy-road/known-leases/<remote>/` by every online `delegate`, `message`, `resume` and `worker sync` (a plain `git fetch` does not fetch them). Each launch or resume pushes `refs/specy-road/leases/<checkout-id>/<worker-id>` (a parentless empty-tree commit naming the worker) and counts again after the push, so of two checkouts launching at once neither goes over the limit (both may be refused). `adopt` pushes one too, with no recount (the session already runs); an adopt whose lease cannot be pushed is refused and its record closed. A `delegate` whose leaf already has a worker here returns it before any remote read, so a retry is answered while the remote is down. The checkout id is a uuid written once to `<git-common-dir>/specy-road-checkout-id`: linked worktrees share it with their main checkout, and a separate clone has its own. It is written to a temporary file and hard-linked into place, so it is never seen half-written and concurrent first calls agree on one. A file holding a valid id is only ever read, never moved or rewritten, so an id once returned stays the id. A missing, empty, unreadable or malformed file is uninitialized, never "no id": under the workers lock, after reading it again, a new id is installed from a temporary file (`os.link` when absent, which fails if the file appeared; `os.replace` over an invalid one; no lease can have been pushed under it); after any failure the file is read again and a valid id there is used, and a call that still has no usable id refuses the launch or resume. Branch names and claim owners play no part: a clone's worker counts wherever its branch also exists and whoever holds the claim. The lease follows the record: kept while `idle` or `handed_off` (an `idle` worker whose leaf is over has its lease deleted by the next `worker sync`), deleted when the record goes `completed`, `failed` or `terminated`. A later `message` or `resume` of a `completed` or `failed` worker pushes a new lease; a resume the limit refuses deletes that lease again. `completed` and `failed` are written and their lease deleted as one step under the workers lock (a turn that ends `completed`, the wrapper's nonzero exit and harness-start failure, and a dead wrapper's close), so a resume, which pushes its lease under that lock, never has its new lease deleted by the old turn's cleanup. `worker sync` makes this checkout's lease refs match its active records: it deletes refs whose worker is no longer active here (a crashed wrapper, a delete that failed) and, best effort, pushes one for each active worker without one (registered before leases existed, launched `--offline`, a push that failed); it reads the remote first, then rechecks each record and deletes and pushes under the workers lock, the lock every launch and resume pushes its lease under, so it cannot remove a lease being acquired. A repository without that remote pushes and reads no leases. Otherwise the turn is refused, and nothing is launched, when the remote rejects the lease push (`<remote> rejected the lease for W`) or cannot be reached (`cannot reach <remote> …; retry, or pass --offline`). `--offline` on `delegate`, `message` or `resume` is the explicit local-only escape: it neither fetches nor pushes, counts this checkout's workers plus the lease refs as last fetched into `known-leases` (refusing at that count), and prints one warning that the global limit was not verified, since a worker another checkout started after that fetch is not seen; other checkouts count its worker once a later online turn or `worker sync` pushes the lease. `--offline` is part of what an `--op-id` is bound to. Cost: a launch is one fetch, one push and one more fetch; a resume a push and a fetch; a close a push; `sync` one fetch (plus a push for any lease it repairs).

**Orphaned workers.** An `idle` or `completed` worker keeps its slot so a review `block` can resume it for a fix round. It is **orphaned**, and no longer counts toward `max_workers`, on any one of three causes, the same for the slot count, `list`/`sync` and `terminate --orphaned`: **unclaimed**, when at every integration ref that exists (the local integration branch and `<remote>/<branch>`) the registry is readable and has no claim on the leaf under any branch, whatever its status (a landed finish, `registry-prune --remove`, an abandoned leaf; only for a record that names the branch it was delegated under, as delegate and adopt always do); **Complete**, when at every such ref the roadmap is readable and says the leaf is Complete; or **worktree gone**, when the record's worktree is no longer a directory. The two ref causes need every existing ref to agree, so a stale snapshot can only keep a worker: a stale `<remote>/<branch>` still saying Complete or unclaimed for a leaf reopened and claimed since, or a landing not yet pushed and fetched, keeps it, and with no such ref, or one whose registry (roadmap) cannot be read, the unclaimed (Complete) cause is not judged. The caller's working tree is never read, since linked worktrees share the records and an older lane's registry is no authority. The reason lists every cause that holds. A `running` worker is never orphaned. Nothing is stored: each `list`, `sync`, launch and resume judges it afresh. At the limit the refusal names running and held workers apart, for example `` 3 workers active, policy max_workers is 3; 2 running: w-0002, w-0003; 1 completed: w-0001; `specy-road worker terminate w-0001` frees it, or wait for a running one to finish or raise the limit ``. `finish-this-task` terminates the finished leaf's own `idle` and `completed` workers; `worker terminate --orphaned` ends the rest.

**Waiting.** See [orchestration-worker-sync.md](orchestration-worker-sync.md) for `--wait`, `--until`, `--verbose`, and tool-use collapsing. In short: call `specy-road worker sync --wait` rather than sleeping; use `--wait --until completion` when you need the turn to end, not every tool-use line.

The worker's job is the executor's as before: implement, commit, write
`work/implementation-summary-<ID>.md` and `work/reviews/<ID>/READY-*.md`,
stop. A `completion` event says it stopped and whether READY exists; it is
**not** an approval. From there the review path is unchanged:
`review packet`, reviewer prompts, `review record`, `review status`,
`mark-implementation-reviewed`, `finish-this-task`.

**Backgrounded tests.** A `completion` with exit 0 and READY missing, after a final reply saying a test or verifier run is still going in the background ("I'll be notified when it finishes"), is a lost turn: a headless turn ends when the agent replies, and nothing resumes the session when the background job finishes. The executor prompt tells the executor to run the verifier and tests in the foreground for this reason. To recover, `worker message W --text` telling the executor to rerun them in the foreground, wait for them to finish, and then complete its steps. Claude Code launches set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` in the harness environment, executors (with `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`) and reviewers alike (`review delegate` and the default reviewer command, bare or explicit): otherwise `claude -p` stays open up to 10 minutes of idle after its reply for background work it started (harness-facts).

**Post-run check and usage limits.** After every turn, whatever its exit code, the wrapper reads the turn's events and the worktree's git state against the state at the turn's start (`specy_road/orchestration/workers/worker_turn_check.py`). Findings: permission denials (Claude's result `permission_denials`, one `permission_denied` event each), a Cursor question-tool call (one `interactive_tool` finding per turn, naming the tool and that no person saw it, however many such `tool_call` lines the stream holds), a failed turn (an error no completed turn followed, or a non-zero exit, a SIGKILL included, that no usage limit explains; the check is written before the turn's exit event, so it names the exit itself), api retries (`system/api_retry`), a branch change, a HEAD that is not a descendant of the turn's start (reset, rebase, amend), commits outside the leaf's touch zones, a changed stash list (the stack is shared by every worktree of the repository, so another session's stash shows too), and dirty paths beyond the leaf's bookkeeping that are new, changed or gone during the turn (a file already dirty at the start and edited again counts, and so does pre-turn work the turn restores, deletes or commits). Every turn records exactly one `post_run_check` event, a clean turn included (empty `findings`, summary `post-run check: clean`); findings flag the worker `post_run_findings`, which `worker sync` and `list` show, and a clean turn clears the flag. A usage limit is read from the text, never the exit code: a Claude result whose text names a limit (a successful one only with a reset time), a Claude turn that exited non-zero with no result line whose session transcript (`~/.claude/projects/<project>/<session-id>.jsonl`) ends in an assistant message naming a limit (the prompt is never read), a Codex `turn.failed`/`error` with limit wording and its "try again in/at" time, or a turn that ended after `rate_limit` retries with no completed turn. The **retry watchdog** stops a harness whose `rate_limit` retries announce more than 600 s of waiting in one turn (SIGTERM; Claude exits 143 and the turn is lost, the session kept) rather than letting it wait out a usage limit. Such a turn ends in `paused_by_limit` with `limit_reset_at`, even when it exits 0 with a fresh READY (its `completion` event still records `ready`); the worker keeps its slot and lease, and `resume` / `message` refuse it until that time (at once when no time was named), then resume the same session with the same launch flags.

**Killing by pattern.** An executor clearing its own stray test run with `pkill -f "pytest -q"` also ended the coordinator's and other leaves' pytest runs (SIGTERM, no failure reported), since sessions share the machine. The executor prompt forbids kills by name or pattern and allows stopping only a process the executor started, by the pid it recorded.

**Parallel tests.** Concurrent executors and reviewers share the machine's CPU, and each one running the full suite with one test worker per core (`pytest -n auto`) oversubscribes it: with several of them the load average runs well past the core count, the landing suite takes several times as long, and a reviewer's run can outlast its harness's background-task limit and be killed. Add a **`checks:`** entry with `when: prompt` in `roadmap/git-workflow.yaml` for the leaf-level test command with a small worker count (for example `python -m pytest -n 4 -p no:cacheprovider`): executor briefs and reviewer prompts give it as the command to run the leaf's tests, with the test paths appended. Keep the full parallel suite in an entry with `when: land`, which runs once per landing on the merge commit ([git-workflow.md](git-workflow.md#checks-checks)). Without a `prompt` entry the prompts only say to cap parallel test workers when other workers share the machine.

| Command | Does |
|---|---|
| `list [--all]`, `status W`, `events W [--since N]`, `open W` | Read. `open` prints the worktree, the log, and the native resume command. `list` marks each orphaned worker `orphaned: <why>` (`orphaned` in `--json`, `null` otherwise). |
| `sync [--ack] [--wait [--until TYPES] [--timeout S]] [--verbose]` | Every worker's events after the last acknowledged one (`work/.workers/sync.yaml`, per worker the acked `seq` and `acked_at`); compact, with state, lease, epoch and flags. When a follow-up is waiting for the current turn to finish, the worker's `queued_message` is shown too. A sequence number between the last acknowledged one and the record's `last_event_seq` that no readable line carries (lost or unreadable, the final event included) is reported as a gap (`! gap: event(s) #4–#5 …`; `gaps` in `--json`); a worker whose new events are all unreadable is still listed, and `--ack` moves past its gaps. `--wait` blocks until there is something to report ([orchestration-worker-sync.md](orchestration-worker-sync.md): `--until`, `--verbose`, READY-only hint); exit 2 when `--timeout` passes with nothing. Every orphaned worker is listed after the events, new events or not (`orphaned`, worker id to why, in `--json`). |
| `message W --text\|--file` | A follow-up: resumes the native session with the text when the wrapper is stopped. While a turn is still running, the text is stored on the record as `queued_message` and delivered as the next turn when the wrapper finishes (`message_queued` in the log); a second message during the same turn is appended, separated by a blank line, and the event summary says `appended`. When that delivery fails, the text stays and `message_undelivered` is set; the next `message` or `resume` sends the stored text, a blank line, then its own prompt. `list` and `sync` show it. `--no-queue` keeps the old refusal for a live turn. Needs the `broker` lease. |
| `resume W [--ready-only]` | `message` with a "continue from where you stopped" prompt, or with **`--ready-only`** a short prompt to write READY for HEAD only (after a completion reported READY missing). Both resume a worker in `idle`, `completed` (a review `block` goes back as a message) or `failed` **with** a `provider_session_id` (a crashed or hand-killed turn keeps its session, and is refused while another worker holds the leaf). Every resumed turn takes a `max_workers` slot like a launch: refused when the other counted workers already reach the limit. Refused: `failed` with no session id and `terminated` ("delegate again instead"), `handed_off` (`WORKER_LEASED_BY_HUMAN`), and a live process — `stalled` included, which becomes resumable once its harness exits or is stopped (the wrapper then records `failed`; `recover` ends and resumes it in one step; `terminate` instead closes it for good). `--no-queue` applies only to `message`, not `resume`. |
| `recover W [--offline]` | One shot for a `stalled` worker: ends its process group as `terminate` does (also when its wrapper already died and its harness lives on) and, once the group is confirmed gone, drops what that turn left behind as `terminate` does: the `wrapper_gone_harness_alive` flag and the worker's own presence session; it leaves the record resumable (it goes `failed` with its session), keeps the worktree and its commits and uncommitted files, and resumes the native session with the `resume` prompt. Refused, with nothing ended, when the worker is not stalled, another active worker holds its leaf, it has no session its harness can resume, or its lease is not the broker's. Bounded: `recoveries` on the record counts every run, across processes, up to `policy.max_fix_rounds` (default 3); past it the call refuses, flags the worker `needs_person` with one `error` event naming its last output, and leaves it running. Runs under the workers lock, so two recoveries never overlap. A recovery is counted when it ends the turn; when the resume is then refused (an unreachable lease remote, a launch, slot or branch check), the worker is left `failed` with its session and the recovery **pending**: the next `recover`, online or `--offline` (or `grind-session`'s next pass), finishes it without counting it again. See "Stalled workers". |
| `interrupt W` | **Unsupported** by every CLI adapter: exit 2 and the reason. A kill is not an interrupt; use `terminate` and say so. |
| `terminate W` | SIGTERM the recorded process group (wrapper, harness and children), SIGKILL after 5 s, and confirm the group is gone — also when the wrapper itself already died, while the harness still matches its start time and the verified wrapper or harness is still in the recorded group; state `terminated`. The turn is lost. Any `queued_message` is dropped and `message_undelivered` is cleared; the `terminated` summary notes the dropped text. While the record still holds the turn's process group, the presence session the harness started in the worker's worktree (`<user>-s<pgid>`: the wrapper leads its own POSIX session and drops `SPECY_ROAD_AGENT_ID`) is ended; another agent's session there is left alone. `terminate --orphaned` (no `W`, no `--op-id`) ends every orphaned worker in one step and prints each with its reason. |
| `handoff W` / `reclaim W [--note]` | Lease to a human and back; below. |
| `adopt --node ID --harness H --session SID` | Register a session the user started natively; lease `native`, observe only. Refused while the leaf has an active worker, and for an id that is not the harness's own shape (a UUID for Claude Code and Codex; shell-safe characters for all). |
| `reconcile W` | Paths changed since the checkpoint, and over the worker's whole lifetime (from the HEAD it started at), vs the leaf's touch zones as its claim row holds them now (`edit-node` keeps the row in step) — a rename or copy counts on both sides, so a `git mv` into the zone is still a change outside it, while a path that no commit on the branch's own (first-parent) line changed, nor the uncommitted tree, came in only through a merge and is not counted (a merge's own edits do count: what it changed against its first parent, less what another parent brought in and it kept unchanged, both sides of a rename included); and whether the leaf's own contract changed: its execution target (goal, acceptance, touch zones) and its planning sheet in the brief, not statuses or the sections that move with the integration branch (a prompt that can no longer be built for this model counts as changed). Sets or clears `needs_reconcile`. The leaf's brief, summary and prompts, the toolkit's state under `work/`, and `roadmap/registry.yaml` never count; any other `work/` file does. |
| `timeline W\|NODE_ID` | Seconds per phase of the latest turn (a node id means its latest worker): delegated → `launched`, `launched` → `first_output`, `first_output` → turn end (`turn_completed`, `completion`, or an `error` carrying `detail.exit`, which includes a harness that could not start), end → the `sync --ack` that covered it; `unknown` when a boundary event is missing. `--json` prints the same object. |
| `usage W\|NODE_ID` | Per attempt (a node id means every worker on it): model, harness and version, `usage` events counted as turns, and each figure summed over the turns that reported it (`?` when none did; partial sums are lower bounds), then the node's total. `--json` prints the same object. To browse the timeline, usage and event log per worker instead, open the PM GUI's read-only **Workers** drawer ([pm-gui.md](pm-gui.md)). |
| `hook --format H [--print-config]` | The prompt-submit hook body; below. |

## Stalled workers

A `running` worker silent for `policy.stall_after_seconds` (default 600) is flagged `stalled`, measured from its last stdout line or the `message`/`resumed` event that started its current turn, whichever is newer, or from the first turn's launch when there is neither. `recover` clears `stalled` in the same step that counts the recovery, so a second `recover` queued behind it finds the fresh turn not stalled and neither ends it nor spends a retry. Every `worker sync`, `worker list` and `specy-road doctor` sweeps for it and ends with one line per stalled worker: `stalled: W (NODE) silent Ns, recoveries n/limit — specy-road worker recover W` (`--json`: a `stalled` list with `silent_seconds`, `recoveries`, `recovery_limit` and `needs_person`). Doctor only reports it.

`specy-road worker recover W` acts on the flag once and exits; there is no daemon or background loop (principle 5). A person, the coordinator or `grind-session` calls it: `grind-session` runs it for every stalled worker at the start of each cycle and, in manual mode, once a minute while it waits for the ready signal, emitting `worker_recovered`, `worker_needs_person` or `worker_recover_refused` per worker; a worker already flagged `needs_person` is not retried. Pending recoveries are listed (`recovery pending: W (NODE) recovery n/limit ended its turn but the resume did not start`, `--json` `pending: true`) and retried the same way; `grind-session` always recovers online, so while the lease remote is unreachable each pass reports the refusal and the recovery stays pending (run `worker recover W --offline` to finish it without the global count). Pending means the recovery's event is newer than the worker's last `message` event, which is written before every spawn; a spawn that fails after that event counts as started. Some harnesses print nothing for long stretches while working; raise `policy.stall_after_seconds` for them rather than recover a busy worker.

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
before its first signal, lists them again at every step, and signals those outside the group together with the group (SIGTERM, then
SIGKILL after the same grace; each only while its start time still matches, so a reused pid is never signalled). Each listing walks
parent links from the group, from every descendant already found and from recorded pids no process holds now, so a child forked
during the grace by one already found gets the SIGKILL. A zombie (state `Z`, waiting for its parent or a subreaper) counts as gone,
and a survivor makes it fail instead of reporting terminated. The record carries `descendants_unchecked: true` from the start of
that pass until it ends with every listing read and no survivor; while it is set, `terminate` fails without terminating, and the
next one repeats the pass (it finds only descendants whose parent link still holds). It cannot see a process already re-parented before that snapshot: after a `kill -9` of the harness or the
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
| `cursor` | `agent create-chat` first (in the worktree), then `agent -p --resume <chat> --output-format stream-json --trust --sandbox enabled --model … --workspace <worktree> "<instruction naming the prompt file>"`: `agent -p` documents no stdin, so the prompt stays in its file and the one short argument tells the agent to read it, on launch, resume and the `--mode ask` reviewer alike ([`orchestration-harness-launch.md`](orchestration-harness-launch.md)); never `-w`/`--worktree` (a `channels.cli` that passes it is refused). In a **linked** worktree it also passes `--add-dir` with the main checkout's `work/reviews/<ID>/` (an extra workspace root, from `agent --help`, 2026.10.22), on launch and resume. | chosen up front (`create-chat`) | `agent -p --resume <id> … --trust --sandbox enabled …` (print-mode resume with a new prompt keeps the chat id and answers the new prompt, agent 2026.11.05-86047df, 2026-11-08; the prompt file is named, as on launch. A linked-worktree commit under this sandbox needs no git `--add-dir`: see Cursor CLI, checked 2026-11-08) | unsupported | `agent --resume <id>` |
| `generic` | `channels.cli` / profile `access.cli` with `{prompt}` (the prompt file path) or `<prompt>` (the prompt text, as the shipped profiles write it): a command whose one argument would exceed the OS limit of **128 KiB** is refused before it runs, naming the size and the `{prompt}` fix ([`orchestration-harness-launch.md`](orchestration-harness-launch.md)); `{reviews_dir}` as for any `channels.cli` | none | unsupported | unsupported | none |

**Known limitation (Codex inside Codex).** A `codex` worker delegated from inside a coordinator's own `codex exec --sandbox workspace-write` session exits 1 before its first event (`failed to initialize in-process app-server client: Operation not permitted`, codex-cli 0.165.0, 2026-11-04 replay).
Run a Codex coordinator outside that sandbox, or delegate Codex workers from a terminal or another harness.

Whatever the harness, the wrapper's own command line carries only the repo
root, the worker id, a token and the path of a mode-0600 launch file under
`work/.workers/` (argv and the stdin prompt), which the wrapper reads once
and deletes; a brief of any size reaches a stdin-reading harness.

Flags match the accepted `--version`/`--help` captures under `model-profiles/harness-captures/` (Claude Code 2.1.329 and Cursor agent 2026.11.17-f532c45, captured 2026-11-19; codex-cli 0.166.0, captured 2026-11-02) and will drift; `upgrade --only profiles --capture <harness>` classifies a newer capture, and
`tests/flows/worker/test_worker_adapters.py` and `tests/flows/worker/test_worker_turn_check.py` pin the command shapes. The long-lived protocols (Codex app-server, Cursor ACP, Claude Agent SDK) are what would add interrupt and steer; they are later adapters behind the same
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
   resumed run carries the same `session_id`. Checked on agent 2026.11.05-86047df
   (2026-11-08): `agent create-chat`, then `agent -p --resume <chat>` with a new
   prompt, keeps that id and answers the new prompt. If a later build does not,
   set `channels.cli` with `{session}` to a command that works, or treat Cursor
   workers as one-shot.

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
  across its turns). Only the entries below reach your copy. The table in `specy_road/orchestration/workers/worker_sandbox.py`
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
  worker gets its own copy of these, made from yours on its first turn. The `$CLAUDE_CONFIG_DIR/.claude.json`
  copy (from `~/.claude/.claude.json` when the variable is unset) is made again when the config directory
  changes, or when no directory was recorded for it. The directory is resolved before it is recorded, so
  another spelling of the same directory, such as `account/../account`, keeps the worker's copy. A
  copy of a file inside a replaced directory (Cursor's `cli-config.json`, `$CLAUDE_CONFIG_DIR/.claude.json`)
  is a plain file in the worker's own directory, so the harness can replace it by rename (Cursor does on
  every start); `~/.claude.json` is bound over yours.

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

## Interfaces and limits

**`worker list --json` and `worker status W --json` are a stable interface** for watchers (a dashboard, a coordinator script): read them instead of the files under `work/.workers/`, whose layout may change. `worker list --json` prints `{"workers": [...]}`, one object per worker (the active ones; `--all` adds closed ones): the record's fields from "The model" (`worker_id`, `node_id`, `harness`, `model`, `state`, `worktree`, `lease`, `flags`, …), plus `alive` (the wrapper is running) and `orphaned` (`null`, or why its leaf is over); a `stalled` list is added when a worker is stalled (see "Stalled workers"). `worker status W --json` prints one such object, without `orphaned`, plus `recent_events`, the last few events in the event-log shape. Fields are only added, never renamed or removed, within a release line; the text output is for people and may change.

**A claim locks development work, not a runtime resource.** A leaf's registry claim and its branch say who is changing which touch zones; they reserve nothing the code uses when it runs (a port, a database, a device, a staging environment, an API quota). `orchestrate plan` and `grind-session --plan` schedule leaves by their dependencies and their touch zones only: two ready leaves that share a zone never go in one parallel batch, but two leaves that both start a server on port 8000 can. Where leaves contend for a runtime resource, say so in the graph (a dependency between them, or a shared touch zone such as the resource's config file), or set `policy.max_workers` low enough.

**A gitignored `roadmap/` needs a force-added `roadmap/orchestration.yaml`.** Routing (`orchestrate plan`, `prompt`, `worker delegate`, `review delegate`, `grind-session`) reads the roster from the integration branch (`origin/<integration>`), never from the working tree. In a repo whose `.gitignore` covers `roadmap/`, the roster you wrote locally is not on that branch, so routing finds no roster. Add it past the ignore rule and push it to the integration branch: `git add -f roadmap/orchestration.yaml`, commit and push. A model profile under an ignored path needs the same, since routing reads the committed profiles too.

**A Codex executor needs `channels.cli` to commit.** Under the default command, codex-cli's `workspace-write` sandbox keeps git metadata read-only, so the worker implements and tests but cannot commit; give the roster entry a `channels.cli` and `cli_resume` that grant both git directories ("Known limitation" under "Roster setup").

## Optional: refuse push from a linked worktree

`specyrd init --install-pre-push-hook` installs `specy_road/templates/specyrd/hooks/pre-push` as `.git/hooks/pre-push`; it refuses push when the repo toplevel is under `work/.worktrees/` and allows push from the main checkout. `worker delegate` and `review delegate` export `SPECY_ROAD_ORCHESTRATION_ROLE` (`executor` / `reviewer`) into the harness environment so the shipped orchestration hooks apply without pinning the role in the command.

## Working alongside sessions and the gate

`review status` prints active workers beside live sessions. A session whose recorded worktree is no longer a directory, or whose recorded branch has no local ref, no longer counts as live (guard, overlap warnings, `review status`); `session list --all` shows it as `stale: worktree gone` or `stale: branch gone`. Both are judged only when the record names both: a session missing either, or holding a value that is not a string, still lasts until it expires. A worker in a linked worktree does not touch the coordinator's branch; one in the same checkout (the claim's branch was checked out here) does, so the coordinator must not edit files in that leaf's touch zones while the worker runs — the presence guard (`session guard`) already refuses the git operations that would collide. Finishing the leaf is still `finish-this-task` from the leaf's branch after the gate; it terminates the leaf's own `idle` and `completed` workers (a `terminated` event each; a running one is left alone), so their records close and their slots free. With `--on-complete merge`, finish merges into the integration branch and **pushes that branch** (after stating how many local integration commits are not on the remote yet); `--push` only pushes the feature branch. From a linked worktree with `on_complete: merge`, finish cannot check the integration branch out while the coordinator's checkout holds it, so it merges and pushes **in that checkout** instead. That checkout must have no uncommitted changes to tracked files (untracked files are fine): otherwise finish refuses before its bookkeeping commit and names the checkout to commit or stash in.

## The roster: building and trying it

Beside [orchestration.md](orchestration.md) (roles, the review gate, the
`roadmap/orchestration.yaml` reference) and
[orchestration-models.md](orchestration-models.md) (profiles, `prompt`,
`orchestrate plan`). Routing reads `roadmap/orchestration.yaml` from the
integration branch (`origin/<integration>`), never from the working tree: a
roster entry's `channels.cli` and its profile's `access.cli` are executed, so
the copy that runs is the one that was reviewed and merged. This part covers
trying a roster change on your own clone before it lands, building a roster in
one command, and the two `orchestrate plan` choices that depend on it.

### A dry-run plan from the working tree

```bash
specy-road orchestrate plan --roster-from-worktree
```

plans with the working tree's `roadmap/orchestration.yaml` and the working
tree's model profiles. The first line is

```text
DRY RUN: roster from the working tree, nothing may launch from this plan
```

and `--json` carries `"roster_ref": "worktree"` (the banner goes to stderr so
stdout stays JSON). Only `orchestrate plan` accepts the flag: `prompt`,
`worker delegate`, `review delegate` and `grind-session` always read the
integration branch's roster, so a dry run cannot launch anything.

### `models list` names the ref and the uncommitted diff

`specy-road models list` starts with the ref it read the roster from
(`roster: roadmap/orchestration.yaml at origin/dev`). When the working tree's
roster differs from that ref, it ends with `uncommitted roster changes`: the
entry ids added, removed and changed, each changed id with the fields that
differ. `--json` has the same as `roster_ref` and `uncommitted_roster_changes`
(`{added, removed, changed: {id: [fields]}}`, or `null` when they agree). The
rows themselves stay the roster routing reads.

### Local roster entries (`roster_add`)

`roadmap/orchestration.local.yaml` is gitignored and already overlays
availability (`roster:` with `available` / `paused_until` by `id`; see
[orchestration.md](orchestration.md#roadmaporchestrationyaml)). It can also add
whole entries for this clone only:

```yaml
roster_add:
  - {id: local-qwen, family: qwen, roles: [executor], class: cheap}
# allow_local_cli: true   # channels.cli, cli_resume, preflight, harness_bin, cursor_force, or a profile access.cli
```

- Each entry is checked against the roster entry schema. Added entries follow the
  integration branch's, and `orchestrate plan`, `prompt`, `worker delegate` and
  `review delegate` on this clone use them; `orchestrate plan` labels them
  `[local]` and lists them on a `local roster entries` line (`local_roster` in
  `--json`).
- An added entry never overrides a committed one: an `id` the pinned roster
  already has is refused, and routing stops with that error until it is renamed
  or removed. Use `roster:` in the same file to change a committed entry's
  availability.
- An added entry that would run a command on this clone is refused unless the
  same file sets `allow_local_cli: true`. That is a non-empty `channels.cli`,
  `channels.cli_resume`, `preflight` or `harness_bin`, `cursor_force: true`, or
  a profile whose `access.cli` is set.
- The review gate reads only the committed roster, so a review by a local
  entry does not count toward it.
- An added entry may not set `allow_guidance_bypass_model` (below): routing
  stops with that error, and nothing is launched.

Out of scope: sharing local entries between clones. Commit them to the
integration branch to share them.

### A roster in one command: `models roster`

```bash
specy-road models roster --executor claude-opus-5-5 --reviewer gpt-6.1-sol
specy-road models roster --executor composer-2.5 --reviewer claude-opus-5-5 --write
```

Each `--executor`, `--reviewer` or `--coordinator` names a shipped profile by
its file name (`specy-road models list` lists the profiles; an `api_id` or alias
works too) and may be repeated. A profile named for several roles becomes one
entry with all of them. Each entry is filled from the profile:

```yaml
  - id: claude-opus-5-5
    family: anthropic
    profile: model-profiles/anthropic-claude/claude-opus-5-5.md
    harness: claude-code
    roles: [executor, reviewer]
```

- `id` is the profile's file name, so review records and the gate count the
  same id the profile carries;
- `family` is the roster family the profiles README gives that vendor (the gate
  counts distinct families by it);
- `profile` is the path form `validate` accepts;
- `harness` is the harness whose executor template renders the profile's
  family (`claude-code`, `codex`, `cursor`), else `generic`, which runs the
  profile's `access.cli`.

Without `--write` the entries are printed for you to paste under `roster:`.
With `--write` they are added to the end of the `roster:` block of
`roadmap/orchestration.yaml`, keeping its comments; an id already rostered is
left alone. Run `specy-road validate --generate-orchestration` first when the
file does not exist. An unknown profile id is refused with the nearest ids. When
the repo lacks a profile file the entry points at, the command says to run
`specy-road refresh-profiles --only <id>`, the deprecated alias of
`specy-road upgrade --only profiles --profile <id>`. Commit the roster (and the profiles)
to the integration branch: routing reads the committed copy.

### `profile:` is checked locally

`validate` resolves every roster `profile:` against `model-profiles/` in the
working tree. A value that is not a `.md` file there, such as
`anthropic/claude-opus-5-5`, is a warning naming the accepted form, with the
concrete path when the value's last part names a known profile:

```text
warning: roster entry 'opus' in roadmap/orchestration.yaml: invalid profile: anthropic/claude-opus-5-5, accepted form model-profiles/anthropic-claude/claude-opus-5-5.md
```

`orchestrate plan` reports such an entry the same way (`invalid profile: <value>,
accepted form <form>`) rather than as a profile "not committed on the
integration branch", and leaves out the `no eligible executor … may_process`
hint when that drop is the only reason no executor is left.

An entry without `profile:` gets the first profile whose `api_id`, file name or
alias equals its `id`; only when none does, the first that equals its
`harness_model` (an id match wins). Matching neither, `validate` warns that
its model notes never reach its prompts.

### The coordinator

With no roster entry holding the `coordinator` role, `orchestrate plan` prints
`coordinator: this session` for each leaf: the session that runs the plan
coordinates, and the plan does not count that as a staffing problem. To roster a
model coordinator instead, give an entry the role, for example
`specy-road models roster --coordinator claude-opus-5-5 --write`, or add
`coordinator` to an existing entry's `roles`, and commit the roster. The plan
then picks the rostered coordinator with the highest coordinator score that is
available and may process the leaf's `sensitivity`; when coordinators are
rostered but none qualifies, the leaf is reported as unstaffable.

### Models observed to bypass the guidance (`allow_guidance_bypass_model`)

A model profile can record `guidance_bypass_observed` ([orchestration-models.md](orchestration-models.md#guidance-bypass-observed)):
the model was seen going around specy-road's guidance. The shipped flag is on **composer-2.5**
(its alias `composer-2.5-fast` too), from the 2026-11-05/06 replay through Cursor; it is a finding
about that model, not about the Cursor harness, and `composer-2` is not flagged.

While `policy.signed_reviews` is on, an entry is flagged when any model it can launch (its profile's
`api_id` or alias, `harness_model`, the roster id, or a literal `--model` / `-m` in `channels.cli`,
`cli_resume` or the profile's `access.cli`) matches a flagged profile on the integration branch or in
the bundled set; a project or branch copy
without the field does not clear it, and the committed copy of the entry's profile names its model even
when the working tree's copy differs. A git or file read that fails while reading those profiles
refuses the entry rather than reading as "not flagged"; a committed profile whose front matter does not
parse flags nothing and is refused as an invalid profile wherever it is routed. A flagged entry is excluded from the executor and reviewer roles
and stays eligible as coordinator. `validate` and `doctor` print one warning per flagged executor or
reviewer entry:

```text
warning: composer-2.5 (model composer-2.5) is excluded: set allow_guidance_bypass_model: true on its roster entry to use it at your own risk
```

The rule is bounded: it covers declared configuration, not a model hidden in a custom command. It
reads the profile's `api_id` and aliases, `harness_model`, the roster id, and the literal model flag of
`channels.cli`, `channels.cli_resume` and the profile's `access.cli` (every committed copy included),
and compares names after normalising (case and separators, and Cursor's `cursor-` prefix, so
`COMPOSER-2.5`, `Composer_2.5` and `cursor-composer-2.5` all match `composer-2.5`). A model flag it
cannot read is refused as `<id> (model unreadable in <field>)`: a command readable for this is one
simple command with one literal `--model <id>`, `--model=<id>` or `-m <id>`, so a flag inside a list
or pipeline (`cd . && agent --model …`), a substitution or variable (`"$(printf …)"`, `"$M"`), an
attached `-m<id>`, two model flags, or a command that cannot be split (an unbalanced quote) is
refused, and only the committed opt-in admits it. A `family: human` entry is exempt only without
launch configuration: one that sets `harness`, `harness_model`, `harness_bin`, `profile`,
`channels.cli` or `channels.cli_resume`, or whose id finds a profile, is judged like a model entry,
committed or `roster_add` alike (`channels.paste`, `channels.subagent` and `preflight` launch no
model). The exemption is decided only from a successful read of the integration branch's profiles:
while that read fails, a human entry is refused like every other, since whether a profile answers to
its id is unknown. The rule does not see a model chosen inside a script, wrapper or alias the command runs, by
an environment variable, by a harness's own config file, or by a harness's default when no model is
passed; nor an abbreviated long option (`--mod`). The coordinator role, how signatures are verified,
and the roster schema are unchanged.

To use it anyway, at your own risk, set the opt-in on its entry in the committed roster:

```yaml
  - id: composer-2.5
    family: cursor
    roles: [executor]
    harness: cursor
    allow_guidance_bypass_model: true   # boolean, default false
```

Only the committed `roadmap/orchestration.yaml` on the integration branch counts (a `roster_add`
entry is refused, and `orchestrate plan --roster-from-worktree` ignores an uncommitted opt-in);
protect that file with a code owner, since an executor that can push there could
set it. `validate` and `doctor` then print `warning: <id> (model <api_id>) opted in at its own risk`,
`orchestrate plan` adds the same warning to its notes, and every executor or reviewer launch prints it
once. With `signed_reviews` off none of this applies.

### Spreading executors: `orchestrate plan --spread`

By default every leaf goes to the cheapest capable executor (the ranking in
[orchestration.md](orchestration.md), "Executor ranking"), so one model can
receive every leaf of a long grind. `--spread` assigns executors round-robin
instead: the capable, available entries for a leaf are ranked the same way, and
the leaf at position *i* in the plan (batches in order, then leaves within a
batch) takes entry *i* modulo their number. The assignment is deterministic for
a given roadmap and roster. It does not weigh cost or current load.

## Chores: worker-run work outside the roadmap

A chore is environment repair or other ad-hoc work that should run on a worker, with its usage and review recorded, but has no roadmap leaf. `specy-road chore start <slug> --task TEXT --zone PATH` writes `work/chores/<slug>.json` in the main checkout: no roadmap node, branch or registry row. The chore runs in this checkout (or `--worktree`) on the branch checked out there, and `base` is that branch's head at start. `worker delegate <slug>`, `worker usage <slug>` and `review delegate <slug>` take the slug where they take a node id; `worker message`, `resume`, `sync`, `reconcile` and the rest work on its worker id as for a leaf. `--zone` (repeatable) declares touch zones as a leaf does: `worker reconcile` flags a change outside them (`needs_reconcile`).

### Starting

```bash
specy-road chore start fix-env --task "Repair the pinned toolchain" --zone scripts/ --zone .tool-versions --review
```

The slug is lower-case letters, digits and `-`, never a node id and never
starting with `w-` (a worker id). The checkout must be on a branch, not a
detached head. `--model` and `--harness` set the defaults `worker delegate
<slug>` uses. The model may be off the roster (`roadmap/orchestration.yaml`) when
`--harness` names where it runs (`claude-code`, `codex`, `cursor`); such a
model runs with the harness's default command and no roster checks. A rostered
model keeps its roster harness, profile and executor-role checks.

### Running

```bash
specy-road worker delegate fix-env            # the chore's --model, or pass --model ID
specy-road worker sync                        # as for any worker
specy-road worker reconcile w-0007            # changed paths since base vs the chore's zones
specy-road worker usage fix-env               # tokens and cost per attempt, and the total
```

The executor's prompt is the task, the zones and the commit rules; it has no
brief. The tree must be clean, as for a leaf: delegate refuses uncommitted
changes. A chore's worker is never reported orphaned for lack of a claim; once
the chore is closed, a worker still held on it is.

### Review

With `--review`, `specy-road review delegate fix-env --model <reviewer>` runs a
rostered reviewer in the chore's worktree on `git diff <base>..<head>`. Its
prompt names `work/reviews/<slug>/REVIEW-<model>.md` and the record's form, with
the task as acceptance `A1`. The run is `complete` once a valid record for the
current head is on file. There is no gate: the verdict is recorded, not enforced.

### Closing

```bash
specy-road chore close fix-env --summary "Pinned toolchain repaired; make check passes"
```

`work/chores/<slug>.md` holds the task, worktree, branch and `base..head`, the
zones, the summary, `worker usage`'s lines for every attempt, and one line per
valid review record (`<model>: approve|block at <commit>`), or `unreviewed`.
The chore's JSON keeps `closed_at`, so the slug cannot be started again.

### Gardening

```bash
specy-road chore garden                                   # report: one finding per line
specy-road chore garden --json                            # the same, for machines
specy-road chore garden --open-chores --under M12         # also file each finding class as a leaf
```

`chore garden` finds drift between what the toolkit enforces and what the docs
and agent files claim. Each finding is one line, `<class>: <path>:<line>: <detail>`,
with paths relative to the git root; the exit code is 0 whether or not there are
findings, because it is a report. It edits nothing tracked.

| Class | What it reports |
| --- | --- |
| `stale-command` | A `specy-road` or `specyrd` command this version does not register, named in `docs/**/*.md`, `AGENTS.md`, `CLAUDE.md` (project and git roots), `.specyrd/AGENTS.md` or `.specyrd/AGENTS.team.md`. It is the scanner `validate` runs on the agent files, over more files and over whole files, managed blocks included (`validate` skips those); it checks command names, not flags. |
| `advisory-rule` | A provenance comment (`<!-- prevents: … \| enforced: advisory … \| ref: … -->`) in a managed agent file, or in `specy_road/agent_rule_provenance.md` (the maintainers' copy of the templates those files are rendered from, which no wheel ships) when it is in this checkout: one line per rule nothing checks. |
| `ratchet-grew` | A `policy.ratchet_paths` baseline with lines added since the newest tag (`git describe --tags --abbrev=0`), reported as `<path>: +N line(s) since <tag>`. With no tag, or no integration branch to read the policy from, the scan reports nothing and says why once on stderr. |

`--open-chores --under <PARENT>` adds at most one leaf under `PARENT` per class
with findings by running `add-node` itself, so every check `add-node` makes
applies (parent exists, milestone lock, unique id, title and codename, chunk
routing). The leaf gets its title from the class (for example `Garden: stale
command mentions`), codename `garden-<class>`, one acceptance line per finding
path (the first 10, then a count of the rest) and the finding paths as touch
zones. A node belongs to a class when its codename (`garden-<class>` or
`garden-<class>-N`) or its title (`<title>` or `<title> (N)`) says so, under
any parent. While a live leaf of the class is not Complete, a run adds nothing
for it and prints that leaf's id. Otherwise the new leaf is generation N + 1,
where N is the highest generation any live or archived node of the class
carries, so a number is never reused. When `add-node` refuses, the run exits 1
with its reason. The leaves are picked up,
delegated and reviewed like any other; gardening never fixes a finding itself.

#### Cadence

```yaml
# roadmap/orchestration.yaml
policy:
  garden_cadence_days: 14
```

Each run records its date in `work/chores/.garden.json`, which the managed
`.gitignore` block ignores (`specy-road upgrade` adds the line to an older block). With `policy.garden_cadence_days` set, `specy-road validate`
warns "gardening due: last run <date>, every N days; run `specy-road chore garden`"
once more than N days have passed, or `never run` when there is no record. The
warning is never fatal; unset, there is none.

#### Unattended

Run the report on a schedule and let a person or coordinator decide what to file:

```bash
# cron or a scheduled CI job, from the checkout root
specy-road chore garden --json > work/garden-report.json
# then, after reading it
specy-road chore garden --open-chores --under <PARENT>
```

Each run, report or not, resets the cadence clock.
