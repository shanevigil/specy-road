# Implementation summary: M22.5 `steering-file-guard`

The branch already held the git-steering part of M21.7, after R30, R31 and R32 removed the other classes, finish's refusal and the launch denies (M22.30, M22.31 and M22.32 restore them). This change makes that code meet M22.5's acceptance. It is one commit, 77430a38, on top of base 7cc1b7c0.

## What changed, per acceptance item

- **A1 (filesystem only):** `steering_paths.scope_for` no longer asks git at the turn's start. `git_config_text.git_reads` (`rev-parse --git-path hooks`, `config --list --show-origin`) is removed, and `Scope.git_known` with it. The snapshot reads:
  - the common `config`, `config.worktree` and their `include.path` / `includeIf.*.path` files, using the existing parser;
  - the hooks directories.
  The hooks directories are each `core.hooksPath` value **plus** `<common>/hooks` and `<worktree-gitdir>/hooks`. A1 says "hooksPath when set, else the defaults". I watch both on purpose: include conditions are not evaluated, so a `hooksPath` found only under an `includeIf` that does not hold would otherwise hide the directory git really uses. The existing `nonmatching_conditional_include` case covers this. The extra coverage only adds detection.
  Direct entries only: a regular file (a link followed) is stored as its sha256 and a subdirectory is skipped. The old `link:<text>@sha` and `dir`/`other` values are gone.
- **A2 (cap):** a hooks directory is listed with `os.scandir` and `islice(201)`. If it has more than 200 entries, the directory itself is recorded as unreadable, so every comparison gives one `check_error` (class `git_hook`) and the git probes are skipped. This replaces the `capped` marker.
- **A3 (fail closed):**
  - Every read opens the file with `O_NONBLOCK`, then `fstat` must show a regular file. A FIFO, socket or device is a `check_error` and never blocks, including one swapped in after a stat.
  - A 30 s snapshot budget (`SNAPSHOT_SECONDS`) is checked before each step and per 1 MiB chunk while hashing. A path read after the budget runs out is a `check_error` (`TimeoutError`).
  - With no snapshot from the turn's start, or a comparison that raises, the check records one `check_error` per class naming the worktree, plus `git_probes_skipped`. Before, that path had no path or class and no `git_probes_skipped`.
  - `git_probes_skipped` is now the shared constant `PROBES_SKIPPED`.
- **A4 (runner order):** `worker_runner._finish` now runs `close_turn` before `fresh_ready`. If `fresh_ready` raises (invalid UTF-8 in a READY), `ready` is false. On exit 0, the turn's `completion` event then reads `exit 0; READY file invalid: <error>`; `exit_event` is not called, because its summary would parse the READY again. A non-zero exit still goes through `exit_event`, which does not read READY.
- **A5 (sticky flag):** this already worked and is unchanged. `steering_changed` is in the record's `flags`, which `worker status --json` and `handoff status --json` print, and the schema's flag enum already lists it. `worker reconcile` prints one `path class before after` line per finding and clears the flag.
- **A6:** all cases are in `tests/test_steering_file_guard.py` (see Added).
- **A7:** none of M22.30, M22.31 or M22.32's code is on this branch. The docs name them as out of scope.

## Touch zones

The final list is the brief's list, unchanged. `specy_road/schemas/worker-record.schema.json` needed no change: it already lists `steering_changed` and describes it. No call site outside the zones changed.

## Verification

- `pytest -q tests/test_steering_file_guard.py`: 18 passed.
- `pytest -q -n 4`: 5980 passed.
- `specy-road file-limits`: OK.
- `ruff check` on the changed Python files: clean.
- Red/green: with the four product files at base 7cc1b7c0, both new tests fail (`over_the_cap`, `unparsable_ready`). With this change, both pass.

## Notes for reviewers

- I dropped a `fifo` row for `git_config` (a FIFO as an included config). With that FIFO in place before the turn, git's own `git status` at the turn's start blocks on it (300 s), before any of this code runs. The snapshot side of a FIFO is covered by the `fifo` hook row.
- The turn-start `git_state` (`git status` and others in `TurnWatch.__init__`) still runs before the next turn. If the previous turn changed `core.fsmonitor`, it runs under it. That turn was already flagged `steering_changed`, and refusing the next turn is outside this leaf (M22.31 refuses at finish).

## Added

- `steering_paths._open_regular`: opens without blocking and refuses anything that is not a regular file once open (FIFO or special file, or a swap after stat; A3).
- `steering_paths._in_time`, `SNAPSHOT_SECONDS`, `_until`: the snapshot time budget, so a timeout is a `check_error` (A3).
- `steering_paths._hook_value`, `_add_hook`: a hook's value is the sha256 of the regular file it resolves to, and a subdirectory is skipped (A1, A3). They replace `_value` and `_add`.
- `steering_paths._hooks_dir` cap branch: more than 200 entries raises, so the directory is a `check_error` on every comparison; the listing stops at 201 (A2).
- `worker_turn_check.PROBES_SKIPPED`: one `git_probes_skipped` finding, also recorded when there is no snapshot (A3).
- `worker_turn_check._turn_findings` no-snapshot branch: one `check_error` per class naming the worktree (A3).
- `worker_runner._finish` try/except around `fresh_ready`: an unparsable READY is the turn's completion error, and the check runs before it (A4).
- Test row `fifo` for a hook in `UNREADABLE_ROWS`: a special file fails closed without blocking (A3).
- Test `test_a_hooks_directory_over_the_cap_fails_closed_even_when_a_replaced_hook_keeps_it_over` (A2, A6).
- Test `test_an_unparsable_ready_through_the_worker_runner_still_ends_with_one_check_holding_the_config_change`: a fake `claude` on PATH writes a READY with byte FF and runs `git config` (A4, A6).
- Changed tests (expectations only, to match the acceptance's value format): `unchanged_symlink_written_through` now compares sha256 values, not `link:` values. The `unavailable` snapshot case now expects one `check_error` per class plus `git_probes_skipped`.
- Mocks: none added.
