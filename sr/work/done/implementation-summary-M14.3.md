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

## Fix round 3, first pass (Sol R1–R4; commit e34762f7)

The findings fall into three classes:

- **R1: a subtree that removal deletes but the walk skipped.** `_walk_foreign` dropped every `.git`
  directory from the walk. `shutil.rmtree` on a configured full clone deletes that clone's `.git`, so
  another repository's worktree inside it was missed. Fix: the walk no longer skips any directory. The
  exemption set now holds each configured repo and its own `<repo>/.git` (`exempt | {e / ".git"}`),
  so only those two paths are exempt from being reported. Everything inside them is walked.
- **R2: path data read through text-mode git.** Universal newlines turn `\r` into `\n`, and stripping
  drops edge whitespace. Fix: a new `_git_path()` runs git as bytes, removes only the single trailing
  `\n`, and decodes with `os.fsdecode`. All git-read paths in this module now go through it:
  `_common_dir` and `_is_repo_top` (now local, replacing the text-mode ones imported from `nested_repos`)
  and `--absolute-git-dir`. That covers `leaf_worktree`, `_check_nested` and `_foreign_refusal`.
- **R3: unquoted paths in a printed command.** Both arguments now go through `shlex.quote`. The printed
  command is the only shell text built from paths in the touch zones.
- **R4:** removed the unreachable `or 'unknown'`.

Tests in `tests/test_worktree_prune_foreign.py`:

- New `test_a_foreign_worktree_inside_a_configured_clones_git_directory_refuses_and_survives` (R1).
  `plan.foreign` is exactly the worktree at `lib/.git/foreign-worktree`, `remove(plan)` refuses, and
  preview and `--yes` both exit 1, name it, and leave it, the clone and the leaf in place.
- New `test_an_owning_repository_with_a_carriage_return_in_its_name_is_named_exactly` (R2). The owner is
  `other\rrepo`. The refusal names that exact path, its quoted form appears in the suggested command, and
  the CLI exits 1 both ways while every directory survives.
- `test_foreign_worktrees_whose_names_git_quotes_refuse_and_survive` is extended (R3). The owner is now
  `other repo`. `shlex.split` of the printed command yields exactly
  `git -C <owner> worktree remove <sibling space>`, and running it exits 0 and removes that worktree.
- `_other_repo()` takes an optional directory name.

Red/green: with `worktree_prune.py` at `955713b9`, those three tests fail and the other 7 pass. With the
fix, `pytest -n 4 tests/test_worktree_prune.py tests/test_worktree_prune_foreign.py` gives 42 passed.
The nested-repo suites (`test_nested_repo_worktrees.py`, `test_nested_unpushed_report.py`) also pass:
74 passed in total. `specy-road file-limits` is OK and `ruff` is clean.

## Probes

- R1 class, every subtree `remove()` deletes:
  - leaf root: walked.
  - configured linked worktree: its `.git` is a file and the directory is walked.
  - configured full clone: now walked, including `.git` (regression test).
  - leaf admin dir `.git/worktrees/<name>`: it lives outside the leaf root in the main checkout, and git
    removes only that admin dir. No user repository lives there.
- Configured full clone with an initialized submodule: `lib/.git/modules/sub` now refuses as a bare
  clone and `lib/sub` as a checkout. Both are deleted with the clone, so the refusal is correct (probe
  at `/tmp/m143probe`).
- `<clone>/.git/worktrees/<n>` and other admin directories inside an exempt `.git`: no `.git` entry and
  no `objects/` + `refs/` pair, so they do not refuse. The cases in the existing configured nested-repo
  tests still pass.
- R2 class, every git-read path in `worktree_prune.py`:
  - `--git-common-dir`, `--show-toplevel` and `--absolute-git-dir` now go through `_git_path` as bytes.
  - `_status` was already bytes.
  - The remaining `git_text` reads are SHAs, ref names and commit subjects, not paths. Ref names cannot
    hold control characters.
  - `os.walk` returns `str` paths with no newline translation.
- R2, owner with `\r`: the refusal names the real path (regression test).
- R3 class, shell text built from paths: the only such text is the `git -C … worktree remove …` step,
  now quoted. Other refusal text names paths as prose, not as commands. The CLI prints refusals and
  builds no commands of its own.
- R3, owner and worktree both containing spaces: the printed command splits to the exact two paths and
  runs with exit 0 (regression test).
- R4: no other `or 'unknown'` fallback on a value that is always truthy. `branch`'s `or "unknown"`
  stays, because `git_text` returns `None` when `rev-parse` fails.

## Fix round 3: invariants (commit ebe9b8c3, after merging origin/WIP/improvements-0-3-1)

The first pass fixed each finding where it was reported. This pass makes each fix hold for the whole
module by construction.

1. **The scan set equals the delete set.** `_deleted(plan)` returns the configured nested repos followed
   by the leaf worktree.
   - `remove()` deletes exactly that list, in that order. A linked worktree goes through
     `git worktree remove` against its owner (`plan.main` for the leaf); any other entry goes through
     `shutil.rmtree`.
   - `plan_prune()` passes the same list to `_walk_foreign(roots)`, which walks each root whole with
     `os.walk` and does not follow links. A root inside another root is walked with the outer one.
   - The only exemptions are each root itself and the root's own `.git` entry, never their contents. A
     full clone's `.git` directory is therefore walked.
   - Pinned by `test_every_foreign_repository_in_anything_removal_deletes_refuses_at_any_depth`. It
     places checkouts and linked worktrees at depths 1 to 3 in the leaf, inside the clone, and inside
     the clone's `.git` (`info/`, `refs/…/deep`, `.git/sibling-linked`). It asserts:
     - `plan.foreign` equals exactly that set;
     - `remove(plan)` refuses;
     - preview and `--yes` both exit 1, name every one, and every directory survives.
   - Also pinned by `test_a_foreign_worktree_inside_a_configured_clones_git_directory_refuses_and_survives`.
2. **Bytes in, bytes out.** Every git call in the module goes through `_git()`.
   - `_git()` runs `subprocess.run` as bytes. `-z` is used where git has it (`status`).
   - Output is decoded only with `os.fsdecode`, and `_out()` removes only the final newline.
   - Paths come from `_git_path()`.
   - `git_text`, `git_stdout`, `git_code` and `run` are no longer imported. A grep for them, for
     `splitlines` and for `text=` in the module finds nothing.
   - Pinned by `test_an_owning_repository_with_a_carriage_return_in_its_name_is_named_exactly`
     (owner `other\rrepo`) and `test_an_ignored_foreign_checkout_with_a_carriage_return_in_its_name_refuses_and_survives`.
3. **Commands are built, not formatted.** Every command shown is built with `shlex.join` from an
   argument list.
   - `_cmd(*argv)` covers: the foreign worktree's `git -C <repo> worktree remove <dir>`,
     `specy-road worker terminate <id>`, and `remove()`'s `git -C <owner> worktree remove --force <dir>`
     failure message.
   - `ls-remote` uses `shlex.join` without backticks. Its text is unchanged for a plain remote name, so
     the existing `test_worktree_prune.py` assertion still holds unmodified.
   - Pinned by `test_foreign_worktrees_whose_names_git_quotes_refuse_and_survive`. It uses owner
     `other repo` and destination `sibling space`, and checks that `shlex.split` of the printed command
     yields exactly those two paths and that running it exits 0.

Red/green: with `worktree_prune.py` at `955713b9`, 4 tests fail (the three above plus the
any-depth test) and 7 pass. With the fix:
`python -m pytest -q -n 4 tests/test_worktree_prune.py tests/test_worktree_prune_foreign.py
tests/test_nested_repo_worktrees.py tests/test_nested_unpushed_report.py` gives 75 passed.
`specy-road file-limits` is OK (`worktree_prune.py` is 375 lines) and `ruff` is clean. The full suite
was not run.

### Every place a path enters or leaves the module

| Place | Direction | Covered by |
|---|---|---|
| `_status()`: `git status --porcelain=v1 -z` | in (git) | 2: bytes, NUL-split, `os.fsdecode` |
| `_git_path()`: `--git-common-dir`, `--show-toplevel`, `--absolute-git-dir`, used by `_common_dir`, `_is_repo_top`, `leaf_worktree`, `_check_nested` and `_foreign_refusal` | in (git) | 2 |
| `_git()` messages (stderr from `worktree remove`, `ls-remote`, `fetch`) | in (git), shown | 2: `os.fsdecode`; stripped for display only |
| `_out()`: stash subjects, ref names, SHAs, `log --oneline` subjects | in (git); not paths | 2, which applies to every call anyway |
| `_walk_foreign()`: `os.walk` over `_deleted(plan)` | in (filesystem) | 1. `str` paths, so no newline translation |
| `os.walk` `onerror` → "cannot read {e.filename}" | out (text, not a command) | 1: the error refuses |
| `nested_repos(main)` paths → `leaf_root / nr.path` | in (config) | 1: they are roots of the walk and of `remove()` |
| `list_records(main)` worker worktree paths | in (JSON) | not git output; compared as `Path`s |
| Foreign refusal: `{shown}/ is a … of another repository, {repo}` | out (prose) | 2 (exact path); `shown` is absolute when outside the leaf |
| Foreign refusal next step `git -C … worktree remove …` | out (command) | 3 |
| Worker refusal `specy-road worker terminate <id>` | out (command) | 3 |
| `remove()` failure `git -C <owner> worktree remove --force <dir> failed` | out (command) | 3 |
| `remove()` failure `cannot remove {d}: {e}`, `PruneError` texts, `plan.ignored` list | out (prose / list) | not commands. `ignored` comes from `_status` (2) |
| `remove()` argv `["worktree", "remove", "--force", str(d)]` | out (to git) | passed as a list, never through a shell |

### Probes (round 3 invariants)

- Grep of `worktree_prune.py` for `git_text|git_stdout|git_code|run(|splitlines|text=`: only `_git`'s
  `subprocess.run` remains.
- Grep for backtick commands and `git -C`: every one goes through `_cmd`. `ls-remote` uses `shlex.join`.
- Any-depth tree (8 foreign repositories, including 3 inside the clone's `.git`): all 8 refuse and all
  survive (new test).
- A configured nested path that resolves outside the leaf: `_walk_foreign` walks it as its own root, and
  the refusal shows its absolute path. Not reachable in tests: no `..` paths are configured. `_status`'s
  existing skip computation (`relative_to(wt)`) is unchanged from before this leaf.
- A configured clone's submodule (`.git/modules/sub`) still refuses as before (probe `/tmp/m143probe`).
- The existing `test_worktree_prune.py` ls-remote assertion passes unmodified. No test was loosened.

## Fix round 4: complete delete set (commit 405c5bae, after merging origin/WIP/improvements-0-3-1)

**Class:** something removal deletes implicitly, without naming it, that the scan never walked. Round 3
derived the delete set from the paths `remove()` passes to git. But `git worktree remove` also deletes
the worktree's administrative directory, `<common dir>/worktrees/<name>/`, which lives outside the
worktree.

**Design change:**
- `deletions(nested, main, worktree)`, in the new module `specy_road/worktree_delete_set.py`, returns
  every step `remove()` takes. For each step it lists every directory that step deletes, each with the
  entries that count as that directory's own git files.
- `plan_prune()` walks exactly those directories (`walk_foreign(steps)`).
- `remove()` recomputes the same list and executes it step by step. If any directory cannot be
  determined, it refuses.
- Nothing else in the module decides what gets deleted.
- Branch and other refs in the owner's common directory are not files of any step and are not
  deleted; the per-leaf branch is left for `finish` and cleanup.
- The walk rule is the same as before: bytes paths, symlinks not followed, unreadable directories
  refuse. A directory is foreign when it holds a `.git` entry or a `HEAD` + `objects/` + `refs/` layout,
  unless it is a delete-set directory and those entries are all among its own git files.
  Nothing below a delete-set directory is ever exempt.

| Delete-set member | Derived from | Own git files (exempt in that directory itself only) | Test |
|---|---|---|---|
| Leaf worktree directory | `plan.worktree`; removed by `git -C <main> worktree remove --force` | `.git` (its link file) | `test_every_directory_of_every_kind_prune_deletes_is_scanned`, and all earlier foreign tests |
| Leaf administrative directory | `git rev-parse --absolute-git-dir` in the leaf, which reads its `.git` file. Accepted only when its parent is `<--git-common-dir>/worktrees`; otherwise a refusal | `_ADMIN_OWN`: `HEAD`, `ORIG_HEAD`, `FETCH_HEAD`, `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `AUTO_MERGE`, `BISECT_LOG`, `gitdir`, `commondir`, `index`, `locked`, `config.worktree`, `logs`, `refs`, `modules`, `rebase-merge`, `rebase-apply`, `sequencer` (no `.git`, no `objects`) | `test_a_foreign_worktree_in_the_leafs_administrative_directory_refuses_and_survives` (R1 regression), and the all-kinds test |
| Configured linked nested worktree | `plan.nested` with `linked`; removed by `git -C <main copy> worktree remove --force` | `.git` | all-kinds test |
| Its administrative directory | the same derivation, in that worktree | `_ADMIN_OWN` | all-kinds test |
| Configured full clone | `plan.nested`, not linked; removed by `shutil.rmtree` | `.git` | all-kinds test; `test_a_foreign_worktree_inside_a_configured_nested_clone_refuses_and_survives` |
| Its `.git` directory | `<clone>/.git` (inside the clone, so walked with it) | `HEAD`, `objects`, `refs` | all-kinds test; `test_a_foreign_worktree_inside_a_configured_clones_git_directory_refuses_and_survives` |

**Tests** in `tests/test_worktree_prune_foreign.py`:
- `test_every_directory_of_every_kind_prune_deletes_is_scanned` builds a leaf with a configured linked
  worktree (`src/engine`) and a configured full clone (`lib`). In each of the six delete-set
  directories it plants a checkout at depth 1, a checkout at depth 3 and another repository's linked
  worktree at depth 2: 18 plants in all. It asserts:
  - `plan.foreign` is exactly those 18;
  - direct `remove(plan)` refuses;
  - preview and `--yes` both exit 1 and name every plant;
  - every plant, both nested repos and the leaf survive.
- `test_a_foreign_worktree_in_the_leafs_administrative_directory_refuses_and_survives` (R1) plants a
  linked worktree of another repository, with one unpushed commit on `topic`, and a checkout under
  `logs/` in the leaf's admin directory. It asserts:
  - the directory, owner, branch and private commits of each are named;
  - preview and `--yes` both exit 1, and direct `remove(plan)` refuses;
  - every directory survives.

**Results:**
- Red/green: with `worktree_prune.py` at `60a4d9e8`, these two tests fail and the other 11 pass.
- With the fix, `python -m pytest -q -n 4 tests/test_worktree_prune.py tests/test_worktree_prune_foreign.py
  tests/test_nested_repo_worktrees.py tests/test_nested_unpushed_report.py` passes.
- `specy-road file-limits` is OK and `ruff` is clean.

**New file outside the listed touch zones:** `specy_road/worktree_delete_set.py`.
- It was needed because `worktree_prune.py` reached 420 lines, over the 400 cap.
- It holds the bytes git helpers (`git_run`, `git_out`, `git_path`, `common_dir`, `is_repo_top`),
  `cmd`, `Deletion`, `deletions`, `walk_foreign` and `foreign_refusal`. They were moved from
  `worktree_prune.py` and renamed public.
- Please add it to M14.3's touch zones.
- Round 3's invariants 2 (bytes) and 3 (`shlex.join`) now span both files.

### Probes (round 4)

- **Everything `git worktree remove` deletes:** the worktree directory and `<common>/worktrees/<name>`.
  Both are now in the delete set, for the leaf and for every configured linked worktree.
- **What `shutil.rmtree` deletes:** the clone directory, `.git` included. In the set.
- **Leaf admin directory, foreign linked worktree and checkout:** both refuse, and all survive
  (R1 regression).
- **The other five delete-set directories at depths 1 to 3:** all 18 plants refuse, and all survive
  (all-kinds test).
- **Submodule inside the leaf:** its repository lives at `<admin>/modules/vendor` and now refuses as a
  bare clone, besides `vendor/` itself. Both are deleted with the worktree, so this is correct (probe
  `/tmp/m143p4`).
- **Common directory** (`<main>/.git`, objects and branches): outside the delete set and not walked;
  `git worktree remove` does not delete it.
- **Admin directory not where git keeps one** (a `.git` file pointing elsewhere): a refusal in
  `plan_prune`, and `remove()` refuses too. Not exercised by a test, since `leaf_worktree` and
  `_check_nested` already require a linked worktree of the expected repository.
- **A `.git` planted directly in an admin directory:** `.git` is not in `_ADMIN_OWN`, so that admin
  directory itself refuses as foreign.
- **Per-worktree refs and reflogs** (`refs/bisect`, `refs/worktree`, `logs/`) in an admin directory:
  deleted with it, as before. They are not repositories, and the scan checks their contents only for
  repositories.
- **Callers of the moved helpers:** `worktree_prune.py` imports them from `worktree_delete_set.py`, and
  `worktree_cli.py` is unchanged. A grep of both modules for `git_text|git_stdout|git_code|run(` shows
  only `git_run`'s `subprocess.run`.

## Fix round 5: every unlanded commit listed (gpt-6.1-sol-low R1, after merging origin/WIP/improvements-0-3-1)

**Class:** an output cap that hides evidence A1 requires. `foreign_refusal()` ran `git log --max-count=21`
and showed only the first 20 commits, so on a branch with 22 commits its upstream lacked, the two oldest
were never shown. The fix removes the cap. The refusal now lists the full `@{u}..HEAD` (or
`HEAD --not --remotes`), and `_SHOWN` is gone.

**Test:** `test_a_linked_worktree_of_another_repository_refuses_and_survives` is extended. The sibling
now has 22 commits its upstream lacks (`private-01` … `private-21`, then "unpushed sibling work"). It
asserts that every one, the oldest included, appears in the preview and in the `--yes` output. All of
its previous assertions are unchanged.
- Red/green: with `worktree_delete_set.py` at `9485371a`, that test fails and the other 12 pass.
- With the fix, `python -m pytest -q -n 4 tests/test_worktree_prune.py tests/test_worktree_prune_foreign.py
  tests/test_nested_repo_worktrees.py tests/test_nested_unpushed_report.py` gives 77 passed.
- `specy-road file-limits` is OK and `ruff` is clean.

`gpt-6.1-sol`'s block is on `60a4d9e8` (R1, admin directories). Fix round 4 (`405c5bae`) addressed it,
and its regression and property tests are still in place and pass.

### Fix round: probes

- **Truncations in `worktree_prune.py`, `worktree_delete_set.py` and `worktree_cli.py`:** grepped for
  `[:`, `[-`, `more`, `max-count` and `head`. The only hits left are `sha[:12]`, in `_lost_tips` and in
  the merged target. They shorten a SHA but drop no entries; every lost tip is still listed.
- **Other lists a refusal or the preview prints:**
  - changed and untracked paths, both the leaf's and each nested repo's: all;
  - stash subjects: all;
  - lost tips: all;
  - foreign directories in `remove()`'s message: all;
  - unreadable directories: all;
  - the CLI's ignored-file list: all, one per line.
- **The no-upstream span (`HEAD --not --remotes`):** also uncapped now. A checkout with no remote lists
  its whole history, which is exactly what removal would lose.
- **Test imports:** no test in `tests/test_worktree_prune*.py` imports a `_`-prefixed name from another
  test module. The only cross-module imports are `FEATURE`, `make_pickup_project`, `run_specy_road`,
  `commit_file`, `git`, `COVERED`, `UNCOVERED` and `add_nested_repo`.

## Fix round 6: what HEAD is on, unborn and detached (gpt-6.1-sol-low R1, after merging origin/WIP/improvements-0-3-1)

**Class:** a HEAD state that `rev-parse --abbrev-ref HEAD` misreports. On an unborn branch, as in an
empty checkout or an orphan worktree, it fails, and the refusal fell back to "unknown". On a detached
HEAD it prints a bare `HEAD`, with no commit.

**Fix:** one new function, `head_state(d)` in `worktree_delete_set.py`, now names HEAD everywhere a
foreign refusal does.
- It reads the branch with `git symbolic-ref -q --short HEAD`, as bytes, decoded with `os.fsdecode`.
  This names a branch whether or not it has a commit. When there is no commit it adds "(no commits yet)".
- Otherwise it reports `HEAD (detached at <sha12>)`. The existing "on HEAD" text is kept as a prefix.
- If neither works, it reports "an unreadable HEAD".
- `foreign_refusal()` skips the upstream and `log` reads when HEAD has no commit, because they would
  fail and wrongly say the commits "cannot be listed". It reports "no commits … lacks" instead.

**Tests:**
- New `test_unborn_foreign_branches_are_named_and_survive` covers an empty checkout on
  `private-unborn` and another repository's `--orphan` linked worktree on `orphan-unborn`. Through the
  CLI, preview and `--yes` both exit 1 and name each branch with "(no commits yet)". "unknown" does
  not appear, and every directory survives.
- `test_a_checkout_of_another_repository_refuses_with_commits_no_remote_holds` gains an assertion for
  `on HEAD (detached at <sha12>)`. Its existing "on HEAD" assertion is unchanged.

**Results:**
- Red/green: with `worktree_delete_set.py` at `39f9d281`, both tests fail and the other 12 pass.
- With the fix, `python -m pytest -q -n 4 tests/test_worktree_prune.py tests/test_worktree_prune_foreign.py
  tests/test_nested_repo_worktrees.py tests/test_nested_unpushed_report.py` gives 78 passed.
- `specy-road file-limits` is OK and `ruff` is clean.

`gpt-6.1-sol`'s block is on `60a4d9e8` and was addressed by fix round 4 (`405c5bae`). Its tests still
pass.

### Fix round: probes

- **Foreign refusal branch, unborn checkout:** names `private-unborn (no commits yet)` (test).
- **Foreign refusal branch, unborn linked worktree** (`--orphan`): names `orphan-unborn (no commits yet)`
  (test).
- **Foreign refusal branch, detached:** `HEAD (detached at <sha12>)` (test).
- **Foreign refusal branch, empty bare repository:** `symbolic-ref` works in a bare repo, so it names
  its unborn default branch instead of "unknown".
- **Foreign refusal commits when unborn:** no `log` or `@{u}` call is made, so the result is
  "no commits … lacks" instead of "cannot be listed".
- **Foreign refusal repository when unborn or detached:** taken from `--git-common-dir` and
  `--absolute-git-dir`, which do not depend on HEAD, so it is unchanged.
- **Configured nested repo `_lost_tips`:** a detached HEAD is labelled `HEAD (<sha12>)`, with its
  commit. An unborn HEAD has no commit to lose and is skipped. A clone's branches are listed by
  `for-each-ref`, which includes no unborn branch.
- **Stash refusals:** they quote git's own subjects, which already name the branch or `(no branch)`.
- **Leaf merged check** (`the worktree's HEAD`, `worktree_prune.py:232`, which predates this leaf): an
  unborn leaf falls back to the literal `HEAD`. That check is not a foreign refusal and is outside
  A1/A2, so it is unchanged and only reported here.
- **Commits on a foreign checkout's other local branches:** not listed. A1 asks for the commits on the
  branch HEAD is on, and the whole checkout still refuses, so nothing is deleted.
- **Test imports:** no `_`-prefixed name is imported from another test module.

## Deletion-path audit (updated in fix rounds 2 and 3)

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
| Contents of a configured nested repo, its own `.git` directory included (the repo and that `.git` are exempt themselves) | filesystem walk | the same foreign refusal for any repository inside it |
| A directory the walk cannot read (permission denied) | `os.walk` `onerror` | "cannot read <dir>: …" refusal; `remove()` guard |
| Leaf worktree tracked files at `HEAD` | git refs | HEAD and the leaf branch (local, remote-tracking, and on the remote via `ls-remote`) must be merged into the remote's integration tip |
| Leaf modified, staged (including renames) or untracked non-ignored files | `git status -z`, read as bytes | "uncommitted or untracked" refusal |
| Leaf ignored files | `git status -z`, read as bytes | listed one by one in the preview; deleted only with `--yes` (by design) |
| Leaf admin dir `<common>/worktrees/<name>` (and each configured linked worktree's) | `deletions()` via `--absolute-git-dir` (round 4) | walked for foreign repositories like the rest; HEAD merged check; index changes caught by status |
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
- `_SHOWN` — caps listed commits at 20 (removed in fix round 5: A1 needs every commit).
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
- Round 3: `_git_path()`, local `_common_dir()` and `_is_repo_top()`. Paths that git prints are read as bytes (R2).
- Round 3: `<exempt>/.git` added to the walk's exemption set, and the `.git` skip removed. A configured clone's metadata is walked (R1).
- Round 3: `shlex.quote` on both paths in the suggested command (R3). Removed `or 'unknown'` (R4).
- Round 3: `_other_repo(name=…)` parameter, so the owner name can hold a space or `\r`.
- Test `test_a_foreign_worktree_inside_a_configured_clones_git_directory_refuses_and_survives`: R1.
- Test `test_an_owning_repository_with_a_carriage_return_in_its_name_is_named_exactly`: R2.
- Test `test_foreign_worktrees_whose_names_git_quotes_refuse_and_survive` extended to check that the printed command splits and runs: R3.
- Round 3 invariants: `_git()` and `_out()` are the module's only git entry points, bytes only (invariant 2). They replace `git_text`, `git_stdout`, `git_code` and `run`.
- Round 3 invariants: `_cmd()` builds every shown command with `shlex.join` (invariant 3).
- Round 3 invariants: `_deleted()` is the single list that `remove()` deletes and `_walk_foreign()` walks. `remove()` was rewritten to loop over it (invariant 1).
- Round 3 invariants: `_walk_foreign(roots)` walks every root, skips nested ones, and exempts only the roots and their own `.git` entries.
- Test `test_every_foreign_repository_in_anything_removal_deletes_refuses_at_any_depth`: pins invariant 1.
- Round 4: new module `specy_road/worktree_delete_set.py`, holding the helpers moved to keep `worktree_prune.py` under the cap.
- Round 4: `Deletion` and `deletions()`, the one complete delete set that both the scan and `remove()` read. It includes each linked worktree's administrative directory (R1).
- Round 4: `_ADMIN_OWN`, `_TOP_OWN` and `_GIT_DIR_OWN`, the explicit own-git-file exemptions, each applying to its directory itself only.
- Round 4: the refusal when a linked worktree's administrative directory is not under `<common dir>/worktrees`. It goes into `plan_prune`'s refusals and `remove()` refuses on it too.
- Round 4: `remove()` executes `deletions()` instead of its own list.
- Round 4 test helpers `_admin()` and `_shown()`.
- Test `test_a_foreign_worktree_in_the_leafs_administrative_directory_refuses_and_survives`: R1.
- Test `test_every_directory_of_every_kind_prune_deletes_is_scanned`: the property test across all six delete-set members.
- Round 5: removed `_SHOWN`, `--max-count` and the "(and more)" slice. The linked-worktree test now has 22 unlanded commits and asserts every one is listed.
- Round 6: `head_state()` names the branch HEAD is on, born or unborn (`symbolic-ref`), or the commit a detached HEAD is at.
- Round 6: `foreign_refusal()` makes no upstream or log reads for a HEAD with no commit.
- Test `test_unborn_foreign_branches_are_named_and_survive`, and the detached assertion in the no-remote checkout test.
- Mocks: none.
