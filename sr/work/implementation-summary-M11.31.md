# Implementation summary: M11.31 (`worktree-prune`)

## What changed

- **`specy_road/worktree_prune.py`** (new): `plan_prune(root, node_id)` finds the leaf's worktree (`work/.worktrees/<codename>` in the main checkout, via `reviews_root`, the same place `worker delegate` creates it) and collects every reason not to remove it, plus the ignored files removal would delete. `remove(plan)` removes each nested repository (a linked worktree with `git worktree remove --force` in the main checkout's copy, a full clone with `rmtree`) and then the leaf's worktree.
- **`specy_road/bundled_scripts/worktree_cli.py`** (new): `specy-road worktree prune <ID> [--yes] [--repo-root]`. Prints the refusals and exits 1, or lists nested repos and ignored files. Without `--yes` it removes nothing and exits 0.
- **`specy_road/cli.py`**: registers `worktree` in `_FORWARDED`.
- **`docs/git-workflow.md`**: new "Retiring a leaf's worktree (`worktree prune`)" section, an index line in the agent quickstart, and the nested-repo "Removing the leaf's worktree" bullet now points to the command.
- **`tests/test_worktree_prune.py`** (new): 23 tests.

## Acceptance

- **A1**: the command refuses unless both `feature/rm-<codename>` (when it exists locally) and the worktree's `HEAD` are ancestors of the integration ref. That ref is `base_ref`: `<remote>/<integration_branch>`, else the local branch. Nothing is fetched, so a stale ref can only make the check stricter. It also refuses on any non-ignored `git status` entry (tracked changes or untracked files) and on any stash whose subject does not name another branch. That covers stashes made on the leaf's branch, on a detached `HEAD`, or stored under a custom subject. The stash stack is shared across worktrees, so a stash is passed over only when git's own `WIP on <b>:` / `On <b>:` names some other branch `<b>` (see Rework rounds 1 and 2). It lists `!!` entries from `git status --porcelain --ignored --untracked-files=all`, one per file, including files inside ignored directories (Rework round 4), and removes only with `--yes`. Tests: unmerged, merged locally but not pushed, tracked change, untracked file, stash, and clean (list without `--yes`, removal with it, branch kept).
- **A2**: for each `nested_repos` path that is a repository top inside the leaf worktree:
  - **Linked worktree vs full clone:** the type is decided by comparing its git common dir with the main checkout's copy.
  - **Linked worktree:** it shares refs and stash with the copy, so only `HEAD` is checked. It must be contained in some `refs/heads` or `refs/remotes` of the copy. Stashes are judged as in A1.
  - **Full clone:** `HEAD`, every local branch tip and every remote-tracking tip of the clone must be contained in a branch or remote-tracking ref of the main checkout's copy. The clone's own remote-tracking refs are tips that would be deleted with it, never a place that holds commits (Rework rounds 2 and 3). Any stash refuses.
  - **All nested repos:** any non-ignored status entry refuses, and ignored files are added to the list.
  - **Tests:** detached commit, edit and stash in a linked worktree; a stash made in the detached (uncovered) linked worktree; a commit on the leaf branch, which passes because that branch keeps it; clean removal of both linked worktrees, which leaves the copies' `worktree list` with one entry; and in a full clone, an unpushed branch refused until it is pushed to the copy, then removed; a branch held only by the clone's stale `origin/topic`, which is refused; an `origin/topic` with no local `topic` whose branch left the copy, which is refused; plus an edit and a stash.

## Touch zones

Confirmed as listed: `specy_road/bundled_scripts/worktree_cli.py`, `specy_road/worktree_prune.py`, `specy_road/cli.py`, `docs/git-workflow.md`, `tests/`. Not changed, outside the zones: `specy_road/cli_usage.py` (`USAGE_TEXT`). `specy-road --help` does not list `worktree prune` yet, and a later change could add one line there.

## Verification

- `python -m pytest -q -n 4 tests/test_worktree_prune.py tests/test_validate_stale_commands.py tests/test_nested_repo_worktrees.py tests/test_nested_repo_finish.py tests/test_doctor.py tests/test_ready_command.py tests/test_branch_cleanup.py`: 93 passed (before the last test was added). `python -m pytest -q -n 4 -p no:cacheprovider tests/test_worktree_prune.py`: 16 passed.
- `python -m pytest -q -n 4 -p no:cacheprovider tests/test_cli.py tests/test_cli_imports_without_gui_extra.py tests/test_cli_query_commands.py tests/test_cli_version.py tests/test_doc_links.py tests/test_file_limits_gitignore.py tests/test_skill_mirrors.py tests/test_shared_checkout_guidance.py tests/test_validate_strict.py tests/test_prerelease_files.py tests/test_agents_md_block.py tests/test_touch_zone_tracked.py tests/test_upgrade.py`: 125 passed.
- `specy-road file-limits`: OK. `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0. `ruff check` on the changed Python files: clean.
- The full `pytest -n 4` run did not finish within the harness's 10-minute command cap and was stopped, so it is not claimed.

## Rework round 1 (review `gpt-5.6-sol-medium`, blocked at a7987f29)

- **Required change 1** asked that a stash created in a detached linked nested worktree (subject `On (no branch): ...`) refuse the prune, with a public-behavior regression test. Changes:
  - **`specy_road/worktree_prune.py`:** for a linked worktree, `_stashes` now also matches `WIP on (no branch):` / `On (no branch):`. Git does not record which worktree made a detached stash, and the stack is shared, so any such stash in the copy refuses. That can over-refuse, which is the safe direction.
  - **The leaf's own worktree:** the same function checks it, so a detached-`HEAD` stash there now refuses too. That case is reachable, because `finish --delete-branch` leaves a delegate worktree detached. The main-tree message now reads `stashes made on <branch> or a detached HEAD`.
  - **Docs and help text:** the module docstring, the `worktree prune` help text and `docs/git-workflow.md` say the same.
  - **Test:** `test_a_stash_made_in_a_detached_nested_linked_worktree_refuses_the_prune` is new. The main-worktree stash case's expected message is updated to the new wording, with the same subject.
- **Red-green:** the new test fails against `a7987f29`'s `worktree_prune.py` (1 failed) and passes with the fix.
- **Touch zones:** no file outside the touch zones was needed.
- **Verification:** `python -m pytest -n 4 -q -p no:cacheprovider tests/test_worktree_prune.py` gives 17 passed. `specy-road file-limits` is OK, and `ruff check` on the changed Python files is clean.

## Rework round 2 (review `gpt-5.6-sol-medium`, blocked at 0ec9498b)

- **Required change 1** asked that linked-worktree stashes whose subject cannot be safely attributed refuse the prune, custom subjects included, with a public CLI test. Changes:
  - **`specy_road/worktree_prune.py`:** `_stashes` turned around. For a linked worktree, every stash refuses unless git's own subject form (`WIP on <b>:` / `On <b>:`, matched by the new `_STASH_ON`) names a branch `<b>` other than the leaf's branch and `(no branch)`. A subject stored with `git stash store -m` that names no branch now refuses. A git ref name cannot contain `:`, so the captured name is exact.
  - **Messages and docs:** the leaf worktree's refusal now reads `stashes that may be this worktree's: …`. The module docstring, help text and `docs/git-workflow.md` say the same.
  - **Test:** `test_a_custom_subject_stash_refuses_but_another_branchs_does_not` is new. Through the CLI with `--yes`, a stash stored as `notes for later` refuses (exit 1), the main checkout's `On main: …` stash is not listed, and the worktree stays.
- **Required change 2** asked that a clone's own remote-tracking refs not count as durable, with a public CLI test for a stale one. Changes:
  - **`specy_road/worktree_prune.py`:** `_lost_tips` now counts only a branch or remote-tracking ref of the main checkout's copy. The clone's own `refs/remotes` check is removed, because those refs go with the clone and may be stale. This is the reviewer's conservative option. The refusal now reads `commits on no branch or remote-tracking ref of <copy>`.
  - **Docs and help text** are updated to match.
  - **Test:** `test_a_full_clone_branch_held_only_by_its_own_stale_remote_tracking_ref_is_refused` is new. The clone pushes `topic` to the copy, `topic` is then deleted in the copy, and the clone's `origin/topic` is left stale. The CLI with `--yes` exits 1, names `topic`, and leaves the clone and the leaf worktree in place.
- **Red-green:** both new tests fail against `0ec9498b`'s `worktree_prune.py`: the CLI exits 0 and removes the worktree (2 failed). They pass with the fix.
- **Touch zones:** no file outside the touch zones was needed.
- **Verification:** `python -m pytest -n 4 -q -p no:cacheprovider tests/test_worktree_prune.py` gives 19 passed. `specy-road file-limits` is OK, and `ruff check` on the changed Python files is clean.

## Rework round 3 (review `cursor-grok-4.6-high`, blocked at ae8e013b)

- **Required change 1** asked that a full clone's remote-tracking tips be treated as commits deleted with the directory: they must be held by a branch or remote-tracking ref of the main checkout's copy, never by the clone's own `refs/remotes`. It also asked for a public CLI regression test. Changes:
  - **`specy_road/worktree_prune.py`:** for a clone, `_lost_tips` now reads `HEAD` plus every `refs/heads` and `refs/remotes` tip of the clone, in one `for-each-ref` with names and shas. Each tip must be contained in `refs/heads` or `refs/remotes` of the copy. As before, the clone's own refs are never a holding location. A linked worktree still checks only `HEAD`.
  - **Docs:** the module docstring, help text and `docs/git-workflow.md` say the same.
  - **Test:** `test_a_full_clone_remote_tracking_ref_whose_branch_left_the_copy_is_refused` is new. The clone pushes `topic` and deletes its local `topic`, so only `origin/topic` holds the commit. The copy then deletes `topic`. `worktree prune M1 --yes` exits 1, names `origin/topic`, and leaves the clone and the leaf worktree. The clean full-clone prune still passes, because the clone's `origin/main` and `origin/HEAD` are held by the copy's `main`.
- **Red-green:** the new test fails against `ae8e013b`'s `worktree_prune.py`: the CLI exits 0 and removes the clone (1 failed). It passes with the fix.
- **Touch zones:** no file outside the touch zones was needed.
- **Verification:** `python -m pytest -n 4 -q -p no:cacheprovider tests/test_worktree_prune.py` gives 20 passed. `specy-road file-limits` is OK, and `ruff check` on the changed Python files is clean.

## Rework round 4 (review `gpt-5.6-sol-medium`, blocked at 29586255)

- **Required change 1** asked that the list name every ignored file removal deletes, including files below an ignored directory, with a public CLI regression test showing the dry run names the contained files before `--yes` removes the worktree. Changes:
  - **`specy_road/worktree_prune.py`:** `_status`, shared by the leaf worktree and each nested repo, now runs `git status --porcelain --ignored --untracked-files=all`. Git then lists each file inside an ignored (or untracked) directory instead of the bare directory. Nested repos inside the leaf worktree are still left out of its list by the prefix skip, and are listed file by file from their own status.
  - **Docs and help text:** the help text and `docs/git-workflow.md` say that files inside ignored directories are listed.
  - **New test:** `test_the_dry_run_names_each_ignored_file_inside_an_ignored_directory`. A merged leaf ignores `build/` and holds `build/app.bin` and `build/deep/cache.db`. The dry run exits 0, prints both paths and leaves the worktree; `--yes` then removes it.
  - **Updated test:** `test_a_plain_directory_at_a_nested_path_is_checked_as_part_of_the_worktree` now expects `lib/notes.txt` rather than `lib/`. That is the same input with the more precise listing.
- **Red-green:** the new test fails against `29586255`'s `worktree_prune.py`, which printed only `build/` (1 failed). It passes with the fix.
- **Touch zones:** no file outside the touch zones was needed.
- **Verification:** `python -m pytest -n 4 -q -p no:cacheprovider tests/test_worktree_prune.py` gives 21 passed. `specy-road file-limits` is OK, and `ruff check` on the changed Python files is clean.

## Rework round 5 (review `gpt-5.6-sol-medium`, blocked at 8cc8aba5)

- **Required change 1** asked that the command fail closed when stash state cannot be read in the leaf worktree or any nested repository, with public-CLI coverage showing `--yes` refuses and preserves the leaf worktree and a nested full clone when `git stash list` fails. Changes:
  - **`specy_road/worktree_prune.py`:** `_stashes` now reads `git stash list` with `git_stdout` and returns `None` on failure, where before it turned the failure into "no stashes". `plan_prune` (leaf worktree) and `_check_nested` (each nested repo) refuse on `None`, with `cannot read the stash list` and `<label>: cannot read the stash list`.
  - **Same pattern in the clone's ref listing:** `_lost_tips` read a full clone's `refs/heads` and `refs/remotes` with `or ""`, so a failed listing meant "no tips to check". It now returns `None` on failure, and `_check_nested` refuses with `cannot list its branches and remote-tracking refs`.
  - **Docs:** `docs/git-workflow.md` says that an unreadable status, stash list or ref listing refuses.
  - **Tests:** `test_an_unreadable_stash_list_in_the_leaf_worktree_refuses` and `test_an_unreadable_stash_list_in_a_nested_full_clone_refuses` are new. Both break `refs/stash` (the main checkout's, which the leaf worktree shares, and the clone's own), run `worktree prune M1 --yes`, and check exit 1, the refusal text, and that the directories remain.
- **Red-green:** both tests fail against `8cc8aba5`'s `worktree_prune.py`: the CLI exits 0 and removes the worktree (2 failed). They pass with the fix.
- **Touch zones:** no file outside the touch zones was needed.
- **Verification:** `python -m pytest -n 4 -q -p no:cacheprovider tests/test_worktree_prune.py` gives 23 passed. `specy-road file-limits` is OK, and `ruff check` on the changed Python files is clean.

## Added

### Helpers
- `worktree_prune.PruneError`: the node, its codename or its worktree cannot be found. The CLI turns it into exit 1.
- `worktree_prune.PrunePlan`: carries the main root, worktree, branch, refusals, ignored paths and nested repos from the checks to the removal.
- `worktree_prune.leaf_worktree`: resolves node id to codename, worktree path and branch, and refuses a path that is not a worktree of this repository.
- `worktree_prune._status`: splits `git status --porcelain --ignored --untracked-files=all` into changed and ignored paths, leaving out nested repo directories. It reads raw stdout because `git_text` strips the leading space of ` M` lines. `--untracked-files=all` lists each file inside an ignored directory rather than the directory (round 4).
- `worktree_prune._STASH_ON` / `_stashes`: decide which stashes refuse. A clone refuses on any stash. A linked worktree refuses on every stash whose git-form subject does not name another branch; this covers the leaf's branch, `(no branch)` and custom subjects (round 2).
- `worktree_prune._held` / `_lost_tips`: find commits no branch or remote-tracking ref of the main checkout's copy holds. For a clone, the tips are `HEAD`, its branches and its remote-tracking refs (round 3), and none of the clone's refs counts as holding anything (round 2). Checking only tips is enough, because a contained tip keeps all of its ancestors.
- `worktree_prune._check_nested`: runs the A2 checks per nested repo, distinguishing linked worktrees from clones.
- `worktree_prune.plan_prune` / `remove`: the A1 checks plus the removal (nested repos first).
- `bundled_scripts/worktree_cli.py` (`cmd_prune`, `build_parser`, `main`): the CLI, shaped like `branches_cli.py`.

### Branches and guards
- No integration ref: refuse, because merged cannot be judged.
- The branch check is skipped when the local branch is gone. The worktree's `HEAD` is still checked.
- A nested path that is not a repository top inside the worktree is skipped by the nested checks. The main worktree's status leaves out only the nested repos that were actually checked, so such a directory is still checked (or listed as ignored) as part of the worktree.
- Unreadable status (main or nested): refuse.
- Unreadable stash list (leaf worktree or nested repo): refuse (round 5).
- A full clone whose branches and remote-tracking refs cannot be listed: refuse (round 5).
- `--force` on removal is used only after the checks, so that ignored files do not block git. A locked worktree still fails.

### Mocks
- none

### Tests (`tests/test_worktree_prune.py`)
- `test_unmerged_branch_is_refused`: A1, unmerged branch and `HEAD`.
- `test_merged_locally_but_not_pushed_is_refused`: A1, only the remote-tracking integration ref counts when it exists.
- `test_unknown_node_and_missing_worktree_are_errors`: the `PruneError` paths.
- `test_unsaved_work_in_the_worktree_is_refused` (3 cases: tracked change, untracked file, stash on the branch): A1 refusals, via the API and the CLI with `--yes`.
- `test_clean_prune_lists_ignored_files_and_removes_only_with_yes`: A1, clean prune through the CLI.
- `test_clean_prune_removes_nested_linked_worktrees`: A2, clean prune with linked nested worktrees.
- `test_unsaved_work_in_a_nested_linked_worktree_is_refused` (3 cases: detached commit, edit, stash): A2, linked-worktree refusals.
- `test_a_commit_on_the_leaf_branch_of_a_nested_linked_worktree_is_kept_by_that_branch`: A2, a commit on the leaf branch is not counted as lost.
- `test_full_clone_branch_held_nowhere_is_refused_until_pushed`: A2, a full clone's unpushed branch is refused, then a clean prune of the clone.
- `test_unsaved_work_in_a_nested_full_clone_is_refused` (2 cases: edit, stash): A2, full-clone refusals.
- `test_a_stash_made_in_a_detached_nested_linked_worktree_refuses_the_prune`: rework round 1. A2, an `On (no branch):` stash in a detached linked nested worktree refuses, through `plan_prune` and through the CLI with `--yes`, which leaves both directories in place.
- `test_a_plain_directory_at_a_nested_path_is_checked_as_part_of_the_worktree`: guards the skip so that a non-repository directory at a nested path is not passed over unchecked. Since round 4 it expects the contained file, `lib/notes.txt`, in place of `lib/`.
- `_break_stash` (test helper): points `refs/stash` at a missing object, so `git stash list` really fails while status and the other refs still read. No mock is involved.
- `test_an_unreadable_stash_list_in_the_leaf_worktree_refuses`: rework round 5. A1, the CLI with `--yes` exits 1 with `cannot read the stash list` and the leaf worktree stays.
- `test_an_unreadable_stash_list_in_a_nested_full_clone_refuses`: rework round 5. A2, the CLI with `--yes` exits 1 with `nested repo lib (full clone): cannot read the stash list`, and the clone and the leaf worktree stay.
- `test_the_dry_run_names_each_ignored_file_inside_an_ignored_directory`: rework round 4. A1, the dry run names `build/app.bin` and `build/deep/cache.db` inside the ignored `build/`, and `--yes` then removes the worktree.
- `test_a_custom_subject_stash_refuses_but_another_branchs_does_not`: rework round 2, item 1. A1, a stash with an unattributable subject refuses through the CLI with `--yes` and the worktree stays; another branch's stash is not listed.
- `test_a_full_clone_branch_held_only_by_its_own_stale_remote_tracking_ref_is_refused`: rework round 2, item 2. A2, a branch held only by the clone's stale remote-tracking ref refuses through the CLI with `--yes`, and the clone and the leaf worktree stay.
- `test_a_full_clone_remote_tracking_ref_whose_branch_left_the_copy_is_refused`: rework round 3. A2, a clone with `origin/topic` and no local `topic`, after the copy deleted `topic`. Through the CLI with `--yes` it exits 1, names `origin/topic`, and leaves the clone and the leaf worktree.
