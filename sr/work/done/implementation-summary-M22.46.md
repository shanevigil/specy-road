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

## Fix round 1 (review `gpt-5.6-sol-high` at `fc481e53`): stopped, the fix is outside the touch zones

I merged `origin/WIP/improvements-0-3-1` (`c64ca716`; no conflicts). The merge did not change
`worker_sandbox.py` or `tests/test_worker_sandbox.py`.

The review record could not be read from this sandbox: `sr/work/reviews/M22.46/` looked empty here. I worked
from the findings quoted in the fix-round message.

Both blocking findings are one class: **operator docs that describe the sandbox's outbox and Cursor's state
entries, left stale by A1 and A3.** Their only instances are in `docs/orchestration-workers.md`:

- line 441: the Cursor row lists `sandbox-policies/` as read-only;
- line 457: the Hand-off bullet says the outbox is "empty at each turn's start".

`docs/orchestration-workers.md` is not a touch zone of this leaf. The fix round says to stop and name such a
path, so I made no doc edit. **Coordinator:** add `docs/orchestration-workers.md` to M22.46's touch zones, then
re-run the fix round. The two edits are:

- line 441: drop `sandbox-policies/` from the Cursor row's read-only list;
- line 457: say the outbox starts with a copy of the regular files already in `work/reviews/<ID>/` (links
  excluded), and that only `READY-*` is moved back, so edited copies are discarded.

## Probes

- `grep -rn "sandbox-policies\|outbox"` over `docs/`, `README.md`, `suggested_prompts/` and `specy_road/*.md`:
  the only stale mentions are `docs/orchestration-workers.md:441` and `:457`. The other outbox hits are the
  unrelated ops outbox (`worker_outbox.py`, design notes, line 44).
- Docstrings in `worker_sandbox.py` (module and `HARNESS_STATE`): already describe the seeded outbox and no
  longer list `sandbox-policies`. Current.
- CHANGELOG `[Unreleased]` / Fixed entry: matches A1 to A3. Current.
- Merged tree: `tests/test_worker_sandbox.py` with bwrap running (the `/var/tmp` redirect wrapper above):
  13 passed.
- `ruff check specy_road tests scripts`: all checks passed.
- `specy-road file-limits`: OK.

## Fix round 2 (review `gpt-5.6-sol-high` at `fc481e53`): fixed

`docs/orchestration-workers.md` is now in the zones. I merged `origin/WIP/improvements-0-3-1` first (no
conflicts; the integration side's generated and registry files were kept as merged). Doc commit: see the commit
that READY names.

- **Class:** operator docs that describe the sandbox outbox and the harness state entries, left stale by A1 and
  A3.
- Cursor row of the harness state table: dropped `sandbox-policies/` from the read-only list. The row now
  matches `HARNESS_STATE["cursor"]`.
- Hand-off bullet: the outbox now starts with a copy of the regular files already in `work/reviews/<ID>/`
  (REVIEW, notes and `history/`; links not copied). Only `READY-*` is moved back, and a new `REVIEW-` or an
  edited copy of a record is discarded. I removed the sentence "nothing needs to be read from there": it is no
  longer true.

### Probes (round 2)

- Every row of the harness state table against `HARNESS_STATE` (claude-code, cursor, codex): they match after
  the edit.
- `grep -rni outbox` over `docs/`, `README.md`, `suggested_prompts/`, `specy_road/templates/` and `CHANGELOG.md`,
  excluding the unrelated ops outbox: only the Hand-off bullet (fixed) and the two CHANGELOG entries. The M22.44
  entry only says READY-only delivery, which is still true.
- `grep "nothing needs to be read"` / `policies` over `docs/` and `specy_road/`: no other stale claim.
- Tests that read `docs/orchestration-workers.md` (`tests/test_worker_resume_permissions.py`): 57 passed.
- `tests/test_worker_sandbox.py` with bwrap running (the `/var/tmp` redirect wrapper): 13 passed. Under plain
  pytest: 5 passed, 8 skipped (`/var/tmp` is read-only in this session).
- `ruff check specy_road tests scripts`: all checks passed. `specy-road file-limits`: OK.

### Added (round 2)

- none (doc text only)
