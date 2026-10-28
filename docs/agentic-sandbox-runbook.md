# Agentic sandbox runbook: 0.3.1 release candidate

> **Audience:** the maintainer and the agent driving the agentic sandbox.
> `0.3.1-rc1` is not cut until every scenario here has been played out and
> recorded as passed. The [release runbook](release-runbook.md) takes over
> from there (Section A). This file is the 0.3-line supplement to its §3.3
> three-app harness: it covers what the automated suite cannot — real
> harness CLIs, real sessions, real pages.

## Agent quickstart

**Use this doc when:** playing out the real-harness scenarios that gate `0.3.1-rc1`, or recording their evidence.
**Not for:** cutting the tag and publishing — [`release-runbook.md`](release-runbook.md) §A; the worker commands themselves — [`orchestration-workers.md`](orchestration-workers.md).

**Must know without reading on:**
- Nothing here is claimed by `pytest`; every scenario needs signed-in `claude`, `codex` and `agent` CLIs and three disposable consumer apps.
- Record each scenario in `work/sandbox-runbook-<YYYY-MM-DD>.md` as PASS, PASS-WITH-NOTE, FAIL or SKIPPED, stating what was not observed; a blank is SKIPPED, never a pass.
- A FAIL anywhere, or a SKIPPED on §5 or §6, blocks the rc.
- The version is the maintainer's to state (`0.3.1-rc1`; this line never uses `.0`).

**Read further for:**
- CLIs, apps and the evidence file → "0. Prerequisites"
- `specyrd init` skills on each harness, upgrading from 0.2.3 → "1. Scaffold and skills (every harness)"
- the gate, stale reviews, signed records, lean prompts and reviewer restraint → "2. Review gate and signed reviews"
- `session guard` hooks → "3. Presence and the tool-call guard"
- roster, prompts and sensitivity → "4. Models, prompts, plan"
- delegate, handoff, hook and process-tree faults → "5. Workers (the 0.3.1 headline)"
- rounds, panel, evidence, promote and the GUI → "6. Brainstorm v2"
- hook-mode grind and the gate → "7. Grind and unattended loops"
- what must be green before §A → "8. Close-out"

**Related:** [`release-runbook.md`](release-runbook.md), [`orchestration-workers.md`](orchestration-workers.md), [`brainstorming.md`](brainstorming.md), [`orchestration.md`](orchestration.md).

The suite (`pytest`, ~2,100 tests) proves the toolkit's logic with fake
harnesses and stub fetchers. Everything below needs a machine with the
vendor CLIs installed and signed in, and is **not** claimed by any test.

## 0. Prerequisites

- A sandbox checkout of the toolkit at the `WIP/improvements-0-3-1` tip, installed
  into a fresh virtual environment (`pip install -e .`), so `specy-road`
  is the candidate.
- Harness CLIs, signed in on the maintainer's own plans: `claude` (Claude
  Code ≥ 2.1.302), `codex` (≥ 0.164), `agent` (Cursor CLI, 2026.10+). Note
  the versions in the evidence file; the adapters were verified against the
  2026-10-27 docs and flags drift.
- OpenSSH ≥ 8.1 (`ssh-keygen -Y`; the docs state 8.1 as the floor, and the
  signing tests have only run on 10.x, so run S6 on the oldest OpenSSH the
  team uses), `gh` if `on_complete: pr` is exercised.
- Three disposable consumer apps as in release-runbook §3.3 (ToDo,
  Calculator, Notes), each a git repo with a bare local remote; the Notes
  app carries the moderate roadmap (phases, gates, dependencies, planning
  sheets, shared contracts, ≥ 8 leaves with `acceptance` and `touch_zones`).
- Evidence file: `work/sandbox-runbook-<YYYY-MM-DD>.md` in the toolkit
  checkout (gitignored), one section per scenario: commands, paths, node
  ids, pass/fail, and the exact text of any refusal or warning. For every
  scenario, state what was **not** observed as well as what was; a blank is
  a SKIPPED, never an implied pass.

Rating for each scenario: **PASS** (criteria met), **PASS-WITH-NOTE**
(met, with a documented caveat), **FAIL** (blocks the rc), **SKIPPED**
(name why; a skip on S5 or S6 blocks the rc).

## 1. Scaffold and skills (every harness)

In the Notes app:

1. `specy-road init project` → `validate` and `file-limits` exit 0.
   `export --check` and `digest --check` exit 1 with `missing …` because the
   scaffold ships neither generated file (`roadmap.md`,
   `roadmap-context.md`); run `specy-road export` and `specy-road digest`
   once, then both exit 0. `roadmap/orchestration.yaml`, `model-profiles/` and
   the `AGENTS.md` managed block are present.
2. `specyrd init --ai cursor`, `--ai claude-code`, `--ai codex`: one
   `.agents/skills/<name>/SKILL.md` per command; `.claude/skills/<name>` is a
   symlink to it; `AGENTS.md` is unchanged (its block comes from step 1).
3. In each harness, invoke `specyrd-orchestrate`, `specyrd-brainstorm` and
   `specyrd-do-next-task` by name (Claude `/name`, Codex `$name`, Cursor
   `/name` or `@name`). Pass: the skill text is loaded (the agent quotes a
   line from it), not a lookalike community skill.
4. Edit a stub, run `specy-road refresh-stubs`: only managed files change;
   a pre-0.3 `.claude/commands/*.md` that `.specyrd/manifest.json` records
   is named for removal, not deleted. It is named on the first refresh only
   (the refresh drops it from the manifest); an unrecorded one is never named.
5. **Upgrade from the last release.** In a scratch repo, scaffold with
   `specy-road==0.2.3` from PyPI in its own venv (`init project`, `specyrd
   init --ai claude-code`), commit, then switch to the candidate venv:
   `refresh-stubs` gives a managed `AGENTS.md` block with a `## Lean changes
   and tests` section and leaves every line outside the markers unchanged;
   `refresh-schemas` and `refresh-profiles` add what is missing;
   `refresh-profiles --force <path>` brings a profile's `## Code and test
   tendencies`; `validate` exits 0 (with or without the CHANGELOG's
   `.gitignore` lines, which it does not check). No refresh command creates
   `roadmap/orchestration.yaml`; without it the default policy applies
   (`models list` shows only `human`).
6. `add-node` two phases with titles: `manifest.json` `includes` lists them in
   creation order, and each planning sheet is named from its title.

## 2. Review gate and signed reviews

In the Notes app with `require_implementation_review_before_finish: true`
and `on_complete: merge` in `roadmap/git-workflow.yaml`, committed on the
integration branch. The scaffold's `on_complete: pr` only prints a PR tail
and leaves the leaf open on the integration branch, and a bare local remote
has no host to open that PR on.

1. `do-next-available-task` claims a leaf; commit a change inside its touch
   zones; write `work/implementation-summary-<ID>.md` and
   `work/reviews/<ID>/READY-<agent>.md`.
2. `review-packet <ID>` writes `PACKET.md` with the brief's `A1..An`, the
   diff, and the verify tails.
3. In a **fresh** session of another harness, record a review:
   `review record <ID> --model <roster id> --verdict approve --file …`.
   `handoff status` shows the policy met.
4. `mark-implementation-reviewed --yes` closes the gate; the registry commit
   carries a `Reviewed-by:` trailer.
5. Commit again on the branch: `handoff status` shows the review stale and
   `finish-this-task` refuses. Re-review, then finish.
6. Signed: generate an ed25519 key, put its public line on the reviewer's
   roster entry, set `policy.signed_reviews: true` on the integration
   branch. `review record` without `--sign-key` is refused; with it, the
   gate passes; edit one byte of the record and the gate reports "does not
   verify".
7. Policy from the branch under review must not count: lower
   `reviewers_required` on the feature branch only; the gate still reads the
   integration branch's file.
8. **Lean prompts on real models.** `prompt <ID> --role executor` asks for an
   `## Added` inventory and `--role reviewer` carries the excess checklist.
   For each harness's executor (here and in §5), record whether its
   implementation summary ends with `## Added` listing each helper, guard,
   mock and test with a reason. Delete that section from one summary:
   `review-packet` prints a one-line note and still writes the packet.
9. **Reviewer restraint.** Make the leaf's change include one boundary check
   with a reachable trigger and a test (for example, reject an empty title
   from the CLI) and one guard with no reachable trigger. Review it in a
   fresh session of each other family.

Pass: steps 4–7 and the prompt and packet checks in 8 behave exactly as
stated, and in 9 no reviewer recommends removing the boundary check, and
every excess finding cites a caller trace or the covering test;
`finish-this-task` lands with the registry row removed. Record per model
whether the `## Added` inventory was written and whether the unreachable
guard was flagged: a miss is PASS-WITH-NOTE, evidence on whether the lean
rules change model behaviour, not a FAIL.

## 3. Presence and the tool-call guard

1. Two terminals in one checkout: `session start --path src/` in each with
   different `--agent` ids; the second prints the overlap warning;
   `session check` refuses a commit whose staged paths overlap the other.
2. Wire `session guard --format <harness> --print-config` into Claude Code
   (`PreToolUse`), Codex and Cursor (`beforeShellExecution`). With another
   session live, ask the agent to run `git reset --hard`: Claude Code blocks
   (exit 2) and shows the reason; Cursor shows the deny with the reason;
   Codex denies. `git status` is allowed. End the other session: the same
   command is allowed (no `--always`).
3. Non-denials must not widen the harness's own permissions. Alone in the
   tree, ask Claude Code to run `git reset --hard` with the hook installed:
   the hook prints `additionalContext` only (no `permissionDecision`), and
   Claude Code still asks as it would without the hook. Same in Cursor: the
   hook answers `permission: allow` (its schema is allow|deny|ask, and empty
   output fails open); confirm in a real IDE that this does **not** skip
   Cursor's normal approval prompt for a command it would otherwise ask
   about. If it does, the Cursor adapter must answer `ask` instead — record
   the result here before release (review round 6, B14 and question 4).

## 4. Models, prompts, plan

1. `models list` shows each roster entry's profile scores (C/E/R) and a
   `stale` flag (`--json` adds the profile path); the `researched` dates are
   in `models show <id>` and `models stale`. `models stale` exits 1 with one
   rostered profile's `researched` date set 200 days back, 0 otherwise.
2. `prompt <ID> --model <id> --role executor --channel cli` runs the
   profile's `access.cli` on the real harness and the session completes the
   leaf's precondition check (it must not implement when the leaf is not
   claimed by it).
3. A leaf with `sensitivity: restricted` and a roster entry whose
   `may_process` lacks it: `prompt` refuses; `orchestrate plan` names only
   eligible models and exits 1 when none qualifies.
4. `models show <id> --section "Code and test tendencies"` prints the
   profile's dated tendencies (bare `models show` prints Prompting rules),
   and `prompt --role executor --model <id>` carries that
   family's counter-rule.

## 5. Workers (the 0.3.1 headline)

Roster three entries with `harness: claude-code`, `codex`, `cursor`,
executor role, each with `profile:` pointing at its scaffolded profile as
the roster guide recommends, `max_workers: 2`. Claim two leaves. From the
coordinator chat (any harness):

1. **Delegate returns first.** `worker delegate <ID1> --model <claude id>`
   prints a worker id in under two seconds; the chat stays usable; `worker
   list` shows `running` with a pid; `worker sync` later shows
   `started`, `output`, `turn_completed` and a `completion` event; the
   record's `provider_session_id` equals the session id in `<id>.log`.
   `ps -ww -o command= -p <harness pid>` shows the harness's default command
   (JSON output, the profile's `api_id` as the model), not the profile's
   `access.cli`. Repeat on `codex` and `cursor`; a profile whose `api_id` is
   `unknown` needs `channels.cli` (PASS-WITH-NOTE). Record which plan or key
   each drew on as `billing_route`.
2. **Permission stop.** With the default command, note whether the Claude
   worker stops at a shell permission (`acceptEdits`). If it does, set
   `channels.cli` on the roster entry and delegate again. Pass: the worker
   reaches `idle`/`completed` with a READY file.
3. **Cap and idempotency.** A third `delegate` is refused by `max_workers`;
   re-running `delegate <ID1>` returns the same worker id; `--op-id` replay
   returns the first result without a second launch.
4. **Message / resume.** On an `idle` Claude worker, `worker message <W>
   --text "also update the README"` resumes the same session id (check
   `<id>.log`); on `cursor`, confirm whether the resumed run keeps the
   `session_id` — if not, record PASS-WITH-NOTE and set `channels.cli` with
   `{session}`. On `codex`, the resume passes the prompt on stdin (`-`) with
   the same sandbox flags as the launch: confirm `codex exec resume` accepts
   that form on the installed version, else record it and pin `channels.cli`.
   Also message a `completed` worker (after its READY): it must resume, and
   a READY left from the earlier turn must not complete the new one.
5. **Interrupt is honest.** `worker interrupt <W>` exits 2 with
   `unsupported by <harness>` on every adapter; nothing is killed.
6. **Double-open (expected failure).** With a Claude worker `idle`, run
   `claude --resume <id>` interactively *without* `handoff`, send a prompt,
   and in parallel `worker message`. Observe interleaving in the transcript.
   Then do it properly: `worker handoff <W>` prints the resume command and
   sets the lease; `worker message` is refused with `WORKER_LEASED_BY_HUMAN`.
7. **Hook witness.** Install `worker hook --format <harness> --print-config`.
   In the handed-off native session send two prompts, exit, `worker reclaim
   <W>`: the `intervention` event quotes both prompts, `instruction_epoch`
   is 1, and the worker is **not** flagged `possibly_modified_externally`.
   Repeat without the hook: it **is** flagged.
8. **Reconcile.** In a handed-off session, edit a file outside the leaf's
   touch zones; `worker reclaim` then `worker reconcile <W>` sets
   `needs_reconcile` and names the path.
9. **Terminate / recovery.** `worker terminate` on a running worker: state
   `terminated`, pid gone. Kill the coordinator's terminal mid-run: the
   worker finishes anyway; a new terminal's `worker sync` shows its events.
   **9b. Fault in the process tree.** What the code does (`worker_runner.py`,
   `worker_ops.py` at the candidate commit): the wrapper is a session leader
   and the harness is its child in the same process group, writing stdout to
   the wrapper's pipe and stderr straight to `<id>.log`. Find both with
   `ps -o pid,ppid,pgid,command -g <pgid>`.
   (i) `kill -9 <wrapper pid>` mid-turn. Nothing is recorded at that moment.
   Before any other `worker` command, watch for 60 s: is the harness pid still
   alive, does `<id>.log` grow, does `git status` in the worktree change?
   While the harness survives, `worker delegate <ID>` must **not** launch a
   second worker: `_wrapper_gone` appends one `error` event (source `system`,
   "wrapper pid <pid> is gone but harness pid <hpid> (group <pgid>) is still
   alive; the leaf stays owned"), flags the record
   `wrapper_gone_harness_alive`, and `delegate` returns the same worker id;
   `worker terminate <W>` then signals the recorded group and confirms it is
   gone (state `terminated`, `ps -g <pgid>` empty). Pass: that event, the
   flag, no second launch, and the group gone after `terminate`. Alternative
   path: `kill -- -<pgid>` by hand, then `worker delegate <ID>`:
   `_wrapper_gone` appends "wrapper pid <pid> is gone without recording an
   exit; marked failed", the old record is `failed`, and a new worker id is
   launched.
   (ii) `kill -9 <harness pid>` while the wrapper lives. `proc.wait()`
   returns `-9` (or `137` where `/bin/sh` is dash, which forks the harness
   under `sh -c` instead of exec-ing it) and `_finish` appends an `error`
   event (source `worker`, "exit -9; see <id>.log", `detail: {exit: -9,
   ready: …}`, with `137` in place of `-9` under dash) and sets the
   worker `failed`, not `idle` — even if a READY was written. `worker
   resume <W>` is then refused ("is failed; delegate again instead"), and
   `worker delegate <ID>` launches a new worker. Pass: `worker events <W>`
   and `worker status <W>` show exactly that.
10. **Finish.** Review and `finish-this-task` the leaf as in §2 (with
    `on_complete: merge`; `pr` cannot land against a bare local remote);
    `worker terminate` the idle worker; `handoff status` no longer lists it.

Pass: 1, 3, 5, 7, 8, 9, 9b (ii), 10 exactly; 2, 4, 6, 9b (i) with their
notes recorded.

## 6. Brainstorm v2

In the Notes app, with a real agent on two harnesses (one run each):

1. **Round 1.** `brainstorm start --topic "…" --under <M> --count 30
   --rounds 2`. The agent asks the frame questions, records answers with
   `brainstorm frame`, writes the allocation, generates. Pass: the prompt
   contains no roadmap inventory; the agent did not research (check its
   tool calls); ≥ 30 ideas each with `--origin`.
2. **Round 2.** `brainstorm next-round --count 15`. Pass: ≥ 15 new ideas, and
   a human count of near-duplicates against round 1 under 20%.
3. **Experiment (regeneration vs one pass).** On the same topic in a fresh
   session: `start --count 45 --rounds 1` and generate once. Count distinct
   ideas (merge near-duplicates by hand). Record both counts; the rounds run
   should have more distinct ideas. A smaller count is PASS-WITH-NOTE, not
   FAIL — it is evidence for the design note.
4. **Panel.** `start … --panel 3`; run the three shard prompts as sub-agents
   (or one per harness). Pass: each shard's ideas carry `/1/sN`; the agent
   did not read the other shards (ask it); converge later clusters them.
5. **Converge.** `brainstorm recommend`: the agent records clusters,
   overlaps with relations, critics and cited verdicts via `revise`. Pass:
   `list --by cluster` groups; every `strong` rationale cites a clause,
   source, or overlap.
6. **Evidence and verify.** `brainstorm evidence`; the agent records ≥ 10
   sources with quotes from real pages. `brainstorm verify` lists the URLs
   and **asks**; answer `n`: nothing fetched, all `unverified`. Answer `y`:
   record the share `retrieved` vs `not-found` vs `blocked`. Pass: the
   prompt appears, nothing is fetched on `n`, and a hand check of five
   `retrieved` quotes finds them on the page.
7. **Triage and promote.** `reject` without `--reason` is refused; `park
   --reason … --revisit-when …` (the condition is optional); `accept`
   three; `promote --dry-run` then `promote`; `validate`, `export`,
   `digest` pass. Pass: the new sheets carry the evidence lines with
   verification state, hypothesis, and an "Alternative considered" line
   from the cluster.
8. **GUI.** `specy-road gui`; open the Brainstorm panel on the same session:
   ideas and clusters show; Brainstorm mode produces round-1 prompt
   behaviour (no node inventory); Roadmap mode converges. Pass: the panel
   and CLI agree on the session file.

## 7. Grind and unattended loops

1. `grind-session --plan --json` on the Notes app names the ready wave.
2. One `grind-session --implement-mode hook --implement-cmd '<harness
   cli>' --pre-finish-cmd '<record a review on another harness>'` cycle:
   the gate holds without a review, passes with one. `--yes` never approves
   on its own.

## 8. Close-out

- All scenarios PASS or PASS-WITH-NOTE, notes copied into the design notes'
  "checks that need a real installation" sections where they change a
  claim.
- `pytest`, `file-limits`, fixture gates, and the GUI `npm` sequence green
  on the candidate commit.
- Remove disposable apps and keys. Then follow release-runbook §A with the
  version the maintainer states (`0.3.1-rc1`; this line never uses `.0`).
