# Implementation summary — M9.2

## Summary

Pytest guards `tests/fixtures` via `tests/fixture_guard.py`, wired from `tests/conftest.py` at session start and finish. **A1:** ignored paths (`!!` lines from `git status --porcelain --ignored -- tests/fixtures`) abort collection with `pytest.exit`, listing each path and `git clean -fdX tests/fixtures`. **A2:** if that status snapshot changes during the run, `session.exitstatus` is forced to 1 and stderr lists each path whose porcelain line was added or changed. **A3:** clean, stable trees produce no guard output. **A4:** `tests/test_fixture_guard.py` exercises A1–A3 in a temporary git repo (`.specyrd/cache` under `tests/fixtures/sample/` for A1).

Implementation code landed in `320a9267` (composer-2.5, first executor). This round (claude-fable-5-1) answers the gpt-6.1-sol block on `5bb17c1b` in commit `ac301cc`:

- **R1 (correctness):** `path_from_porcelain` split every path containing `" -> "` as a rename, so an ordinary untracked filename such as `"tests/fixtures/a -> b.txt"` was reported as `b.txt"`. It now splits only when the two-column status code holds `R` or `C`; paths are reported exactly as git prints them (quoted when git quotes them).
- **R2 (test integrity):** the A1 and A2 subprocess tests asserted only header text. The mini repo now tracks `tests/fixtures/sample/tracked.txt` (the dogfood shape, so git names `tests/fixtures/sample/.specyrd/` rather than collapsing to `tests/fixtures/`), the A1 test asserts that exact reported path, and the A2 test also creates `tests/fixtures/a -> b.txt` and asserts both reported paths verbatim. Red–green: against the old parser the A2 test fails on the arrow path (`b.txt"`); with the fix all three pass.

## Touch zones (confirmed)

`tests/conftest.py`, `tests/fixture_guard.py`, `tests/test_fixture_guard.py`, `docs/contributor-guide.md` — accurate; no additions or removals. This round changed only the middle two.

## Verification

```bash
pytest tests/test_fixture_guard.py -q -p no:cacheprovider
pytest -q -p no:cacheprovider
```

Results: `3 passed in 0.98s` (fixture guard); `2525 passed, 2 skipped in 858.63s` (full suite on a clean fixture tree). `-p no:cacheprovider` keeps pytest's own cache out of the worktree; it does not alter the guard.

## Added

Helpers:
- `fixtures_git_lines` — runs porcelain+ignored status for `tests/fixtures` (A1/A2 input).
- `path_from_porcelain` — extracts the path from a status line; splits on `" -> "` only for `R`/`C` records (R1).
- `ignored_fixture_paths` — filters `!!` lines for A1 abort messaging.
- `_line_map` / `paths_with_changed_status` — diff start vs end status by path for A2 output.
- `record_session_start` / `session_start_lines` — store start snapshot on `session.config`.
- `exit_if_ignored_fixtures_present` — A1 `pytest.exit` before tests run.
- `fail_if_fixtures_status_changed` — A2 stderr message and `exitstatus=1`.
- `pytest_sessionstart` / `pytest_sessionfinish` hooks in `tests/conftest.py` — wire guard to `REPO`.
- `_git` / `_mini_repo` / `_run_pytest` in the test module — subprocess pytest harness on a temporary git repo, never touching the real fixtures.

Branches or guards:
- `"R" in code or "C" in code` in `path_from_porcelain` — the only condition under which `" -> "` is a rename separator (R1).

Mocks:
- none

Tests:
- `test_refuses_start_when_ignored_cache_sits_in_fixtures` — proves A1 (A4 cache path); asserts `tests/fixtures/sample/.specyrd/` is the reported path (R2).
- `test_fails_session_when_a_run_pollutes_the_fixture_tree` — proves A2; asserts both `"tests/fixtures/a -> b.txt"` and `tests/fixtures/sample/.specyrd/` are reported verbatim (R1, R2).
- `test_clean_fixture_tree_leaves_exit_status_and_output_unchanged` — proves A3.

Docs:
- Contributor-guide paragraph — documents guard behaviour for maintainers (unchanged this round).
