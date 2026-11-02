# Implementation summary: M10.16 — the worker wrapper imports the launching specy-road

Branch `feature/rm-wrapper-imports-launcher`, base `579b262`.

## What changed

- `specy_road/worker_runner.py` — `spawn` now starts the wrapper as
  `sys.executable -P -m specy_road.worker_runner …` (A1). `-P` (safe path,
  Python 3.11+) stops Python from putting the cwd, which is the leaf's
  worktree, first on `sys.path`. So the wrapper imports the package from the
  `PYTHONPATH` entry `spawn` already sets, the one the launching CLI came from.
  `worker delegate`, `message` and `resume` all reach the wrapper through
  `spawn` (`worker_ops.py:250` and `:293`), so all three are covered. The flag
  goes on the argv only: `PYTHONSAFEPATH` is not set in the environment, and
  `-P` is not inherited, so the harness and the executor's own test runs keep
  importing the worktree's code. The comment above the PYTHONPATH block now
  says why. The file is 235 lines, under the 400-line cap.
- `tests/test_worker_runner_safe_path.py` (new) — the regression test for A2
  and A3, described below. It builds its repository with the public
  `tests.review_repo_helpers.make_review_repo`, not the private `_repo` from
  `tests/test_worker_cli.py` (review E1, gpt-6.1-sol). The test supplies its
  own `Launch`, so it never used `_repo`'s fake harness or roster.
- `tests/test_review_round6_runner.py` — the existing test
  `test_a_huge_stdin_prompt_travels_in_a_0600_file_not_argv` pinned the
  wrapper argv by position (`argv[3:6]`). `-P` moves those three items one
  place to the right, so the slice is now `argv[4:7]`. It compares the same
  three values with the same equality, so the test is no weaker.

## Verification

- With `-P` removed, the new test fails ("worker did not finish": the wrapper
  imports the broken worktree runner and dies without recording an exit).
  With `-P` in place, it passes.
- `python -m pytest tests/test_worker_*.py tests/test_review_round6_runner.py tests/test_review_round4_sol.py tests/test_prerelease_workers.py`:
  137 passed, 1 failed. The failure was the positional slice above; after the
  fix, `tests/test_review_round6_runner.py` together with the new test gave
  12 passed.
- The rest of the suite, run in two chunks because xdist is not installed:
  942 passed, then 1568 passed and 2 skipped.
- `specy-road file-limits`: OK.
- `ruff check` on the touched files: clean.
- After the E1 fix: `python -m pytest tests/test_worker_runner_safe_path.py`
  gave 1 passed, and 1 failed with `-P` removed again.
  `python scripts/check_test_private_imports.py` exited 0 with 0 new
  references. It also reports a stale baseline entry for
  `tests/test_review_round6_evidence.py`, which this leaf did not touch, so it
  is left as is.

## Touch zones

Confirmed as `specy_road/worker_runner.py` and `tests/`. `worker_process._is_wrapper`
recognises the wrapper by whole-argument membership, not by position, so the
extra `-P` does not affect pid checks and needed no change.

## Added

- `-P` on the wrapper argv in `spawn`: keeps the worktree's `specy_road` off the wrapper's `sys.path` (A1).
- `tests/test_worker_runner_safe_path.py::test_a_broken_runner_in_the_worktree_is_not_imported`: puts a `specy_road/worker_runner.py` that raises on import in the worktree, spawns through `wr.spawn`, and asserts the wrapper still ran, wrote its log and recorded `completion` with exit 0 (A2). It also asserts the harness saw no `PYTHONSAFEPATH` and `sys.flags.safe_path` was false (A3).
- `monkeypatch.delenv("PYTHONSAFEPATH")` in that test: so a developer's own environment cannot make the A3 assertion pass or fail by accident.
- Helpers, branches/guards, mocks: none. The test's only fixture helpers are the public `make_review_repo` and `wait_for_worker`.
