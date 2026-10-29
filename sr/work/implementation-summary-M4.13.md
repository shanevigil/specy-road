# Implementation summary: `M4.13` — `specy-road doctor`

Branch `feature/rm-specy-road-doctor-lists-merged-or-stale-feature-branches-worktrees-registry-rows-and-stashes`, base `6bcfeb8` (registration). The branch carries two checkpoint commits from worker w-0029 (`037f20b` code and docs, `23a36cf` draft tests), which this session took over at `23a36cf`, plus `8ff98f9` (review of that draft against the lean-change rules and the gates).

## What it does

`specy-road doctor [--fix [--yes]] [--base B] [--remote R] [--repo-root DIR]` runs `git fetch --prune` (the same helper as `branches prune`), reads the roadmap and registry at `<remote>/<base>`, and lists four sections:

- **A1 branches**: local and remote `feature/rm-*` branches that nothing claims. The test for "nothing claims" is the same one `branches prune` uses: no registry row (local or remote) and not an open milestone rollup. Each row gives a reason: `merged`, `merged (same patch content)`, `leaf <ID> Complete, not merged: N commit(s) … lacks`, or `claim gone, not merged: …`.
- **A1 worktrees**: linked worktrees whose directory is missing, that are detached at a commit the integration branch contains (how `finish --delete-branch` leaves a delegate worktree), or whose branch is a listed merged branch. The main worktree, the current worktree and locked worktrees are never listed. A row names the ignored files that `git worktree remove` would delete.
- **A1 registry rows** on the integration branch whose branch exists neither locally nor on the remote (`detect_stale_claims`). These are advisory.
- **A1 stashes** whose message starts `On <branch>: specy-road: `. That is the form older pickup and review pushed with `-m`.
- **A2**: a branch is "merged" first by ancestry (`merged_into`). When ancestry fails, it is merged if `git cherry` shows every commit upstream (a rebase or cherry-pick). Failing that, doctor builds a probe commit of the whole branch tree on its merge base and checks whether `git cherry` shows that commit upstream (a squash merge). An orphan branch has no merge base and counts as not merged.
- **A3**: the default is a dry run that changes nothing. `--fix` asks once per kind, in this order: worktrees, branches, stashes, registry rows (rows go through `registry-prune --remove`, which commits and pushes). `--yes` skips the questions, and with no answer on stdin doctor stops before removing anything. Every action prints `[ok] …` or `[warn] …`. A local branch is deleted only at the tip that was listed. The remote delete is `--force-with-lease` to that tip, and a stash is found again by its sha before it is dropped. Any warning makes the exit code 1.

## Changes in this session (`8ff98f9`)

- `branches_cli.py`: renamed `_branches` to `feature_branches` and `_live_branches` to `live_branches`, because doctor imports them across modules. Extracted `fetch_integration`, the resolve-defaults, warn, `fetch --prune` and error block that doctor had copied: the lean-clones gate flagged an 11-line new clone. `branches prune` behaviour is unchanged, and its error text is shared.
- `doctor.py`: removed guards that nothing can reach, or that no test reached:
  - The "named branch is gone" worktree case. `git branch -D` refuses a checked-out branch, so this state needs a raw `update-ref -d`, and `git worktree remove` then refuses it anyway.
  - The `WIP on` stash prefix. A message-less stash's subject follows a sha, so it can never match.
  - Codename-less registry rows. The registry schema requires `codename`, `node_id` and `branch`.
  - Truncation of the ignored-file list.
  - The `or "?"` and `or ctx.root` fallbacks, now `git_checked`.
  - The tree `rev-parse` before `commit-tree`, which takes `<ref>^{tree}` directly.
- `tests/test_doctor.py`: replaced the test that called the private `doctor._delete_local` with one that runs the public `--fix` path. Corrected the draft's ignored-file expectation to what git actually prints (`work/`: git collapses a directory whose contents are all ignored). Added fixture worktrees and tests for each remaining guard (see the inventory below).

## Touch zones

The final set is a subset of the brief's: `specy_road/bundled_scripts/doctor.py` (new), `specy_road/bundled_scripts/branches_cli.py`, `specy_road/cli.py`, `specy_road/cli_usage.py`, `specy_road/templates/specyrd/commands/specyrd-finish.md`, `docs/git-workflow.md`, `tests/test_doctor.py`. `specy_road/feature_rm_registry.py` needed no change.

## Verification

- `pytest tests/test_doctor.py tests/test_branch_cleanup.py`: 21 passed.
- Full `pytest`: 2356 passed, 2 skipped, 1 failed. The failure is `tests/test_finish_task_commands.py::test_finish_already_done_on_branch_when_complete_and_deregistered`, and it fails the same way at the base `6bcfeb8` in a clean worktree, so it predates this leaf and is not touched here.
- `ruff check` on the changed files passes. Repo-wide `ruff check specy_road tests scripts` reports one pre-existing C901 in `tests/test_grind_session.py`, which this branch does not touch.
- `scripts/check_clones.py` (pylint 4.1.3, as in CI) reports 0 new clones.
- `scripts/check_test_private_imports.py` reports 0 new.
- `specy-road file-limits`, `validate` and `export --check` on the dogfood fixture all pass.

Notes for reviewers:

- The squash probe writes one unreferenced commit object per unmerged branch, even in a dry run. Refs and the working tree are untouched, and `git gc` collects the objects.
- `--fix` deletes an unmerged unclaimed branch too once confirmed. The list prints its commit count first, and the docs say so.

## Added

- `branches_cli.fetch_integration`: shared resolve-defaults and `fetch --prune` for prune and doctor (it removes the clone the gate flagged).
- `branches_cli.feature_branches` / `live_branches`: these existing helpers were made public for cross-module use. No new logic.
- `doctor.py` (from the checkpoint, kept): `merged_how` and `_all_upstream` for A2. `_complete_leaves` for the "leaf Complete" reason. The remover helpers: `_delete_local` (tip check), `_delete_remote` (lease), `_remove_worktree`, `_drop_stash` (find again by sha), `_prune_row` (reuses `registry-prune --remove`). `_ignored_note` warns before `worktree remove` deletes ignored files. `_confirm` and `_fix` handle the per-kind questions and the report (A3). `_PROBE_IDENT` exists because `commit-tree` needs an identity on CI runners that have none.
- Guards kept, each with the test that reaches it:
  - Orphan branch, no merge base: `test_merged_how_needs_the_patch_upstream_not_just_the_files`.
  - Locked worktree and detached-unmerged worktree skipped: the `wt-locked` and `wt-wip` fixture rows in the dry-run and fix tests.
  - Current worktree skipped: `test_doctor_never_lists_the_worktree_it_runs_in`.
  - Moved local branch, leased remote branch, stash already gone: `test_fix_leaves_what_changed_after_listing`.
  - No answer on stdin: `test_fix_without_an_answer_stops_before_removing`.
  - Fetch fails, roadmap unreadable at the base: `test_doctor_refuses_without_a_fresh_roadmap` (parametrized).
- Mocks: `builtins.input` is monkeypatched, in two tests to answer the per-kind questions and in one to raise `EOFError`. In `test_fix_leaves_what_changed_after_listing` it also changes the repo between listing and removal. `PYTHONPATH` is set so `--fix` can run `registry-prune` as a subprocess.
- Tests (`tests/test_doctor.py`): the dry run lists every kind and changes nothing; CLI wiring; `--fix --yes` removes everything listed and keeps the look-alikes; answering "no" removes nothing; no stdin stops; changes made after listing are left alone; the current worktree is never listed; patch-content merged detection, including different content on the same path and an orphan branch; the refusal cases (failed fetch, unreadable base).
