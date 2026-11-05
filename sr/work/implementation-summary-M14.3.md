# Implementation summary: M14.3

worktree prune refuses to delete another repository's worktree or checkout.

## What changed

- `specy_road/worktree_prune.py`: after `_status()` reads the leaf worktree, `plan_prune()` looks at every
  changed, untracked or ignored path and its parents below the worktree, and finds each directory that holds a
  `.git` entry (configured `nested_repos` are already skipped by `_status`, so they keep `_check_nested()`).
  Each is recorded in the new `PrunePlan.foreign` and adds a refusal naming the directory, whether it is a
  linked worktree (`.git` file; repository from `--git-common-dir`) or a checkout (`.git` directory; the
  directory itself), its branch (`rev-parse --abbrev-ref HEAD`), and the commits its upstream lacks
  (`log @{u}..HEAD`, or `HEAD --not --remotes` with no upstream; first 20, then "(and more)"), with the next
  step: land or push them, then `git -C <repo> worktree remove <dir>` (or move a checkout out).
  `remove()` returns an error and deletes nothing when `plan.foreign` is non-empty.
- `specy_road/bundled_scripts/worktree_cli.py`: docstring and `--help` description name the new refusal. The
  CLI already prints every refusal and exits 1 for preview and `--yes`, so no logic change.
- `tests/test_worktree_prune_foreign.py` (new; `tests/test_worktree_prune.py` is at 395 lines): linked worktree
  of a second repository with one unpushed commit (A2), and a detached clone with no upstream.

Touch zones confirmed accurate: `specy_road/worktree_prune.py`, `specy_road/bundled_scripts/worktree_cli.py`,
`tests/`. No change outside them.

## Verification

- `python -m pytest -q tests/test_worktree_prune_foreign.py tests/test_worktree_prune.py` — pass.
- Red/green: with `worktree_prune.py` reverted, both new tests fail (exit 1).
- Full suite `python -m pytest -n 4 -q`: 3981 passed. `specy-road file-limits` OK; `ruff check` clean.

## Added

- `PrunePlan.foreign` — records the foreign `.git` directories so `remove()` can refuse without re-scanning.
- `_foreign_dirs()` — finds directories (and parents below the worktree) holding a `.git` among the paths removal deletes.
- `_foreign_refusal()` — builds the refusal text: directory, repository, branch, unlanded commits, next step.
- `_SHOWN` — caps listed commits at 20 so a checkout with no remote does not print its whole history.
- Guard in `remove()` — refuses when `plan.foreign` is non-empty, so a caller skipping the refusals deletes nothing.
- Test `test_a_linked_worktree_of_another_repository_refuses_and_survives` — A2: refusal, commit listed, preview and `--yes` exit 1, directory survives.
- Test `test_a_checkout_of_another_repository_refuses_with_commits_no_remote_holds` — the `.git`-directory and no-upstream path of A1.
- Mocks: none.
