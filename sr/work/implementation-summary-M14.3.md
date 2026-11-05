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

## Fix round 2 (Sol R1–R2, after merging origin/WIP/improvements-0-3-1)

Root cause: foreign repositories were discovered from `git status`, which lists only changed or ignored
paths (R1), and the output was decoded in text mode, which changes `\r` to `\n` (R2). Discovery no longer
uses git status:

- `_walk_foreign(wt, exempt)` replaces `_foreign_dirs`. It walks the leaf worktree with `os.walk`
  (`followlinks=False`, `str` paths, no newline translation) and finds every directory below the root
  that holds a `.git` entry (file, directory or link) or is laid out as a bare repository (`HEAD`
  file, `objects/` and `refs/`). Each configured nested repo directory is exempt itself but its contents
  are walked. The walk does not descend into a `.git` directory, or into a repository it found (that
  repository already refuses). Any directory `os.walk` cannot read (`onerror`) becomes a refusal in
  `PrunePlan.unscanned`. `remove()` refuses on that list as well as on `plan.foreign`.
- `_foreign_refusal()` classifies the directory as a linked worktree (git-dir ≠ common dir), a checkout
  (a `.git` directory, or a `.git` file naming its own git directory, as a submodule's does), or a bare
  clone, then names the repository, branch and unlanded commits as before.
- `_status()` (still used to list changed and ignored paths and to refuse uncommitted work) runs git
  directly as bytes (`text=False`), splits on NUL, and decodes each field with `os.fsdecode`.
  `git_subprocess.run` is text-mode and outside the touch zones, so it is not used here.
- New CLI regressions in `tests/test_worktree_prune_foreign.py`. Each asserts that preview and `--yes`
  both exit 1 and the repository survives:
  - a foreign checkout in a clean tracked `vendor/` directory;
  - an initialized submodule at its recorded commit, with a branch that exists only in the submodule;
  - an ignored checkout named `sibling\rname`;
  - a directory with mode 000 (this one asserts the "cannot read … Permission denied" refusal).
- Red/green: with `worktree_prune.py` at `b4ddb345`, the four new tests fail (4 failed, 4 passed); with
  the fix all pass. Targeted run: `python -m pytest -q tests/test_worktree_prune_foreign.py
  tests/test_worktree_prune.py` → 40 passed. `specy-road file-limits` OK; `ruff` clean. Full suite not
  run, as instructed.

## Deletion-path audit (updated in fix round 2)

`remove()` deletes, in order: each configured nested repo (`git -C <copy> worktree remove --force` for a
linked worktree, `shutil.rmtree` for a clone), then the leaf worktree (`git worktree remove --force`),
which also deletes its admin dir `.git/worktrees/<name>`. Every subtree it deletes lies under the leaf
worktree root, and the filesystem walk covers that whole root. Nothing is deleted while `plan.refusals`
is non-empty (CLI), and `remove()` refuses on its own when `plan.foreign` or `plan.unscanned` is
non-empty. Before any of this, the plan refuses on a running worker, an unreadable
`git-workflow.yaml`, or a remote that cannot be read.

| Path deleted | Discovery | Check that protects it |
|---|---|---|
| Any directory below the leaf root holding a `.git` file, directory or link (another repo's linked worktree, a checkout, an initialized submodule, a `--separate-git-dir` checkout), tracked or untracked, clean or not, ignored or not, any name | filesystem walk (`os.walk`, links not followed) | foreign refusal naming repository, branch and commits its upstream lacks; `remove()` guard |
| A directory laid out as a bare repository (`HEAD`, `objects/`, `refs/`) | filesystem walk | foreign refusal ("bare clone"); `remove()` guard |
| Contents of a configured nested repo (the repo itself is exempt) | filesystem walk | the same foreign refusal for any repository inside it |
| A directory the walk cannot read (permission denied) | `os.walk` `onerror` | "cannot read <dir>: …" refusal; `remove()` guard |
| Leaf worktree tracked files at `HEAD` | git refs | HEAD and the leaf branch (local, remote-tracking, and on the remote via `ls-remote`) must be merged into the remote's integration tip |
| Leaf modified, staged (including renames) or untracked non-ignored files | `git status -z`, read as bytes | "uncommitted or untracked" refusal |
| Leaf ignored files | `git status -z`, read as bytes | listed one by one in the preview; deleted only with `--yes` (by design) |
| Leaf admin dir `.git/worktrees/<name>` (`HEAD`, index) | git | HEAD merged check; index changes caught by status |
| Configured nested linked worktree | `nested_repos` config + `is_repo_top` | its status, its stash (any whose subject does not name another branch), and its HEAD must be held by a branch or remote-tracking ref of the copy |
| Configured nested full clone | `nested_repos` config + `is_repo_top` | its status, any stash, and every branch and remote-tracking tip must be held by the copy's refs |

Inputs probed by hand through the CLI (scratch repos built with the public test helpers; probe at
`/tmp/m14probe/`), each found safe:

- **Ignored symlink to a foreign repository** (`sibling-link -> ../foreign`): the walk does not follow
  it. Preview lists `sibling-link` and `--yes` exits 0 and removes the leaf; the target, its `.git` and
  its files all survive, because only the link is deleted. An untracked, non-ignored symlink refuses
  as "uncommitted or untracked".
- **`.git` as a symlink to another repo's git directory**: refuses (checkout, branch `private`, commit
  listed); exit 1 both ways; both survive.
- **`.git` file (`gitdir:` link)**: covered by the linked-worktree and submodule tests; refuses.
- **Bare repository directory** (`sibling.git`, an empty bare init): refuses as a bare clone; exit 1
  both ways; it survives. Its commit list reads "cannot be listed", since it has no commits.
- **Nested worktrees**: another repo's worktree inside a foreign checkout refuses on the outer checkout.
  The main repository's own linked worktree inside the leaf refuses as a linked worktree, with
  `git -C <main> worktree remove <dir>` as the next step. Exit 1 both ways; all survive.
- **Permission-denied subdirectory** (mode 000): refuses with "cannot read <dir>: Permission denied";
  exit 1 both ways (regression test). It is not skipped silently.

Still not checked (no `.git` entry and no repository shape): per-worktree refs (`refs/worktree/*`,
`refs/bisect/*`) in the leaf's admin directory, and a configured nested full clone's tags, reflog-only
commits, hooks and config.

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
- Round 2: `_walk_foreign()` (replaces `_foreign_dirs`) — R1/R2: discovery from the filesystem, not git status.
- Round 2: `PrunePlan.unscanned`, its refusal and its `remove()` guard — an unreadable directory refuses instead of being skipped.
- Round 2: bare-repository shape check in the walk, and "bare clone" / submodule-aware kind in `_foreign_refusal()` — the audit's bare-repo and submodule inputs.
- Round 2: `_status()` runs git as bytes and splits on NUL — R2: no newline translation of paths.
- Round 2 test helpers `_own_checkout`, `_refused_both_ways` — shared setup and assertions for the new CLI regressions.
- Test `test_a_foreign_checkout_in_a_clean_tracked_directory_refuses_and_survives` — R1, clean tracked dir.
- Test `test_an_initialized_submodule_refuses_and_survives` — R1, submodule at its recorded commit.
- Test `test_an_ignored_foreign_checkout_with_a_carriage_return_in_its_name_refuses_and_survives` — R2.
- Test `test_an_unreadable_directory_refuses_instead_of_being_skipped` — permission-denied refuses.
- Mocks: none.
