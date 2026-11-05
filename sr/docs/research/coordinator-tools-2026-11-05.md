# Coordinator tools harvest (2026-11-05)

## Purpose

During the 0.3.1 grind (2026-11-04 and 2026-11-05) the coordinator built small tools around specy-road to keep
the build → review → land loop running unattended. Each tool marks a job the product does not do yet. This page
lists every tool, the product gap it shows, and the roadmap node that covers the gap, so the tools can be retired
as the product catches up.

Sources: the tools under `sr/work/orchestrator-2026-11-04/` and `sr/tools/` (untracked coordinator workspace and
tracked wrappers), and their evidence in `sr/work/coordinator-rough-edges.md` (rough edges, cited as **RE** with
the entry's date and time or section) and `sr/work/orchestrator-2026-11-04/overnight-decisions.md` (cited as
**OD** with the time).

## Rulings that constrain the harvest

- **Orchestration is canonical core** (maintainer, 2026-11-05, decision D1 in the M16 phase sheet; written into
  the constitution by M16.29). Workers, review delegation and the grind loop stay in the product; a harvested
  feature extends them rather than living in an optional extra.
- **No new runtime dependencies.** Every harvested feature uses the standard library, git and the harness CLIs
  specy-road already launches. No queue server, scheduler, process supervisor or workflow engine.
- **Keep building, reopen buy vs build on its triggers** ([`harness-landscape.md`](harness-landscape.md)). The
  grind loop, review queue and supervision overlap the job of a durable workflow engine (Temporal, Kestra) and
  of local multi-CLI runners (Vibe Kanban, Claude Squad). None meets a trigger: Temporal and Kestra need a server
  or daemon, Vibe Kanban and Claude Squad do not drive the review gate, and no maintained package drives two of
  our CLIs with usage reporting from Python without a daemon. The new leaves cite this page; the next landscape
  run should check whether one of those projects now covers the loop.
- **Themed milestones.** New work goes to M18 (orchestration and review-loop features, after 0.3.1), never to
  M1–M15. Fix-shaped gaps go to M16.65's feedback-and-fix intake, not to M18.
- **M16 end state.** M16.15–M16.19 move the orchestration code under `specy_road/orchestration/` (state
  snapshot, `workers/`, `roster/`, `guard/`, `grind/`), and M16.14 and M16.52 replace the verify and land keys
  with `checks:`. The new leaves name those destinations as touch zones and depend on the moves.

## Inventory

One row per tool. "Coordinator-only" means glue that should not become product (reason in the last section).

### `sr/work/orchestrator-2026-11-04/`

| Tool | What it does | Product gap | Covered by | Evidence |
|---|---|---|---|---|
| `dispatch.py`: pickup and delegate loop | Every 60 s picks eligible leaves (prefixes, deps Complete, unclaimed, not held), schedules by zone overlap, delegates up to `MAX_EXEC` with per-model caps, re-delegates orphaned claims | `grind-session` lands one leaf at a time; nothing runs several workers, schedules by zones across live claims, or re-delegates an orphaned claim | **new leaf M18.20** (unattended loop); per-model cap in M18.20; orphan listing already landed in M15.26 | RE 2026-11-05 06:53 (OD 06:53: held claims held zones, loop idle 2 h); RE 15:46 |
| `dispatch.py`: `NO_CONFLICT_ZONES` incl. `CHANGELOG.md` | Treats `tests/`, `planning/`, `shared/`, `work/` and `CHANGELOG.md` as non-overlapping | `grind.shared_zones` covers directories only; two leaves naming the same file still overlap, so every leaf zoning `CHANGELOG.md` serialized | **new leaf M18.27** (append-only zone kind); directory part already product (`grind.shared_zones`) | RE 2026-11-05 15:46 |
| `dispatch.py`: zones released in review | Only running or undelegated claims hold zones; leaves in review do not (maintainer: maximum parallelism) | No setting for when a claim stops holding its zones | **M18.20** (opt-in release in review) | dispatch.py `eligible()` comment; OD 06:53 |
| `dispatch.py`: Opus / Composer / Grok routing | `OPUS_LEAVES`, `is_complex()`, Grok when Opus is limited | Executor choice per leaf exists (`executor_eligibility`, `orchestrate assign`); failover when an account is limited does not | `orchestrate assign` (existing); failover in **new leaf M18.23** | OD; RE 2026-11-05 15:44 |
| `dispatch.py`: account split (`split.txt`, `split-counts.json`, session affinity) | Weighted least-used `CLAUDE_CONFIG_DIR` per delegate; a resume stays on the account holding the session; weight 0 drains | One account per roster entry; no pool, no affinity, no failover | **new leaf M18.23** (account pools) | RE 2026-11-05 15:44; RE Open "Both OpenAI routes hit usage limits" |
| `dispatch.py`: review queueing | Queues a leaf when READY is at HEAD and the post-run check is clean | Nothing hands a READY leaf to its reviewers | **M18.20** (calls the review run) and **new leaf M18.24** | RE 2026-11-04 (M12 orchestration) queue deadlock entry |
| `dispatch.py`: pre-review prechecks (ruff, private test imports, complexity growth) | Sends the leaf back before review when a check fails | Checks run at land, after both approvals | M16.14 (`checks:` with `when: ready`), M16.22 (complexity gate), M16.54 (test-to-test imports) | RE 2026-11-04 (M12) ruff and private-import entries |
| `dispatch.py`: gate and land | Runs `gate.sh`, then `land.sh` under the git lock; lands claims whose worker record is gone | Landing needs a coordinator; a missing worker record looks like an orphan | **M18.20** (land on policy met, keyed on the claim); land check: M16.14 | RE 2026-11-05 09:20; OD 09:15 |
| `dispatch.py`: digest drift tolerance | Lands when `digest --check` fails only on claim lines and Quality-by-area rows, then regenerates the digest on the integration branch | Pickup's register commit does not regenerate the digest; Quality-by-area rows depend on branch history | M16.65 intake (pre-filed there; fix-shaped) | RE 2026-11-04 (M12) digest entry; OD 03:25 |
| `dispatch.py`: `AUTO_FIX`, `AUTO_FIX_MAX`, park to `hold.txt` | Sends the standard fix round on a new block; parks the leaf after four rounds | `worker message --fix-round` (M14.11) and `policy.max_fix_rounds` (M12.1) exist; nothing sends the round or parks | **new leaf M18.21** | RE 2026-11-05 15:23; OD 03:17, 03:56, 07:00, 07:05 |
| `dispatch.py`: leaf-local review sync | Copies REVIEW records a reviewer filed into the leaf worktree's own `work/reviews/` into the shared hand-off dir | `review record` from a linked worktree can file where the gate never reads | M16.65 intake (pre-filed; fix-shaped); M19.6 saves hand-off files before cleanup | RE 2026-11-04 (M12) "Low-effort Codex reviewer ... files REVIEW/history into the worktree" |
| `dispatch.py`: STUCK lines | Reports a finished worker with READY not at HEAD for 20 min | No report of a stalled leaf | **new leaf M18.22** | dispatch.py; RE 2026-11-05 15:23 |
| `watchdog.py` | Every 3 min: loop or runner dead (restarts them), loop silent, failed / stalled / idle workers, stuck review queue, ready-but-undelegated leaves, dirty main checkout, own heartbeat | Nothing reports these states; `doctor` lists orphaned claims only (M15.26) | **new leaf M18.22** (report only; self-restart is coordinator-only) | RE 2026-11-05 11:25, 15:12, 15:23, 15:44 |
| `fixrounds.py` | Sends the dispatcher's fix round by hand (dispatcher stopped) | Same as `AUTO_FIX` | **M18.21**; prompt text: M18.15 (`--rework` carries blocks and a note) | RE 2026-11-05 15:23, 15:44 |
| `start-dispatch.sh`, `start-runner.sh`, `start-watchdog.sh` | One place for each daemon's environment; `setsid`, `9>&-` | Loop settings live in environment variables, so a restart from the wrong shell used the wrong account or inherited the lock | **M18.20** (settings from config and flags, not environment); the scripts themselves are coordinator-only | RE 2026-11-05 11:25, 15:44; RE 2026-11-03 13:15 |
| `rvq/runner.sh` | File queue; at most `MAX` `rv.sh` runs; `running/<ID>` markers | No review concurrency cap; duplicate runs for one leaf | **new leaf M18.24** | RE 2026-11-04 (M12) `pgrep` deadlock; RE 2026-11-05 03:51; RE 14:53 |
| `rvq/adopt.sh` | Finishes bookkeeping for a review whose runner subshell was killed | Artefact of the shell runner | Coordinator-only; M18.16 (RUN record for every channel) covers the trace | RE 2026-11-04 (M12) runner restart entry |
| `plan-review.sh`, `lenses/*.md` | Two-family lensed plan review of planned leaves | No plan review before pickup | M18.18 (acceptance line added: the schema row of the item lens) | RE 2026-11-05 14:53 (plan reviews miss schema enums) |
| `gate.sh` | Full pre-land gate: validate, export, digest, file-limits, ruff, clones, machine paths, private imports, pytest | Land check ran pytest only; CI and land disagreed | M11.82 (landed: ruff in the land check); M16.14 (`checks:` `when: land`) | RE 2026-11-03 12:05, 12:40 |
| `edit-zone.sh` | Adds zones to a leaf on the integration branch, under the lock, with a reason in the commit subject | No amendment record; the post-run out-of-zone flag stays set; the packet reads zones from the reviewed commit (M11.49) | **new leaf M18.26** | RE 2026-11-05 14:53; RE 2026-11-03 09:58 |
| `edit-acc-append.sh` | Appends to or replaces one acceptance line by index | `edit-node` replaces the whole acceptance list | **M18.26** (one-line edits with a reason) | OD 02:57, 03:05, 03:08 (acceptance rewritten overnight) |
| `edit-m*.sh`, `edit-triage-1.sh`, `edit-roster-*.sh`, `edit-audit-followups.sh`, `add-m16-70.sh` | One-off planner batches of `edit-node` / `add-node` calls | Batch authoring | `apply` (existing) and M21.5 (moves and removals in a change file) | — |
| `make-m21.sh`, `do-moves.sh` | Moves leaves to a new phase, records the old to new id map, rewrites prose ids, notes the old id in each sheet | Moves renumbered too much; prose ids were rewritten by hand | M21.1 (chosen id, subtree-only), M21.2 (group), M21.3 (rename-refs), M21.5 (batch apply) | OD; M18 phase sheet (restructure) |
| `archive-old.sh`, `close-old.sh` | Archives closed milestones one by one with a validate after each; marks milestones Complete; hard-removes an empty phase | Existing commands (`archive`, `archive --auto`, `archive-node --hard-remove`) | M16.45 (`archive --hard-remove`), M21.4 (`remove-node`); loops are coordinator-only | — |
| `hold.txt` | Leaf ids the dispatcher never picks up, fixes or lands; reasons after `#` | No hold list for unattended runs | **M18.20** (hold list); held-leaf triage: M16.34 | OD 03:17–07:05; RE 2026-11-05 15:16 |
| `git.lock` | One flock for every git write in the main checkout (dispatcher, planner, coordinator) | Pickup and finish share a lock (M11.74); roadmap edits in the shared checkout do not, and a dirty checkout blocks landings | M11.74 (landed); **M18.20** waits while the checkout is dirty; **M18.22** reports it | RE 2026-11-05 11:25, 15:12; RE Open "single landing lock starves pickups" |

### `sr/tools/`

| Tool | What it does | Product gap | Covered by | Evidence |
|---|---|---|---|---|
| `rv.sh` | Trial-merge conflict check, review packet, out-of-zone stop, reviewer 1, reviewer 2 only after reviewer 1 approves; one retry when a one-shot record is refused | `review delegate` runs one reviewer and retries capacity errors only; no ordered run of the required reviewers; no retry on a refused record | **new leaf M18.24**; trial merge before review: M3.13 (landed); zone stop before review: M18.9 | OD 07:15; RE 2026-11-04 (rc3 session 3) refused-approve entry |
| `rv2.sh` | Runs only the second reviewer | Same | **M18.24** (skips a reviewer with a record at HEAD); script coordinator-only | — |
| `land.sh` | Pause file; conflict check ignoring generated files; `--allow-scaffold-planning` when WIP has the written sheet; retry with the branch's own code for a new schema key; worktree removal; worker terminate | Each was a product gap | M16.68 (landed: inherited roadmap conflicts), M11.15 (scaffold sheet), M11.69 (landed: schema key), M19.6 (cleanup after land), M18.20 (pause through the hold list) | RE Open (schema key; scaffold sheet); RE 2026-11-03 12:15 |
| `codex-review.sh` | Prompt file on stdin, effort override, hand-off dir as writable root, prints only `codex -o`'s final message, transcript to `work/reviews/.transcripts/` | A `channels.cli` reviewer's whole output must be one JSON object, so every wrapper re-implements answer extraction and transcript keeping | **new leaf M18.25** | OD 03:31; RE 2026-11-04 (Ubuntu) E2BIG and bwrap entries |
| `cursor-review.sh`, `last-json.py` | Prompt file named in the prompt; raw output to a side transcript; prints the last top-level JSON object | Same | **M18.25** | OD 03:47; RE 2026-11-04 10:00 |
| `claude-review.sh` | Opus fallback reviewer; same transcript and answer handling | Same; fallback order between reviewers | **M18.25**; fallback: M18.10 (limit marks the reviewer unavailable) | OD 07:30 |
| `review-addendum.md` | Notes self-check appended to every reviewer prompt | One-shot records were refused on notes rules | M15.17 (landed), M21.12 (joined observations), **M18.24** (retry with the refusal text) | OD 03:35, 03:37; OD 09:31 |
| `pick.sh` | Pickup into a worktree, then `worker delegate` | Manual pickup and delegate | **M18.20**; `do-next-available-task --worktree` exists | — |
| `claude-worker.sh`, `fable-worker.sh` | Create-or-resume executor wrappers from docs/orchestration-workers.md | Wrapper per model | M16.63 (typed `run:` block), M15.36 (explicit Claude launch mode) | RE Open (2026-11-02: a worker cannot change model mid-leaf) |
| `env.sh`, `specy-road` shim | Resolve the main checkout and run the checkout's own specy-road | Dogfooding only | Coordinator-only | RE 2026-11-03 13:40 (installed vs checkout) |

## New leaves (M18)

| Leaf | Title | Replaces |
|---|---|---|
| M18.20 | Unattended grind loop: several workers, zone-overlap scheduling, per-model caps, review hand-off and landing on policy | `dispatch.py` loop, `pick.sh`, `hold.txt`, start scripts' settings |
| M18.21 | Automatic fix rounds with the fix-round budget as the cap, and parking | `AUTO_FIX`, `fixrounds.py` |
| M18.22 | Orchestration supervision report in `doctor` | `watchdog.py`, STUCK lines |
| M18.23 | Executor account pools: weights, session affinity, failover on usage limits | `split.txt`, Opus fallback |
| M18.24 | `review run`: required reviewers in order, a concurrency cap, one retry on a refused record | `rvq/runner.sh`, `rv.sh`, `rv2.sh` |
| M18.25 | `channels.cli` reviewers write their answer to a file; the transcript is kept aside | `codex-review.sh`, `cursor-review.sh`, `claude-review.sh`, `last-json.py` |
| M18.26 | Amending a claimed leaf's zones or one acceptance line, with a recorded reason | `edit-zone.sh`, `edit-acc-append.sh` |
| M18.27 | Append-only zone paths (such as `CHANGELOG.md`) that do not serialize leaves | `NO_CONFLICT_ZONES` |

Added to an existing leaf instead: M18.18 gains one acceptance line (the item lens's schema row).

Pre-filed in M16.65's intake (fix-shaped, not M18 features): leaf-local review records filed where the gate does
not read them, and `worker message` run from a linked worktree writing the worker record there (RE 2026-11-05
02:00); pickup's register commit leaving the digest stale (RE 2026-11-04 M12; OD 03:25); finish landing in the
checkout every reviewer runs its tools from (RE 2026-11-03 12:15).

## Coordinator-only glue (not product)

- **Daemon start scripts and self-restart** (`start-*.sh`, the watchdog's restart of a dead dispatcher or
  runner): specy-road has no daemon and no service manager (harness-landscape: "no-daemon, file-based
  design"). The product reports a dead or silent loop (M18.22); restarting it belongs to the user's own
  supervisor (cron, systemd, launchd, a terminal multiplexer).
- **`rvq/adopt.sh`**: repairs the shell queue's own bookkeeping after a killed subshell; M18.24's run records
  replace the queue.
- **`env.sh` and the `sr/tools/specy-road` shim**: they run the checkout's code while the toolkit develops
  itself. Adopters run an installed specy-road.
- **`rv2.sh`, `pick.sh`, one-off `edit-*.sh`, `make-m21.sh`, `do-moves.sh`, `archive-old.sh`, `close-old.sh`**:
  thin sequences of existing commands for one planning session; the product parts are listed above.
- **`git.lock` as a coordinator-wide lock**: a lock around the coordinator's own manual git commits is
  workspace discipline; the product part (pickup and finish share a lock) landed in M11.74.
- **Model choice lists in `dispatch.py`** (`OPUS_LEAVES`, `COMPOSER_LEAVES`, `COMPLEX_PATHS`): the
  coordinator's judgement for one grind; the product already has `executor_eligibility` and
  `orchestrate assign`.
