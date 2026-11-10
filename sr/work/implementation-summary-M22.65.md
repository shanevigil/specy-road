# Implementation summary — M22.65 `work-dir-ignored`

## What changed

- **`specy_road/agent_ignores.py`:** `GITIGNORE_LINES` now has `work/*` and the three re-includes `!work/README.md`, `!work/.gitkeep` and `!work/*.template.md`. They replace every per-path `work/` line: session files, `RUNTIME_WORK_DIRS`, `work/chores/.garden.json` and the brainstorm prompts. `_GITIGNORE_NOTE` is reworded. `_prefixed` puts the project prefix after a leading `!` (nested layout: `!sr/work/README.md`). `SESSION_WORK_FILES` is removed; after the change only tests used it. `RUNTIME_WORK_DIRS` and `role_prompt_rca.dirty_check` are untouched (source-identical, A2).
- **Templates:** the `templates/project/.gitignore` comments say all of `work/` is ignored. They also say the scaffold stays tracked, that a project re-includes paths after the block, and that files already tracked stay tracked until `git rm --cached`. `templates/project/work/README.md` says the same. `templates/project/roadmap/git-workflow.yaml` sets `implementation_summary: local` (A3).
- **Docs:**
  - `docs/git-workflow.md` gains a "`work/` is gitignored by default" paragraph after `cleanup_work_artifacts_on_finish`. The `track_worker_logs` paragraph now says the block covers `work/worker-logs/` and names the re-include.
  - `docs/git-workflow-preferences.md` says new projects set `local` and that **a reviewer in another clone does not see the summary**.
  - `docs/install-and-usage.md`: the "bundled `.gitignore` ignores only…" paragraph is rewritten.
- **CHANGELOG:** `[Unreleased]` gets a new `### Changed` section with two notes. The first covers the block: existing tracked files and the printed, never-run `git rm --cached`, plus re-includes. The second covers the summary default.
- **Toolkit root `.gitignore`:** the managed block is re-rendered for the `sr/` layout with `apply_agent_ignores(root, "sr/")`, the same call `refresh-stubs` makes for this block. I did not run `refresh-stubs` itself, because its dry run would also rewrite `CLAUDE.md` and `sr/.specyrd/AGENTS.md`, which are outside the zones. `.cursorindexingignore` came out unchanged.
- **`sr/work/done/` untracked (A4):** all files are kept on disk. This includes the 4 summaries the `origin/WIP/improvements-0-3-1` merge brought in, 225 files in all. The untrack is its own commit. `git commit --only` re-stages on-disk files, so I moved the directory aside for that one commit and then moved it back.

## Tests updated row by row (A5)

- **`tests/test_init_project_gitignore.py`** `test_init_project_ships_a_gitignore`: it asserted `work/prompt-*.md` and the other session lines. It now asserts that the `work/` lines are exactly the four new ones, parametrized embedded and nested `sr/` (block row).
- **`tests/test_init_project_reports.py`:** the `SESSION_WORK_FILES` loops in `test_existing_gitignore_reported_as_updated_with_the_runtime_rules`, `test_fresh_gitignore_keeps_the_template_header_and_one_copy_of_each_rule` and `test_nested_layout_writes_no_project_gitignore` now loop over the four new rules. Nested is `sr/work/*` and `!sr/work/...`.
- **`tests/test_worker_state.py`** `test_a_leafs_own_worker_logs_neither_breach_zones_nor_block_redelegation`: another leaf's `work/worker-logs/` (and this leaf's own) is now ignored. So it no longer shows in reconcile's untracked lists, and `delegate` succeeds with it present.
- **`tests/test_agent_ignores.py`:** `test_worker_state_stays_ignored_and_worker_logs_never_are` is now `test_all_of_work_is_ignored_but_the_scaffold_and_re_includes` (embedded and nested). It covers runtime dirs, chore records, the brief, the summary, `work/done/` and worker logs (all ignored), the five scaffold files (not ignored), and a user `!work/worker-logs/` line after the block (no longer ignored).

## Test fallout outside the first zones (zones added by the operator, 084736c8)

Each scenario built on the old per-path lines gets its new equivalent. No assertion that still applies was dropped.

- **`tests/test_m13_12_quieter_notices.py`:** the repeated block pattern used in the "above the markers" cases is now `work/*`, where it was `work/reviews/` (no longer a block line). This affects `test_two_repeated_patterns_get_one_notice`, `test_no_repeats_print_nothing`, `test_patterns_git_reads_differently_are_not_repeats`, `test_trailing_unescaped_spaces_and_a_crlf_are_what_git_drops` and the `GIT_READS` rows.
- **`tests/test_m13_7_notices.py`:**
  - `test_a_git_dir_from_a_hook…`: the rule column is `(work/*)` where it was `(work/prompt-*.md)`.
  - `CASES` "r1 pathspec-only match" uses `work/sub/x.template.md`, which a pathspec `work/*.template.md` matches but the re-include does not, so it is hidden.
  - "r5 tracked by an older rule only" moves the file outside `work/` (`notes/old.md`) so that no block rule reaches it.
  - "r7 nested rule decides": the committed `work/.gitignore` is now a tracked match.
  - "r7 tracked negated in a nested file": the untracked `work/.gitignore` is now hidden.
- **`tests/test_m13_7_gitignore_symlinks.py`** "nested symlink": the `work/.gitignore` link itself is now hidden too.
- **`tests/test_finish_work_cleanup.py`** `test_an_opted_in_completed_worker_goes_through_review_to_finish`: this is the **re-include row**. A new helper `_opt_in_after_the_block` appends `!work/worker-logs/`, `!work/implementation-summary-*.md` and `!work/done/` after the block. The finish assertion now also checks that the ignored-logs warning (`!work/worker-logs/` in stderr) does not fire. The "another leaf's logs still count" check stays valid under the re-include.
- **`tests/parity/test_leaf_loop.py`** `_implement_and_review`: commits only `src/hello.py`. The brief and summary are ignored now (`git add` refused them) and stay local per the new scaffold default.

## Goldens (A6): one fragment each, edited by hand, never regenerated whole

- **`tests/parity/golden/upgrade/rc3-dry-run.txt`:** one line inserted after `== validate` (line 31).
  - Before: nothing between `== validate` and `OK: roadmap and registry validate.`
  - After: `notice: roadmap/git-workflow.yaml implementation_summary is commit (set or default), but .gitignore ignores 1 leaf summary: work/implementation-summary-M1.1.md (.gitignore:57:work/*); the ignore rule wins for those leaves: …` This is the intended notice for an existing project on the `commit` default.
- **`tests/parity/golden/leaf_loop/merge.json` and `pr.json`:** the same fragment in each.
  - Before: `"worktree": [ "?? work/brief-M1.2.md" ]`
  - After: `"worktree": []` (the brief is ignored now).

## Deviations and notes

- **A2, "tracked still seen":** a modified tracked `work/brief-M1.md` is **not** printed by `dirty_check`. `dirty_check` already leaves out every `work/brief-*.md` as bookkeeping, and A2 also requires it to stay source-identical. Reconcile reports both paths, `delegate` fails on both, and `dirty_check` reports the modified tracked `work/chores/tidy.md`. The test says this in a comment.
- **Final touch zones used:** the original list plus the operator's additions. No other path changed.
- **The summary file itself:** this file sits under the now-ignored `sr/work/*`. The executor prompt asks for it to be committed by explicit path, so I used `git add -f` on this one path, as the toolkit's own `sr/` roadmap still expects.

## Verification

- `pytest -n 4` over the whole suite, run in three parts to fit the tool's time cap: 2696 passed; 4249 passed and 13 skipped; parity 232 passed and 5 skipped.
- `ruff check specy_road tests scripts` passes. `specy-road file-limits` is OK.
- Dogfood `validate`, `export --check` and `digest --check` all pass.

## Added

- `tests/test_init_project_gitignore.py::test_init_project_ships_a_gitignore[sr]` (parametrize): block row, nested prefix after `!`.
- `tests/test_init_project_gitignore.py::test_a_fresh_clone_holds_the_work_scaffold`: scaffold row.
- `tests/test_init_project_gitignore.py::test_a_new_project_keeps_summaries_local_without_a_notice`: summary-quiet row.
- `tests/test_init_project_gitignore.py::test_upgrade_prints_the_untrack_command_for_a_file_already_tracked_under_work`: upgrade row (command printed, file still tracked).
- `tests/test_runtime_dirs_not_dirty.py::test_chore_records_beside_a_claimed_leaf_trip_no_clean_tree_check`: chore-records row.
- `tests/test_runtime_dirs_not_dirty.py::test_files_still_tracked_under_work_are_still_seen`: tracked-still-seen row.
- Test helpers `_new_block_repo` and `_chore` in `tests/test_runtime_dirs_not_dirty.py`: set up the two new rows.
- Test helper `_opt_in_after_the_block` in `tests/test_finish_work_cleanup.py`: the re-include row's setup, kept out of the test body to stay under the 80-line function cap.
- Package helpers, branches or guards: none. `_prefixed` gained one conditional for a leading `!`, which the nested re-includes need.
- Mocks: none.

## Fix round 1 (review by gpt-6.1-sol at 0d0c8fca)

Sol found that A2 contradicted itself. It asked `dirty_check` to report a modified tracked `work/brief-M1.md`, and also asked that `dirty_check` stay source-identical. Its `work/brief-*.md` pathspec exclusion hides tracked and untracked files alike, so both could not hold. I stopped and asked the coordinator.

The operator chose to amend A2 (0cc7f99b). `dirty_check` stays source-identical and keeps leaving out briefs, summaries and the runtime directories. `worker reconcile` and `delegate` must catch a modified tracked `work/brief-M1.md` and `work/chores/<slug>.md`, and `dirty_check` must report the tracked chore record. Narrowing `dirty_check` moves to M23.

- **`tests/test_runtime_dirs_not_dirty.py::test_files_still_tracked_under_work_are_still_seen`** now asserts the amended row through `dirty_check` in both directions: ` M work/chores/tidy.md` is reported and `work/brief-M1.md` is not. The reconcile and delegate assertions are unchanged; both paths are seen there.
- Sol's other findings: none. The other acceptance items and the assert-loss and removed-test rows were marked pass.
- The merges of `origin/WIP/improvements-0-3-1` (95c77cdd, 675dc5d6) each brought in newly tracked `sr/work/done/` summaries: M16.2.4, M22.53 and M22.67. I untracked them in their own commit, which keeps A4 whole. All 228 files are on disk and none is tracked.

## Probes

- **Merged `origin/WIP/improvements-0-3-1` (95c77cdd):** clean merge, no conflicts.
- **Temp repo, `dirty_check("", "M1.1")`, tracked-then-modified files:** `work/chores/tidy.md` is reported. `work/brief-M1.md`, `work/brief-M1.1.md`, `work/implementation-summary-M1.md`, `work/reviews/M1/x.md` and `work/.workers/w.json` are all hidden. The same holds for `work/.sessions/`, `work/.worktrees/` and the leaf's `work/worker-logs/<ID>/`, which use the same pathspec form.
- **`delegate` uncommitted-work check** (`worker_ops_launch.py:365`): exempts only `??` entries that are bookkeeping, so a modified tracked file anywhere under `work/` blocks delegate. This is covered by `test_files_still_tracked_under_work_are_still_seen`, which uses the brief and the chore record.
- **`worker reconcile`:** reports both tracked paths as changed outside the zones. Same test.
- **`ignore_report` / `upgrade`:** lists tracked files under `work/` and prints `git rm --cached`. Covered by `test_upgrade_prints_the_untrack_command_for_a_file_already_tracked_under_work`.
- After the second merge: the targeted tests plus `tests/parity` gave 469 passed and 5 skipped. `ruff check specy_road tests scripts` and `specy-road file-limits` are OK.
- `git ls-files sr/work/done` lists 0 files after the merges; 228 files remain on disk.
