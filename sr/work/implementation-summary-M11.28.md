# Implementation summary: M11.28 — a light chore mode (`chore-mode`)

## What changed

- **`specy-road chore start <slug> --task TEXT --zone PATH… [--review] [--model ID] [--harness H] [--worktree P]`**
  writes `work/chores/<slug>.json` in the main checkout's `work/` (as `work/.workers/` is). No roadmap node,
  branch or registry row. The chore records its worktree (this checkout by default), the branch checked out
  there, and that branch's head as `base`. Slugs are lower case (never a node id) and never start with `w-` (a
  worker id).
- **Worker commands take the slug.** `worker delegate <slug>` uses the chore's `--model`/`--harness` as
  defaults (`--model` is no longer required by argparse; a leaf still gets "--model is required"). The prompt is
  a chore prompt (task, zones, commit rules) and there is no brief. A model off the roster runs when a harness
  is named (`roster_free` entry: no executor-role or eligibility check); without one it is refused. `message`
  and `resume` resolve the same entry and refuse a closed chore. `sync` and `usage <slug>` needed no change,
  because they read worker records by `node_id`. `reconcile` judges the chore's own zones from `base` (the
  worker guard: changes outside them set `needs_reconcile`). The chore's record files are bookkeeping, not
  breaches.
- **Orphans:** a chore worker is never orphaned for lack of a claim or graph node. Once the chore is closed, a
  worker still held on it is orphaned ("chore … is closed").
- **Review (optional, `chore start --review`):** `review delegate <slug> --model R` runs a rostered reviewer in
  the chore's worktree with a chore reviewer prompt. The prompt points at `git diff base..head`, the task as
  acceptance `A1`, and the exact `REVIEW-<model>.md` form to write under `work/reviews/<slug>/`. The existing
  `close_run`/`valid_record` then mark the run complete. Without `--review` it refuses. There is no gate: the
  verdict is recorded, not enforced.
- **`chore close <slug> --summary TEXT`** refuses while a worker is still running, ends idle and completed
  workers (`end_finished_workers`), and writes `work/chores/<slug>.md`. The record holds the task, worktree,
  branch, `base..head`, zones, summary, `worker usage` lines and one line per valid review, or
  `unreviewed (no review was run)` / `unreviewed (review requested; no valid review record was filed)`. The
  JSON gets `closed_at`, so later delegate, message and close calls are refused.
- Docs: new `docs/orchestration-chores.md`. `docs/orchestration-workers.md` (393/400 lines) got one sentence
  linking to it, in its existing "delegate runs after pickup" bullet. `cli_usage.py` has a `chore` entry.

## Touch zones (final)

Added on this branch with `specy-road edit-node M11.28 --add touch_zones=…` (commit `8b913659`), as the
planning sheet allows. The chore hooks live where the worker and review steps are now implemented: M11.59
split `worker_ops.py` into a facade.

- `specy_road/worker_ops_launch.py` — delegate: chore target, roster-free entry, chore prompt, no brief
- `specy_road/worker_ops_message.py` — message/resume: same entry rules; closed chore refused
- `specy_road/worker_reconcile.py` — reconcile: chore target and prompt; chore records are bookkeeping
- `specy_road/worker_orphans.py` — no claim-based orphaning for chores; closed chore orphans its held workers
- `specy_road/review_delegate.py` — `review delegate <slug>`
- `specy_road/cli_usage.py` — `specy-road` usage text lists `chore`
- `docs/orchestration-chores.md` — new doc; `orchestration-workers.md` is at the line cap

Listed but unchanged: `specy_road/worker_ops.py`. The facade re-exports `delegate`, `reconcile` and the rest,
so nothing in it needed to change.

## Verification

- `python -m pytest -q tests/test_chore_mode.py`: 6 passed.
- `python -m pytest -n 4 -q` over the 41 worker/review/doctor/ready/stale-command test files: 595 passed,
  1 failed. The failure was `test_worker_queue_message.py::test_message_while_running_queues_and_delivers`, a
  timing assertion (`state == "idle"` right after delivery, `running` under load). The file passes alone 3/3
  (`python -m pytest -q tests/test_worker_queue_message.py`). That path calls `open_chore("M1.1")`, which
  returns `None` on the slug regex.
- CLI, docs-link and file-limit tests (9 files): 173 passed.
- Re-run before hand-off: `python -m pytest -n 4 -q tests/test_worker_cli.py tests/test_worker_orphans.py
  tests/test_worker_reconcile_contract.py tests/test_review_delegate.py tests/test_worker_resume_failed.py
  tests/test_validate_stale_commands.py tests/test_doc_links.py`: 87 passed.
- `specy-road file-limits`: OK. `ruff check` on the changed files: clean.
- Not run to completion: the whole suite (`pytest -n 4`). A background run was cut off at about 50% when the
  session was interrupted, with no failures up to that point. There is no complete result.

## Added

- `specy_road/bundled_scripts/chore_cli.py` — the chore store, prompts, target, start/close and CLI (A1, A2)
- `chores_dir` — chores live beside `work/.workers` in the main checkout, so every worktree sees one store
- `load_chore` — the one test "is this id a chore", used by reconcile, orphans and review delegate
- `open_chore` — the same, refusing a closed chore, for paths that start a worker turn
- `chore_node` / `chore_target` — the node- and ReviewTarget-shaped view the existing eligibility, reconcile and review-run code reads
- `chore_prompt` — the executor's and reviewer's prompt; the executor's names nothing that moves, so its hash stays the contract
- `start`, `close`, `_verdicts`, `_save`, `cmd_start`, `cmd_close`, `build_parser`, `main` — the command surface the sheet settled on
- `_SLUG` guard — keeps slugs disjoint from node ids and from `w-` worker ids (`worker usage` reads `w-` as a worker)
- `_entry_and_harness(..., roster_free=)` branch — the roster-free `--model`/`--harness` A1 asks for; a leaf is unaffected
- `delegate`: "--model is required" guard — argparse no longer requires it, because a chore supplies one
- `delegate`/`_send`: `if not entry.get("roster_free")` around `_check_eligible` — a roster-free model has no roles to check
- `_launch_locked`: skip `_brief_into` for a chore — there is no brief to render
- `worker_reconcile._target` chore branch, chore prompt, `brief_same` for chores — reconcile works without a roadmap node
- `_bookkeeping`: `work/chores/<slug>.` prefix — the chore's own record is never a dirty tree or a breach
- `worker_orphans._cause` chore branch — no false "no claim" orphan; a closed chore releases its held workers
- `review_delegate.delegate` chore branch and `_start` chore prompt — `review delegate <slug>`, refused without `--review` or once closed
- `cli.py` `_FORWARDED["chore"]`, `cli_usage.py` lines — register and document the command
- `tests/test_chore_mode.py`:
  - `test_start_records_an_unregistered_chore` — start writes only `work/chores`; bad and duplicate slugs refused
  - `test_delegate_sync_usage_message_and_close` — real fake-harness run: delegate, sync, no orphan, usage, message, close record, refusals after close
  - `test_close_refuses_while_a_worker_runs` — close guard (`spawn` mocked to leave the worker starting)
  - `test_roster_free_model_needs_a_harness` — roster-free model needs `--harness`; leaves still need the roster (`spawn` mocked to capture argv)
  - `test_reconcile_enforces_the_chore_zones` — in-zone change passes, out-of-zone change sets `needs_reconcile` (`spawn` mocked)
  - `test_review_delegate_takes_a_chore_started_with_review` — refused without `--review`; with it, a mocked `_turn` files the prompt's template, the run is complete and close records `approve`
  - `run_chore_cli`, `_start`, `_filed_review` — test helpers
