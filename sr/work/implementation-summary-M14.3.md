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

## Fix round 1 (Sol R1–R3, after merging origin/WIP/improvements-0-3-1)

- **R1** — `_status()` now reads `git status --porcelain=v1 -z --ignored --untracked-files=all` and splits
  on NUL, so paths come unquoted (`sibling space`, `siblíng`). A rename/copy record (`R`/`C` in either
  status column) takes the next NUL field as its source path; both paths go in the list. A name that is
  not valid text makes the read fail, which already refuses ("cannot read git status"). Checked by hand
  on a staged `git mv 'old name' 'new näme'`: `['new näme', 'old name']`.
- **R2** — `_check_nested()` scans each configured nested repo's changed and ignored paths with
  `_foreign_dirs(d, …)`, which never returns `d` itself. `plan_prune()` combines those results with the
  outer scan and removes the configured repo directories from the set, so only the configured repository
  itself is exempt. Its existing checks are unchanged.
- **R3** — `tests/test_worktree_prune_foreign.py` builds the leaf with public helpers (`make_pickup_project`,
  `add_nested_repo`, `git`, `commit_file`) instead of importing the private `_leaf`. Both round-0 tests are kept.
- New tests: `test_foreign_worktrees_whose_names_git_quotes_refuse_and_survive` (R1) and
  `test_a_foreign_worktree_inside_a_configured_nested_clone_refuses_and_survives` (R2). Both go through the
  public CLI, assert exit 1 for the preview and for `--yes`, and assert that every directory survives.
  Both fail with `worktree_prune.py` at `cbff878c` (2 failed, 2 passed) and pass with the fix.
- Verified: `python -m pytest -q tests/test_worktree_prune_foreign.py tests/test_worktree_prune.py` →
  36 passed; `specy-road file-limits` OK; `ruff check` clean. The full suite was not rerun this round,
  as instructed.

## Fix round 1: deletion-path audit

`remove()` deletes, in order: each configured nested repo (`git -C <copy> worktree remove --force <dir>`
for a linked worktree, `shutil.rmtree` for a clone), then the leaf worktree (`git worktree remove --force`),
which also deletes its admin directory `.git/worktrees/<name>`. Nothing is deleted unless `plan.refusals`
is empty (CLI), and `remove()` itself refuses when `plan.foreign` is not empty.

Before any path is checked, the plan already refuses on these: a worker `running` in the worktree, an
unreadable `git-workflow.yaml` (nested repos would go unchecked), and a remote that cannot be read.

| Path deleted | Check that protects it |
|---|---|
| Leaf worktree tracked files at `HEAD` | HEAD, local and remote-tracking leaf branch, and the leaf branch on the remote must all be merged into the remote's `ls-remote` integration tip |
| Leaf worktree modified or staged tracked files (including renames) | `-z` status → "uncommitted or untracked" refusal |
| Leaf worktree untracked, non-ignored files and directories | same refusal; a `.git` among them is also named as a foreign repository |
| Leaf worktree ignored files | listed one by one in the preview; deleted only with `--yes` (by design) |
| Directory holding a `.git` file or directory (another repo's linked worktree or checkout) at any depth in untracked or ignored paths, any name | `_foreign_dirs` on unquoted `-z` paths and their parents → foreign refusal naming repo, branch and commits its upstream lacks; `remove()` guard (R1) |
| Path that is not valid text | the status read fails → "cannot read git status" refusal |
| Leaf admin dir `.git/worktrees/<name>` (`HEAD`, index) | HEAD merged check; index changes caught by status |
| Configured nested linked worktree | its status, its stash (any whose subject does not name another branch), and its HEAD must be held by a branch or remote-tracking ref of the copy |
| Configured nested full clone | its status, any stash, and every branch and remote-tracking tip must be held by the copy's refs |
| Ignored files inside a configured nested repo | listed in the preview |
| Foreign `.git` directory inside a configured nested repo's changed or ignored paths | `_foreign_dirs(d, …)` → foreign refusal (R2) |

Paths not protected (outside A1's `.git`-entry definition; reported here, not fixed):
- Per-worktree refs (`refs/worktree/*`, `refs/bisect/*`) in the leaf's admin directory are not checked.
- A full nested clone's tags, reflog-only commits, hooks and config are not checked.
- A bare repository (no `.git` entry) inside an ignored directory is not detected as foreign. Its files
  appear only in the preview's list of ignored files.
- A tracked submodule that sits at its recorded commit does not appear in status, so it is not scanned.
  I checked locally that `git worktree remove --force` deletes a worktree with an initialized submodule,
  submodule gitdir included. Branches or stashes that exist only in that submodule would be lost.
  A submodule moved off its recorded commit shows as changed and is refused.

## Added

- `PrunePlan.foreign` — records the foreign `.git` directories so `remove()` can refuse without re-scanning.
- `_foreign_dirs()` — finds directories (and parents below the worktree) holding a `.git` among the paths removal deletes.
- `_foreign_refusal()` — builds the refusal text: directory, repository, branch, unlanded commits, next step.
- `_SHOWN` — caps listed commits at 20 so a checkout with no remote does not print its whole history.
- Guard in `remove()` — refuses when `plan.foreign` is non-empty, so a caller skipping the refusals deletes nothing.
- Test `test_a_linked_worktree_of_another_repository_refuses_and_survives` — A2: refusal, commit listed, preview and `--yes` exit 1, directory survives.
- Test `test_a_checkout_of_another_repository_refuses_with_commits_no_remote_holds` — the `.git`-directory and no-upstream path of A1.
- Round 1: `-z` record parsing in `_status()` (rename/copy source field) — R1: unquoted paths reach the filesystem check.
- Round 1: `plan.foreign += _foreign_dirs(d, …)` in `_check_nested()`, and the configured-dir exemption in `plan_prune()` — R2.
- Round 1: `_landed_leaf_ignoring_sibling()` builds the leaf from public helpers and takes optional nested repos — R3, and setup for the R2 test.
- Test `test_foreign_worktrees_whose_names_git_quotes_refuse_and_survive` — R1 regression through the CLI.
- Test `test_a_foreign_worktree_inside_a_configured_nested_clone_refuses_and_survives` — R2 regression through the CLI.
- Mocks: none.
