---
description: "Use when running many roadmap leaves in a loop or planning sub-agent batches: --plan for read-only dependency waves, --step pickup/finish from an IDE session, hook mode in a terminal. Never hand-edits the registry."
---

```bash
cd "$(git rev-parse --show-toplevel)"
specy-road grind-session --plan --json
```

`grind-session` wraps the **approved** primitives (`do-next-available-task` →
implement → optional pre-finish hook → `finish-this-task`) across many leaves. It
**never edits `roadmap/registry.yaml` directly** — do not hand-edit the registry;
let these commands manage it.

### Plan first (read-only — no git)

`--plan --json` reports `ready` / `blocked` / `active` leaves plus dependency **waves** and
**parallel_batches**. For sub-agent orchestration:

- Spawn one sub-agent per node in `parallel_batches[0]` (they are independent —
  run them concurrently).
- **Do not** start a node in a later wave until every node in the previous wave is
  `Complete`. Re-run the planner after each wave.
- **Never** start a node listed under `blocked` / `gated`; gates need a human.

This prevents dispatching a sub-agent for work whose dependencies are unmet (e.g.
`M11.1` while `M10.5` is still in flight).

### Drive the loop from this session (step mode)

Step mode is the in-pane path: this session is the coordinator, and each
`--step` runs one phase and exits. Repeat until pickup exits `2` or `3`:

1. **Pick up.** `specy-road grind-session --step pickup --json --on-complete merge [--under X]`.
   Read the `picked` or `resumed` event. It names the node, its branch, and
   `work/prompt-<ID>.md`. Pickup resumes this clone's open claim before it
   claims anything new, so re-running it after an interruption is safe.
2. **Implement** in a **fresh executor sub-agent** given that prompt (one fresh
   session per leaf). It commits, writes `work/implementation-summary-<ID>.md`
   and `work/reviews/<ID>/READY-<agent>.md`, and stops.
3. **Verify.** Run anything that modifies files (formatters, codegen) and commit
   it **now, before review**. After review, any commit touching more than
   `roadmap/registry.yaml`, and any merge (including `-s ours`), makes the
   reviews stale. A `--pre-finish-cmd` must therefore only check, never commit.
4. **Review.** Run `specy-road review-packet <ID>`. Dispatch a **different**
   fresh sub-agent, not the executor and not this session, whose model id is
   rostered as a `reviewer` in `roadmap/orchestration.yaml` **as committed on
   the integration branch**. It reads only `work/reviews/<ID>/PACKET.md`, fills
   in `work/review-record.template.md`, and files it with
   `specy-road review record <ID> --model <id> --verdict approve|block --file <notes>`.
   `review record` refuses `--model human` and unrostered models; the family
   comes from the roster. Then run
   `specy-road mark-implementation-reviewed --yes` here. This shell is not a
   TTY, so `--yes` is the only form. It commits an approval only when the
   recorded reviews already satisfy policy, exits 1 otherwise, and never
   creates a review. `work/reviews/` resolves to the main worktree even from a
   linked worktree.
   **With the default roster (human only) you cannot close the gate.** Stop and
   ask the human to run `specy-road mark-implementation-reviewed` in a
   terminal, then continue with step 5. Do not retry in a loop.
5. **Finish.** `specy-road grind-session --step finish --json [--pre-finish-cmd '…'] [--until X]`
   on the leaf's `feature/rm-*` branch. Exit `4` (pre-finish failed) or `1`
   (finish failed, often the gate) means fix and re-run finish; a
   `hook_failed` with `phase: locate_claim` means HEAD is not on a claim, so
   run `--step pickup` first. A `stopped` event with `until_reached` means
   done; otherwise go to step 1.

**Usage limits are the harness's job here, not specy-road's.** In Claude Code
(2.1.234+), turn on *Continue automatically at usage limit* in `/config`; the
session waits out the limit and carries on. Sub-agents in flight at the limit
are lost, so re-run `--step pickup` (it reports `resumed` for the same leaf)
and dispatch a fresh executor. Cursor and Codex have no auto-continue: re-run
`--step pickup` when the chat resumes. `/loop` and scheduled wake-ups run only
inside a live session and are blocked by the same limit, so they cannot restart
a session; use them only to poll, for example while a human reviews.

Step mode does not take `--implement-mode hook`, `--implement-cmd`, `--plan`,
or `--delete-merged-branches`. `--max-leaves` and `--max-cycles` do not apply;
stopping is your call.

### Hook mode (terminal only)

One process runs the whole loop and calls an agent CLI per leaf:

```bash
specy-road grind-session \
  --until M7.6 --on-complete merge --json \
  --implement-mode hook --implement-cmd 'my-agent --prompt "$SPECY_ROAD_PROMPT"' \
  --pre-finish-cmd 'make test && specy-road validate'
```

Run hook mode in a terminal (`caffeinate`, plus `tmux` if you detach), not in
this chat pane: it needs a process that can be waited on. When
`--implement-cmd` is the **Claude CLI** (`claude -p …`), the loop waits out a
timed session limit and resumes the same Claude session. A spend limit, or
wording the parser does not recognise, stops the session and says why. It also
re-runs a hook killed from outside without printing anything. Those bounds are
tunable; see `docs/grind-session.md`. Other agents, Codex included, get one run
and stop on a non-zero exit.

Human-in-the-loop (manual mode: implement, then `touch work/.session-ready`):

```bash
specy-road grind-session --max-leaves 1 --on-complete merge
```

A hook or manual loop that ends on its own terms checks out the **integration branch**; add
**`--delete-merged-branches`** to also delete the `feature/rm-*` branches it
merged (locally, and on the remote when `--push` was given). Without the flag it
prints the command. With `--json`, stdout is JSONL only — sub-command output goes
to stderr.

Stop conditions: `--until NODE`, `--under PARENT`, `--max-leaves N`, or default
(no actionable work). Stable exit codes: `0` ok, `1` generic failure (including
a refused `pr` mode), `2` no leaves, `3` blocked on dependency/gate (human
needed), `4` pre-finish failed, `5` pickup failed. The loop lands work per
cycle, so it **refuses to start** when the resolved mode is `pr` — pass
**`--on-complete merge`** (or `auto`), or set `on_complete` in
`roadmap/git-workflow.yaml`. `--plan` is read-only and always allowed.

See `specy-road grind-session --help` and `docs/grind-session.md`.

Thin stub; the `specy-road` CLI is canonical. Generated by specyrd {{SPECYRD_VERSION}}.
