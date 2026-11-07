# Implementation summary: M22.47 — Cursor workers start and keep their config under the sandbox

## What changed

- `specy_road/worker_sandbox.py` (`_harness_binds`): the loop over state directories records each replaced
  user directory and the worker's own directory that replaces it. A seed whose path lies inside a replaced
  directory is copied once (when the worker has no copy yet) into the matching path of the worker's own
  directory and **not** bound: the harness sees a plain file it can replace by rename. A seed outside every
  replaced directory (`~/.claude.json`) keeps today's behaviour: a per-worker copy at
  `work/.workers/<id>.state/seed_<rel>` bound writable over the user's path. Module and function docstrings
  updated.
  - Affected seeds: Cursor's `~/.cursor/cli-config.json` (A1), and Claude's `$CLAUDE_CONFIG_DIR/.claude.json`
    (also inside a replaced directory).
- `tests/test_worker_sandbox.py`: the fake harness's spec gains `renamed`; for each path it writes `<p>.tmp`
  and `os.replace`s it over the seed, as Cursor does. Set for `cursor` (`.cursor/cli-config.json`); the existing
  `_snapshot(guarded)` check (seeded paths are in `guarded`) proves the user's copy does not change, on launch
  and resume (A2).
- `docs/orchestration-workers.md` (Worker sandbox): where the per-worker copy lives and why.
- `CHANGELOG.md` `[Unreleased]` → `### Fixed`: Cursor workers start under the sandbox.

Final touch zones: as listed (`specy_road/worker_sandbox.py`, `tests/test_worker_sandbox.py`,
`docs/orchestration-workers.md`, `CHANGELOG.md`). `specy_road/worker_runner.py` (call site) needs no change:
`prepare`'s signature and `Box` are unchanged. No file-limits cap crossed.

## Verification

- `tests/test_worker_sandbox.py`: this session's `/var/tmp` is read-only (the session itself runs sandboxed),
  so the bwrap tests skip under plain pytest ("/var/tmp is not writable"). I ran them through an untracked
  verification wrapper (`sr/work/worker-logs/M22.47/run_vartmp.py`) that redirects only the fixture's
  `mkdtemp(dir="/var/tmp")` to a writable dir: **13 passed** with the fix. With `worker_sandbox.py` reverted to
  base: `test_a_sandboxed_launch_and_resume_...[cursor]` **fails** (the fake harness's rename exits 1), others pass.
- Full suite `pytest -n 4`: 6565 passed, 8 skipped (the bwrap cases, for the reason above).
- `specy-road file-limits`: OK.

### Recorded smoke check: real Cursor under the sandbox (2026-11-07)

Script `sr/work/worker-logs/M22.47/smoke_cursor.py` (untracked): a throwaway repo root with
`worker_sandbox: bwrap`, `worker_state.create_record(..., "cursor", ...)` on this linked worktree,
`worker_sandbox.prepare(...)`, then `box.command([...])` running
`agent -p "Reply with exactly the word ok and do nothing else." --output-format stream-json --trust --sandbox enabled --model auto --workspace <worktree>`.

- **With the fix:** `system/init` (apiKeySource login, model Auto), streamed thinking deltas, assistant `ok`,
  `result/success` (`is_error: false`, `result: "ok"`); **exit 0**, bwrap reported the harness started; the
  worker's own `.cursor/cli-config.json` exists. `sha256sum ~/.cursor/cli-config.json` identical before and
  after (`375f1d55…c343`). Log: `sr/work/worker-logs/M22.47/smoke-cursor.log`.
- **Base code (reverted for the run):** `Error: EBUSY: resource busy or locked, rename
  '~/.cursor/cli-config.json.<pid>.<uuid>.tmp' -> '~/.cursor/cli-config.json'`,
  exit 1 — the 2026-11-07 failure, reproduced.
- Cursor wrote nowhere else in home that the sandbox refused on this start (no "If this fails" path hit).
  Caveat: this session's home is read-only underneath, so auth.json's write-through could not be exercised; the
  start did not need it.

## Notes

- A worker that already ran under the old layout keeps an unused `seed_.cursor_cli-config.json`; its first
  turn after this change copies a fresh `cli-config.json` from the user's into its `.cursor`.

## Added

- `replaced` map in `_harness_binds`: user state dir → worker's dir, to place a seed inside a replaced dir.
- `inside` branch in the seed loop: copy into the worker's own directory and skip the bind (A1).
- `copy.parent.mkdir(...)` (was `own.mkdir`): the copy may now live in a subdirectory of the state home.
- Test: `renamed` spec key and fake-harness loop (write temp, `os.replace` over the seed) in the existing
  parametrized `test_a_sandboxed_launch_and_resume_...`; set for `cursor`, empty for the others (A2). No new test
  function.
- Mocks: none.
