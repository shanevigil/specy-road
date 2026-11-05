# Implementation summary — M12.2 Every refusal names its fix

Branch `feature/rm-every-refusal-names-its-fix`, base `6d080df2`, code commit `558f0975`.

## What changed

- **A1 — remove-dependency** (`specy_road/bundled_scripts/roadmap_crud_dependency_ops.py`): `cmd_remove_dependency()` resolves its argument with `resolve_dependency_refs()`, as `cmd_add_dependency()` does, so a display id, node_key or archived key all work. A dependency the node does not list now exits 1 and prints the node's actual dependencies as `id (node_key)` pairs (or `none`) plus `` `specy-road list-dependencies <ID>` ``. The old `[ok] … did not list` exit-0 path is gone. An argument that resolves to nothing keeps the resolver's ValueError text as an `error:` line, followed by the same list-dependencies hint. A key the node lists but the roadmap no longer has (dangling) can still be removed by that key, because it is matched against the node's list before resolution. Without that, the change would stop a dangling key from being removed.
- **A2 — unclean tree** (`specy_road/bundled_scripts/repo_ops.py`, `mark_implementation_reviewed.py`): `repo_ops` gains `dirty_paths()` (porcelain lines, reusing `_OUTSIDE_WORK`) and `unclean_tree_details()`. The second lists at most 20 paths, then `… and N more`, then how to clear them (commit / `git stash push -u -m <tag>` / `git restore`), then says `work/` is ignored when the check ignores it. `assert_working_tree_clean()` prints these lines, so every caller (`do_next_task`, `sync_integration_branch`) gets the list. Both refusal sites in `mark_implementation_reviewed.py` (leaf approval and milestone full review) now call `assert_working_tree_clean(ROOT, except_work=True)` in place of their inline copies. The first line is now the shared `UNCLEAN_TREE_MESSAGE`. `working_tree_clean()` itself is unchanged; existing tests monkeypatch `git_checked` under it.
- **A3 — abort-task-pickup** (`abort_task_pickup.py`): `_exit_if_base_checked_out_elsewhere()` now also takes `node_id`. It prints `` `git -C <wt> status --short` `` first, saying that removal discards pickup's untracked `work/brief-<ID>.md` and that `--force` also discards any other untracked file. It then prints `` `git worktree remove --force <wt>` ``. `<wt>` is the worktree's git top level, shell-quoted, so the command still targets the worktree when the project root is nested (e.g. `sr/`). `--force` discards only untracked files here, because tracked changes were already refused by `_assert_no_tracked_changes()`.
- **A4 — rule** (`docs/contributor-guide.md`): new "Refusals" subsection under Project stewardship, plus a mention in the section index. A non-zero exit prints what failed, why, and a runnable `specy-road …`/`git …` next step.

## Touch zones

Final list is unchanged from the brief: `specy_road/bundled_scripts/roadmap_crud_dependency_ops.py`, `specy_road/bundled_scripts/mark_implementation_reviewed.py`, `specy_road/bundled_scripts/abort_task_pickup.py`, `specy_road/bundled_scripts/repo_ops.py`, `docs/contributor-guide.md`, `tests/`. No new module was needed. File limits pass: `mark_implementation_reviewed.py` shrank, and `roadmap_crud_dependency_ops.py` is 398/400.

Not changed (outside zones, noted only): the `remove-dependency` argparse help in `roadmap_crud_argparse.py` still reads "Remove one dependency node_key if present", and its metavar is `DEP_NODE_KEY` (also in `cli_usage.py`). Both still work, but they no longer say that a display id is accepted. That is a candidate wording fix for a later chore.

## Verification

- `python -m pytest -q -n 4 tests/test_refusals_name_their_fix.py`: 13 passed.
- Red-green: the new test file against the base commit `6d080df2` (temporary detached worktree): 11 failed, 2 passed. The node_key removal and the abort parametrized case already passed on base, because the old abort hint had a backticked command, just one git refused.
- Related suites (abort, mark-implementation-reviewed gate, milestone full review, crud dependencies, prerelease s5, git helpers, registry commit scope, review hardening, finish commands): 98 passed.
- Full suite `python -m pytest -q -n 4`: 3972 passed.
- `specy-road file-limits`: OK.

## Fix round 1

Sol's review blocked `ca9615d8`; Grok approved it. Merged `origin/WIP/improvements-0-3-1` first (no conflicts). Fixes are in commit `e7352a26`.

- **F1 (A4):** the unclean-tree hint's backticked commands all contained `<path>`/`<tag>`, so none of them ran in a shell. `unclean_tree_details()` now takes `repo_root` and prints a single concrete command, ``git -C <root> stash push -u -m 'specy-road: unclean tree' -- ':/' ':(exclude)work'``. Here `<root>` stands for the real path, shell-quoted. The pathspec is the one the check itself uses (the work/ exclude is dropped when the check does not ignore work/). Commit and discard are still mentioned, but as plain prose, not as commands to copy. Both mark-implementation-reviewed sites get this through `assert_working_tree_clean()`.
- **Test integrity F1:** for the two dirty-tree cases, the parametrized CLI test now extracts the printed stash command and runs it through the shell. It then asserts that `git status` outside work/ is empty and retries the same CLI call, which must exit 0. The A2 tests assert that no `<path>`/`<tag>` remains.
- **Test integrity F2:** removed every private cross-module import. `delegate_layout` now lives in `tests/review_repo_helpers.py`, and `test_prerelease_s5.py` is updated to use it. The leaf and milestone repos are built from the public `make_review_repo`, `make_milestone_repo` and `review_text`.
- **Test integrity F3:** dropped the node_key removal case. `test_roadmap_crud_dependencies.py::test_add_remove_dependency_cli` covers it.
- Verified with targeted pytest only (97 passed across the refusal, prerelease s5, git helpers, registry scope, mark-reviewed gate, milestone review, crud dependencies, abort, review hardening and finish command suites) and `specy-road file-limits` (OK).

## Added

- `repo_ops.UNCLEAN_PATHS_SHOWN`: the 20-path cap from A2, named once.
- `repo_ops.dirty_paths()`: the porcelain lines the clean check sees (raw stdout, so the first line's status column is kept), for A2.
- `repo_ops.unclean_tree_details(repo_root, paths, *, except_work)`: formats the capped list and a runnable stash command (fix round 1), for A2. It is shared by every `assert_working_tree_clean()` caller.
- `repo_ops.UNCLEAN_STASH_MESSAGE` (fix round 1): a fixed stash message so the printed command needs no placeholder.
- Branch in `assert_working_tree_clean()`: prints the detail lines before exiting.
- `roadmap_crud_dependency_ops._refuse_unlisted_dependency()`: the A1 exit-1 message that names the node's actual dependencies.
- Branch in `cmd_remove_dependency()`: a ref already in the node's list is used as is, so a dangling key stays removable (keeps today's behaviour).
- Hint line after the resolver ValueError in `cmd_remove_dependency()`: gives that refusal a runnable next step too.
- `node_id` parameter and `shlex`/`rev-parse --show-toplevel` in `_exit_if_base_checked_out_elsewhere()`: names the brief the hint discards and quotes the worktree path git needs (A3).
- `tests/test_refusals_name_their_fix.py`:
  - `test_each_refusal_exits_1_and_names_a_runnable_next_step` (parametrized over unlisted dependency, leaf approval on a dirty tree, milestone approval on a dirty tree, abort with the base held): A4's CLI test via `python -m specy_road.cli`.
  - `test_remove_dependency_by_display_id`: A1. The node_key case was dropped in fix round 1 (it is covered by `test_roadmap_crud_dependencies.py::test_add_remove_dependency_cli`).
  - `test_remove_dependency_not_listed_names_the_actual_ones`: A1, covering a node with dependencies and one with none.
  - `test_remove_dependency_unknown_ref_keeps_the_resolver_error`: A1's unresolvable argument.
  - `test_leaf_approval_lists_the_dirty_paths` and `test_milestone_approval_lists_the_dirty_paths` (1 and 25 paths): A2 at both sites. The leaf case also checks that `work/` files are not listed.
  - `test_abort_hint_removes_the_worktree_pickup_left`: A3. It runs the printed status and remove commands on a worktree holding an untracked `work/brief-M1.1.md`, and checks that a plain `git worktree remove` is refused there.
- Local test helpers `_approve`, `_approved_leaf`, `_approved_milestone` and `_mark_reviewed` (fix round 1): build the review repos from public helpers, so no private names are imported from other test modules.
- `tests/review_repo_helpers.delegate_layout` (fix round 1): moved from `tests/test_prerelease_s5.py::_delegate_layout`, whose three callers now use it.
- Mocks: none.
