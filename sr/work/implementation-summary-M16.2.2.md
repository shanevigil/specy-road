# Implementation summary: M16.2.2

Shared clock and atomic-write helpers replace the nine now() copies and the hand-written atomic writers.

## What changed

- **`specy_road/clock.py`** (new): `utc_now()` gives an aware UTC datetime with microseconds. `utc_now_iso()` gives UTC to the second with a `+00:00` offset.
- **The nine now helpers are gone.** Each site calls the clock directly and keeps its form from pickup:
  - `worker_state._now`, `worker_outbox._now`, `worker_witness._now`, `reviewer_run_failure._now`, `worker_lease._now` and `decisions._now_iso` now call `utc_now_iso()`.
  - `session_presence._now` is now `utc_now().replace(microsecond=0)`, still a datetime to the second.
  - `worker_turn_check._utcnow` is now `utc_now`, still a datetime with microseconds; it is `TurnWatch`'s default `now`.
  - `grind_session_events._now_iso` is now `utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")` inside `EventEmitter.emit`.
- **A tenth copy is gone too:** `archive_plan.utc_now_iso`. Its callers (`archive_ops`, `milestone_chunk_io`, `tests/test_archive_ops.py`) import it from `clock`.
- **Inline `datetime.now(timezone.utc)` calls go through the clock**, each with the same expression around it, in:
  - claude_code_limits, orphaned_claims, review_rejected, review_files, review_record_write
  - worker_ops_slots, orchestrate_assign, worker_adapter_parsers, review_policy_pin
  - brainstorm_cli, brainstorm_cli_v2, grind_session_implement, mark_implementation_reviewed
- **`specy_road/fs_atomic.py`** (new): `atomic_write_text(path, text, *, tmp=None)`. It writes UTF-8 through `Path.write_text`, using the default temp name `.<name>.<pid>.tmp` (the same as before), then calls `os.replace`. The temp file is created with the umask mode, and a failed write leaves it in place, exactly as the replaced writers did.
- **Writers now on `atomic_write_text`:**
  - `worker_state` (its private `_write_atomic` is removed), and every module that imported that private helper: `worker_outbox`, `session_presence`, `worker_reconcile`, `chore_cli`, `chore_garden`.
  - `brainstorm_session.write_session`.
  - `roadmap_chunk_atomic.AtomicWritePlan.write`. It passes its own `tmp=` name and records it in `tmp_paths` first, so the transaction rollback works as before: earlier files are restored and no temp file is left. Checked by the two-chunk test below.
- **Modules that imported the removed private `_now`** now import `clock`: worker_runner, worker_reconcile, review_delegate, review_record_write, role_prompt_cli, chore_cli.

## Deviations from the acceptance text, for the reviewers and maintainer

1. **`history_cache.save_cache` stays on `safe_write.write`.** A6 says it calls `atomic_write_text` "with no repo-root check". Since planning, M21.39 moved it onto `safe_write`, and `tests/test_ops_writers_refuse_links.py::test_digest_carries_on_past_a_refused_history_cache[history-to-outside-file]` requires a symlink at the cache file to be refused with a warning. `safe_write` also keeps an existing file's mode. Moving the cache writer would break that test and change its mode behaviour, so it stays. The file has no `os.replace(`.
2. **The `os.replace(` allowlist has three more entries than A6 lists.** All three were added or changed after the M16.2.2 sheet was written (M15.40/M22.20 and M22.49). They install bytes, modes or symlinks; none writes text:
   - `finish_bookkeeping_undo._restore`: restores a file's bytes and mode, or a symlink, and names the kept temp file on failure.
   - `finish_bookkeeping_undo.restore_pre_commit`: restores git's index bytes.
   - `worker_sandbox._install_seed`: copies bytes with mode 0600 over a read-only placeholder.

   A text helper cannot serve them without a bytes, mode and symlink variant that the leaf did not ask for. If the maintainer wants them routed instead, that is a follow-up.
3. **`reviewer_run_failure.save_run` and `worker_lease.checkout_id` keep their specialised installers** (`review_write_check.replace_file` and `checkout_id`'s link-if-absent install), as A3/A6 say. Only their clocks moved. Their existing public-caller tests cover them:
   - `tests/test_review_writers_refuse_links.py`, which reaches `save_run`.
   - The `test_worker_max_workers_global.py` checkout-id tests: missing, empty or unusable, cannot be written, and concurrent first calls.
4. **Edits in `specy_road/` beyond the named files.** The planning sheet allows the zone only for inline clock calls. The edits beyond those are the import lines in the modules that imported the removed private helpers (`_now`, `_write_atomic`, `archive_plan.utc_now_iso`), listed above. They change no behaviour.

## Final touch zones

The listed zones, plus these files inside `specy_road/` and `tests/`:

- Imports and inline clock calls: archive_ops, archive_plan, milestone_chunk_io, claude_code_limits, orphaned_claims, orchestrate_assign, review_delegate, review_files, review_policy_pin, review_record_write, review_rejected, worker_adapter_parsers, worker_ops_slots, worker_reconcile, worker_runner.
- In `bundled_scripts/`: brainstorm_cli, brainstorm_cli_v2, chore_cli, chore_garden, grind_session_implement, mark_implementation_reviewed, role_prompt_cli.
- Tests: tests/test_archive_ops.py, tests/test_grind_session.py, tests/test_grind_session_cleanup.py, tests/test_grind_session_in_flight.py.

## Gates

- `pytest -n 4`: 7040 passed, 15 skipped.
- Clean: `ruff check specy_road tests scripts`, `specy-road validate`, `export --check` and `digest --check` on the dogfood fixture, `specy-road file-limits`, `scripts/check_clones.py` (0 new) and `scripts/check_test_private_imports.py` (exit 0).
- Parity harness (`tests/parity/`) unchanged and green (A4).
- `scripts/lean_metrics.py --check` was not completed: it times the full suite three times and ran past a 10-minute limit.
- Net package line change: +10 (157 added, 147 removed). The informational estimate was about -60; the difference is the added import lines.
- `constraints/test-private-imports-baseline.txt` now has two stale entries for `grind_session_events._now_iso`, which the tests no longer patch. That file is outside this leaf's zones, so they are left for a shrink.
- Running `validate` or `digest` on the dogfood fixture leaves an ignored `.specyrd/` cache there. pytest then refuses to start until `git clean -fdX tests/fixtures` is run, so the READY command runs pytest first.

## Added

- `specy_road/clock.py` `utc_now()`, `utc_now_iso()`: the one wall-clock read (A1).
- `specy_road/fs_atomic.py` `atomic_write_text()`: the one atomic text writer (A2). Its `tmp=` parameter exists because `AtomicWritePlan` must know the temp name to roll it back.
- Guard or branch: none.
- Mocks: `FrozenDatetime` patched over `specy_road.clock.datetime` (a public module attribute), to pin each site's timestamp form. In three grind tests, `monkeypatch.setattr(gse, "utc_now", ...)` replaces the patch of the removed private `_now_iso`.
- Tests, all in `tests/test_clock_and_atomic_write.py`:
  - `test_each_timestamp_keeps_its_type_and_form`, 9 rows, one per replaced now helper (A1, done-but-wrong check 1). It absorbs `test_the_timestamp_is_utc_to_the_second`, which was removed from `tests/test_grind_session_cleanup.py`.
  - `test_a_writer_keeps_utf8_lf_and_the_umask_mode`, 4 rows: worker_state, worker_outbox, session_presence, brainstorm_session (A3).
  - `test_a_failed_write_leaves_its_temporary_file`, the same 4 rows (A3).
  - `test_a_roadmap_write_keeps_utf8_lf_and_the_umask_mode`: the roadmap_chunk_atomic writer (A3).
  - `test_a_roadmap_write_failing_on_its_second_file_restores_the_first_and_leaves_no_temporary_file`: rollback is kept (done-but-wrong check 2).
  - `test_the_wall_clock_is_read_only_in_clock_py`: scans for wall-clock reads outside clock.py (A1).
  - `test_os_replace_is_only_in_fs_atomic_and_the_allowlist`: AST scan of every `os.replace` call, with the committed `OS_REPLACE_ALLOWED` table (A2, A6, deviation 2).
