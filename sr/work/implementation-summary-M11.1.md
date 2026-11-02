# Implementation summary: M11.1 (`worktree-paths-agree`)

## Summary

Every command already resolved the hand-off directory through one function,
`review_files.reviews_root` (by way of `reviews_dir`): `review-packet`, `review
record`, `handoff status`, the gate, `mark-implementation-reviewed` and `worker
delegate` (`worker_adapters._reviews_handoff_dir`, `worker_process.ready_fingerprints`).
That resolver ran three `git rev-parse` calls and, when any failed, **fell back
silently to the worktree's own `work/reviews/`**. A process git cannot serve
(a sandbox, a `safe.directory` ownership refusal, a missing git on `PATH`)
therefore read and wrote the worktree's copy while the coordinator's commands
used the main checkout's. That is the split the field report describes.

`reviews_root` now finds the git top the way git does (nearest ancestor with
`.git`) and, through `_main_checkout`, reads a linked worktree's `.git` file
(`gitdir: …`) and that directory's `commondir`, without running git. When
`commondir` cannot be read, it uses git's `<common>/worktrees/<name>` layout,
which comes from the worktree's own `.git` file, so a process sandboxed to the
worktree still resolves the main checkout. Behaviour is unchanged in every
other case: the main worktree, a plain repo, a nested project (`sr/`), a fixture
inside another checkout, a bare-repo or submodule worktree (common dir not
named `.git`) and a separate `--separate-git-dir` repo keep `repo_root/work/reviews`.

The reviewer prompt's precondition (`role_prompt_rca.reviewer_precondition`)
now names that directory, absolute, as the reviewer's one **writable root**.
It says a harness sandboxed to the worktree must be launched with it as a
writable root (Claude Code `--add-dir`), and tells the reviewer to write its
notes there as `notes-<roster id>.md`, since a `review-…` name matches the
case-insensitive `REVIEW-` record prefix. `docs/orchestration-review.md` has
a new section, "The hand-off directory in a worktree", saying all of this.
`handoff status` with nothing to report now prints the resolved directory
instead of the literal `work/reviews/`.

## Changes

- `specy_road/review_files.py`: `_main_checkout` added; `reviews_root` rewritten
  to use it (no git subprocess). `ready_path` removed: it had no caller anywhere
  in the repository, and the file was already at the 400-line `file-limits` cap.
- `specy_road/bundled_scripts/role_prompt_rca.py`: writable-root paragraph in
  the reviewer precondition (A2).
- `specy_road/bundled_scripts/review_cli.py`: the empty-sweep message names the
  resolved directory.
- `docs/orchestration-review.md`: new section (A1, A2).
- `tests/test_worktree_paths_agree.py`: new (A3).

Final touch zones used: `specy_road/review_files.py`,
`specy_road/bundled_scripts/review_cli.py`,
`specy_road/bundled_scripts/role_prompt_rca.py`, `docs/orchestration-review.md`,
`tests/`. `review_packet.py` and `review_gate_ready.py` needed no change: both
already go through `reviews_dir`/`review_path`. Not touched, outside the zones:
`worker_adapters.linked_worktree` still asks git whether a worktree is linked.
It decides only whether to pass `--add-dir`, and the directory it passes comes
from `reviews_dir`, so the two agree whenever git runs.

## Verification

- `python -m pytest -q tests/test_worktree_paths_agree.py`: 3 passed.
  With the base `review_files.py` restored, `test_the_directory_resolves_when_git_cannot_run` fails (red at base).
- Full suite in five shards (`python -m pytest -q <files>`): 2958 passed, 2 skipped, 0 failed.
- `specy-road file-limits`: exit 0 (`review_files.py` is 399 lines).

## Added

### Helpers
- `review_files._main_checkout`: reads the main checkout from a linked worktree's `.git`/`commondir` so resolution never depends on git running (A1).

### Branches or guards
- `except OSError` on reading `.git`: an unreadable `.git` file means "not redirected", as a git failure did before.
- `except OSError` on reading `commondir`: falls back to git's `worktrees/<name>` layout so a sandbox that hides the main `.git` still resolves; otherwise not a worktree (a submodule).
- `common.name == ".git"` check: keeps the existing rule that bare-repo and submodule worktrees are not redirected.

### Mocks
- `monkeypatch.setenv("PATH", …)` in `test_the_directory_resolves_when_git_cannot_run`: simulates a process git cannot serve.
- `monkeypatch.chdir(wt)` in the agreement test: runs the commands from inside the worktree.

### Tests
- `test_packet_record_and_status_agree_from_a_linked_worktree`: review-packet, review record and handoff status run from a linked worktree all use the main checkout's directory, and none creates the worktree's own (A3).
- `test_the_directory_resolves_when_git_cannot_run`: the resolver gives the main checkout's directory with no git on `PATH` (A1, the field failure).
- `test_the_reviewer_prompt_names_the_writable_root`: the reviewer prompt built from a worktree names the main checkout's directory as the writable root (A2).
