# Implementation summary: M22.46 — Sandboxed workers can read their leaf's review records

Base `cdcd4d7f`. The previous worker (`w-0183`) left no commits; this is the first implementation. Code commit:
`2d657acb`.

## Changes

- `specy_road/worker_sandbox.py`
  - `prepare` now calls a new `_seed_outbox(reviews, outbox)` after making the empty outbox. It copies every
    regular file under `work/reviews/<node>` into the outbox and keeps the layout, so `history/` is included
    (`os.walk`, `shutil.copy2`). Symlinked files and directories are not followed or copied (A1).
  - `_deliver_ready` is unchanged: it still moves only top-level regular `READY-*` files back and discards the
    rest of the outbox. An edited copy of a REVIEW or notes file therefore never reaches the reviews directory
    (A2). An existing READY seeded and left untouched moves back with the same bytes and mtime (`copy2`).
  - `HARNESS_STATE["cursor"]` no longer lists `sandbox-policies` as a read-only entry. It is now part of the
    worker's own `~/.cursor` state, so Cursor can write its policy file on start (A3).
  - The module docstring explains that the outbox is seeded.
- `tests/test_worker_sandbox.py`: I extended the existing parametrized end-to-end test (through `worker_runner.run`)
  instead of adding new tests (A4):
  - Before the first turn, the reviews directory gets `REVIEW-gpt.md`, `notes-coordinator.md`,
    `history/0001-REVIEW-gpt.md` and a symlink `linked.md`.
  - The fake harness reads each record, reports its contents, and appends to it. The test asserts that the
    contents it read match, that the real records are unchanged after each turn, and that the link does not
    appear inside the sandbox.
  - In the `cursor` case the user now has `~/.cursor/sandbox-policies/policy.json`. The fake harness writes it
    (this must succeed), and the user's copy stays unchanged.
- `CHANGELOG.md`: a `[Unreleased]` / Fixed entry.

## Verification

- `ruff check` on both Python files: clean. `specy-road file-limits`: OK.
- `pytest -q -n 4` (full suite): 6540 passed, 8 skipped. The 8 skips are the bwrap cases in
  `tests/test_worker_sandbox.py`, skipped because `/var/tmp` is read-only in this session's own sandbox.
- I ran the bwrap cases for real with the fixture's `/var/tmp` redirected to a writable, git-ignored directory.
  The wrapper (`/tmp/run_sandbox_tests.py`) patches `tempfile.mkdtemp(dir="/var/tmp")` and nothing else:
  13 passed.
- Red-green with that wrapper:
  - Base `worker_sandbox.py`: 3 failed (every harness; the fake harness cannot read the seeded REVIEW).
  - Base `sandbox-policies` entry only: 1 failed (`cursor`; write refused, EROFS).

## Touch zones

The zones are confirmed: `specy_road/worker_sandbox.py`, `tests/test_worker_sandbox.py`, `CHANGELOG.md`.
`worker_runner.py` (the caller) needs no change.

**Follow-up outside the zones:** `docs/orchestration-workers.md` is now stale. Line 441 lists `sandbox-policies/`
as read-only for Cursor, and line 457 says the outbox is "empty at each turn's start". Neither is required by an
acceptance item, so I left them unchanged. The doc needs a zone to be corrected.

## Added

### Helpers
- `worker_sandbox._seed_outbox`: copies the reviews directory's regular files into the outbox (A1).

### Branches / guards
- In `_seed_outbox`, symlinked directories are pruned and only regular non-symlink files are copied: links are
  not copied (A1).

### Mocks
- none

### Tests
- No new test functions. The existing `test_a_sandboxed_launch_and_resume_commit_hand_off_ready_and_reach_nothing_else`
  gains the seeded records and the read-and-edit probe (A1, A2), and the Cursor `sandbox-policies` file case (A3).
- `RECORDS` (test module constant): the records seeded into the reviews directory and expected back unchanged.
