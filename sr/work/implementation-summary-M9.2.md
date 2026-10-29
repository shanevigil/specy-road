# Implementation summary — M9.2

## Summary

Pytest now guards `tests/fixtures` via `tests/fixture_guard.py`, wired from `tests/conftest.py` at session start and finish. **A1:** ignored paths (`!!` lines from `git status --porcelain --ignored -- tests/fixtures`) abort collection with `pytest.exit`, listing each path and `git clean -fdX tests/fixtures`. **A2:** if that status snapshot changes during the run, `session.exitstatus` is forced to 1 and stderr lists paths whose porcelain line was added or changed. **A3:** clean, stable trees produce no guard output. **A4:** `tests/test_fixture_guard.py` exercises A1–A3 in a temporary git repo (`.specyrd/cache` under `tests/fixtures/sample/` for A1).

Implementation code landed in commit `320a9267f9a5929341f2aabddb00ff0ec082ab22` (checkpoint before this summary).

## Touch zones (confirmed)

`tests/conftest.py`, `tests/fixture_guard.py`, `tests/test_fixture_guard.py`, `docs/contributor-guide.md` — accurate; no additions or removals.

## Verification

```bash
pytest tests/test_fixture_guard.py -q
pytest -q
```

Results: `3 passed in 1.10s` (fixture guard); `2525 passed, 2 skipped in 1021.23s` (full suite on clean fixture tree).

## Added

- `fixtures_git_lines` — runs porcelain+ignored status for `tests/fixtures` (A1/A2 input).
- `path_from_porcelain` — extracts path from a status line (ignored and tracked forms).
- `ignored_fixture_paths` — filters `!!` lines for A1 abort messaging.
- `_line_map` / `paths_with_changed_status` — diff start vs end status by path for A2 output.
- `record_session_start` / `session_start_lines` — store start snapshot on `session.config`.
- `exit_if_ignored_fixtures_present` — A1 `pytest.exit` before tests run.
- `fail_if_fixtures_status_changed` — A2 stderr message and `exitstatus=1`.
- `pytest_sessionstart` / `pytest_sessionfinish` hooks in `tests/conftest.py` — wire guard to `REPO`.
- Contributor-guide paragraph — documents guard behaviour for maintainers.
- `_mini_repo` / `_run_pytest` — subprocess pytest harness without touching real fixtures.
- `test_refuses_start_when_ignored_cache_sits_in_fixtures` — proves A1 (A4 cache path).
- `test_fails_session_when_a_run_pollutes_the_fixture_tree` — proves A2.
- `test_clean_fixture_tree_leaves_exit_status_and_output_unchanged` — proves A3.
