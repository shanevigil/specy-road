# Implementation summary: M22.31 (steering-finish-refusal)

## What changed

- **First commit (`de4953fe`)** is `git revert` of R31 (`5005042e`), with the conflicts resolved against what predecessors landed:
  - `steering_paths.py` was not restored, as the 2026-11-07 change requires.
  - Its in-tree list (`POLICY_FILES`, `SHELL_FILES`, `in_tree_class`) moved into `specy_road/steering_gate.py`. The finish classes are the only ones left, so `FINISH_CLASSES` is gone.
- **`specy_road/steering_gate.py`:**
  - `zones_or_exit` runs the implementation check and then `steering_or_exit`. `finish_task.py` calls it before any bookkeeping, as at R31's parent.
  - `steering_hits` matches exact zones only. A zone may name the path project-relative or git-root-relative. Directory and glob zones never authorize a change.
  - `roadmap/registry.yaml` is not on the list.
  - **A3, new compared to R31's parent:** the old code read a missing ref or an unreadable diff as an empty list. Now `steering_or_exit` refuses, naming the integration ref, the merge base (`git merge-base`) or the changed-path list (`diff_paths`) that could not be read.
  - The project prefix comes from `project_prefix` (git), as the implementation check gets it, instead of `git_top` + `prefix_within`.
  - The module docstring names its topic (the steering list at finish), not the file limit.
- **`docs/orchestration-steering-files.md`:** rewritten to cover the three classes and the finish refusal only. The per-turn watch content belonged to the dropped M22.5.
- **Tests:**
  - `test_steering_file_guard.py` is rewritten to cover the finish refusal only.
  - Three files now commit their policy config on `dev` and merge it into the leaf: `test_finish_merge_failure_undo.py` (`_repo` as at R31's parent, plus `_set_land`, from M22.10), `test_finish_work_cleanup.py` (`_config_on_dev` as at R31's parent, plus the M22.14 PR-mode test) and `test_finish_config_preflight.py` (`_config_on_dev`, added to the zones by the coordinator).

## Touch zones

Final list: the six original zones plus `tests/test_finish_config_preflight.py` (coordinator, `f16b7705`). No other file changed. The merge of `origin/WIP/improvements-0-3-1` brought in other leaves' files unchanged.

## Verification

- `python -m pytest -n 4 -q -p no:cacheprovider tests/test_steering_file_guard.py tests/test_finish_merge_failure_undo.py tests/test_finish_work_cleanup.py tests/test_finish_config_preflight.py`: 91 passed.
- `tests/test_finish*.py tests/test_project_layouts_outside.py`: 195 passed.
- Full suite before the merge, without the preflight fix: 6,847 passed, 8 skipped, 2 failed (both in `test_finish_config_preflight.py`, fixed above).
- `ruff check specy_road tests scripts`: clean.
- `specy-road file-limits`: OK, with existing warnings on other files only.

## Notes for reviewers

- The refusal message suggests `git checkout <ref> -- <path>`. As at R31's parent, that cannot revert a path the branch added, which needs `git rm`.
- `REVERT_HEAD` is still present in this worktree's git dir. `git revert --quit` cannot write `.git/packed-refs.lock` from the sandbox (read-only file system). Commits landed regardless.

## Added

- `steering_gate.POLICY_FILES`, `SHELL_FILES`, `in_tree_class`: the steering list, moved here from the removed `steering_paths.py` (A1).
- `steering_gate._unreadable`: the A3 refusal when the ref, merge base or diff cannot be read.
- Guards in `steering_or_exit` for a missing ref, a missing merge base and a `None` diff (A3).
- `test_finish_lands_a_steering_file_only_under_an_exact_zone`: parametrized over harness, policy and shell paths × exact, absent, directory and glob zones × embedded and nested roots (A2, A4). Refusals check that the branch tip, the registry and the index are unchanged.
- `test_a_registry_only_change_lands`: `roadmap/registry.yaml` is ignored (A2, A4).
- `test_a_diff_that_cannot_be_read_refuses_before_bookkeeping`: monkeypatches the public `steering_gate.diff_paths` to return `None`, as git failing would (A3, A4).
- `_config_on_dev` in `test_finish_config_preflight.py` and `_set_land` on `dev` in `test_finish_merge_failure_undo.py`: their setup changes policy files, which a leaf's own diff may no longer change (A4).
- Mocks: the single `diff_paths` monkeypatch above.
