# Implementation summary: M14.6

Reviewer usage is visible: RUN files and notes kept per round, `specy-road review usage <ID>`, reviewers in `worker usage`'s node total.

## Changes

- **A1 / A4 — rounds kept.** `review delegate` calls `archive_round()` (new, `specy_road/review_usage.py`) just before it writes the new run's record. When a `RUN-<model>.json` already exists:
  - it is copied to `history/RUN-<model>-<commit12>-<n>.json`;
  - `RUN-<model>.log` is **moved** to `history/RUN-<model>-<commit12>-<n>.log`;
  - `notes-<model>.md` is **moved** to `history/notes/notes-<model>-<commit12>-<n>.md` when that run left notes behind.

  `n` is that model's round. It is one more than the highest `n` among the archived records whose `model` field (not the file name) is this model. The current files stay at their paths, so `handoff status`, `review list` and `run_states` are unchanged.
  - **Why the log is moved, not copied:** `_turn` opens the log in append mode. Before this change the log built up across rounds; it was not overwritten. Moving it means the current log holds only the current round, so usage is never counted twice.
  - **Why notes are moved, not copied (RC2):** a copy left the previous round's draft in place. A later run that failed before writing notes could then be archived with that stale file, relabeling another commit's notes. Moving clears the current path like the log.
  - **Why notes go in `history/notes/`:** `list_review_history` reads every `history/*.md` as a filed review record. That list feeds the gate's prior approvals, RCA rounds and eligibility. Reviewers draft their record in their notes and file it with `--file <notes.md>`, so a notes copy in `history/*.md` could be counted as a filed approval. The `notes/` subdirectory is still under `history/` and is not globbed. This is my reading of A4's "under history/"; reviewers should check it.
- **A2 — `review usage <ID>` [--json].** It lists every delegated run, archived and current. For each run it gives model, harness, round, commit, state, file, turns and the summed usage, then a total over all runs.
  - Each log is parsed line by line with the run's harness adapter `parse_events`, the same parser worker events use.
  - Session running totals become per-turn figures with `worker_usage_delta.turn_usage`, as `worker usage` does. A `resumed` run continues the same model's previous run's event history, so a resumed Claude session's `total_cost_usd` is not counted twice.
  - Figures are summed with `worker_cli_render._sum_usage` and printed with `usage_text`, so an unreported figure is `None` / `?`, never 0.
  - The subparser is defined in `review_usage.add_parser` and registered from `review_delegate.add_parser`. That function is already called from `review_cli.py`, so `review_cli.py` ends up unchanged. After the merge of `WIP/improvements-0-3-1` (which added `review defer`), `review_cli.py` is exactly 400 lines. Two more lines there would break the file-limits cap.
  - No roster price estimate is applied, because the saved log does not keep the launch argv's `--model`. The cost is whatever the harness reported, or `?`.
- **A3 — node total.** `usage_lines()` takes an optional `repo_root`. When the node has delegated reviewer runs it prints three lines: `executors, …`, `reviewers, N run(s), …` and the combined `total, …`. With no reviewer runs the output is unchanged.
  - `usage_json_payload()` adds `executors`, `reviewers` and a combined `total` to `--json` when reviewer runs exist, so text and JSON agree (RC1). `usage()` and its `total` stay executor-only for GUI per-worker rows.
  - `usage()` rows also carry each attempt's `worktree`. When `repo_root` is not passed, `usage_lines` finds the project from that worktree's nearest existing directory. A finished leaf's worktree is gone, but its parent under the project's `work/` still exists.
  - `worker_cli.cmd_usage` passes its resolved `--repo-root` into `usage_lines` / `usage_json_payload`.

## Touch zones (final)

`specy_road/review_delegate.py`, `specy_road/review_usage.py` (new), `specy_road/bundled_scripts/worker_cli_render.py`, `specy_road/bundled_scripts/worker_cli.py`, `tests/`. `specy_road/bundled_scripts/review_cli.py` is in the zones but ends up unchanged. No change outside them.

- **Merge:** `WIP/improvements-0-3-1` was merged earlier on this branch; `review usage` registers from `review_delegate.add_parser` so `review_cli.py` stays at the cap.
- **Rework (gpt-6.1-sol RC1/RC2):** JSON node totals include reviewers; archived notes move instead of copy so a no-notes failure cannot relabel a prior draft.

## Probes

- `worker usage --json` with executor plus two review rounds: combined `total` matches text (1300/130/$1.75); `executors` and `reviewers` subtotals present — pass after RC1.
- `archive_round` when `notes-<model>.md` is absent after the prior run's notes were moved: no `history/notes` file created for the archived RUN — pass after RC2 (covered by the new capacity-failure test).
- `usage()` / GUI `_row` still read executor-only `total` without calling `usage_json_payload` — unchanged contract, no reviewer double-count in the Workers drawer.
- Successful two-round archival test still passes with notes moved (same on-disk content as copy for completed rounds).
- `list_review_history` glob `history/*.md` still excludes `history/notes/` — notes paths unchanged.

## Verification

- `python -m pytest tests/test_review_usage.py -q`: 7 passed.
- `specy-road file-limits`: OK.
- `python -m pytest -n 4 -q`: (recorded in READY).

## Added

- `review_usage.archive_round`: keeps the previous round's RUN json, log and notes under `history/` before a new run (A1, A4); notes **move** (RC2).
- `review_usage._history_runs`: reads archived RUN records and filters by the model recorded inside them, because model ids may contain hyphens and make file names ambiguous.
- `review_usage._round_of`: reads the round number from an archived file name.
- `review_usage._log_turns`: per-turn usage from a log via the adapter parser and `turn_usage` (A2).
- `review_usage.review_usage`, `review_usage_lines`, `cmd_review_usage`, `add_parser`: the `review usage` command and its data (A2).
- `review_usage.NOTES_DIRNAME`: the `history/notes/` subdirectory, so notes copies are never read as filed records (A4).
- Guard in `archive_round`: the commit is sanitised to alphanumerics, using `unknown` if there is none, because it becomes part of a file name.
- Branch in `review_usage`: a resumed run carries the same model's previous run's events, so session totals are not counted twice.
- `review_delegate.delegate`: one call to `archive_round` before the new record is saved (A1, A4).
- `review_delegate.add_parser`: one call to `review_usage.add_parser`, so `review usage` is registered without lines in `review_cli.py`, which is at its file-limits cap (A2).
- `worker_cli_render._project_root_of`: finds the project from a worker's worktree or its nearest existing parent (A3).
- `worker_cli_render.reviewer_total`: the node's reviewer total, or `None` when the node has no delegated runs (A3).
- `worker_cli_render._combined_node_total`: shared executor/reviewer/combined totals for text and JSON (RC1).
- `worker_cli_render.usage_json_payload`: `--json` payload with `executors`, `reviewers` and combined `total` when reviewer runs exist (RC1).
- `worker_cli_render.usage_lines`: the executors/reviewers/total branch and the optional `repo_root` (A3).
- `worker_cli_render.usage`: `worktree` field on each attempt row, used to find the project (A3).
- `worker_cli.cmd_usage`: passes resolved root to `usage_lines` and `usage_json_payload` (A3, RC1).
- Test `tests/test_review_usage.py::test_each_round_keeps_its_run_json_log_and_notes_in_history` (A1, A4).
- Test `::test_review_usage_lists_each_run_and_the_total` (A2).
- Test `::test_worker_usage_adds_reviewers_to_the_node_total` (A3; text and `--json` combined total, RC1).
- Test `::test_notes_are_not_relabeled_when_a_later_run_writes_no_notes` (A4/RC2: capacity failure at new commit, then successful retry).
- Test `::test_a_removed_worktree_still_finds_its_projects_reviews`: covers the `_project_root_of` parent walk.
- Test `::test_worker_usage_uses_its_repo_root_not_the_worktree`: `--repo-root` when the worktree names no project (A3).
- Test `::test_no_delegated_review_keeps_the_single_total_line`: output unchanged without reviewer runs.
- Mock `FAKE_USAGE` in that test file: the existing fake Claude harness, extended to print usage on its result line and to write notes during the run.
- `tests/review_delegate_helpers.py`: public fake-harness and CLI helpers shared by delegate and usage tests (no imports of underscore names from test modules).
