# Implementation summary: M13.12

Quieter, accurate validate notices. Commits `36e8aabf` and `cc417326`, then a fix round (after merging `origin/WIP/improvements-0-3-1`), on
`feature/rm-quieter-accurate-validate-notices-untracked-touch-zones-the-managed-gitignore-comment-and-tracked-files-under-new-ignore-rules`.

## Acceptance

- **A1** — `warn_untracked_zones()` (`touch_zone_tracked.py`) now takes `claims=` (the registry entries `run_validation` already loaded) and `show_all=`. Nodes are ranked: claimed or In Progress, then any other status, then Not Started non-leaves, then Not Started unclaimed leaves. At most `LISTED_LIMIT` (10) are named; the rest, including every Not Started unclaimed leaf, are counted: `and N more node(s) (by status: Blocked 9, Not Started 66); `specy-road validate --all` lists every one`. With `show_all`, every node is named. `validate_roadmap_checks.py` changes only the call line (still 398 lines). The existing `--all` flag already reaches it through `show_all`. Its help text is unchanged, because `validate_roadmap.py` may change only call lines. `warn_written_zones` (add-node/edit-node) is unchanged.
- **A2** — `_GITIGNORE_NOTE` and the init template's `.gitignore` comment now say "`.specyrd/manifest.json`, when present, stays tracked". This is a rewording, so the block is the same in every repo. Existing repos see the managed block as `updated` on their next refresh-stubs or upgrade.
- **A3** — `ignore_report.print_matches`: for tracked matches it prints `git rm --cached -- <quoted paths>` (the listed tracked paths, run from the git root, never run for you), plus `git ls-files -ci --exclude-standard` when more exist than are listed. It then prints `UNTRACK_HINT`, which now reads: keep tracking a file meant to be shared (the rule only hides new files); untrack one that is session scratch.
- **A4** — `notice_repeated_ignore_patterns(root)` (`validate_notices.py`, called from `validate_at`) reads the git root's `.gitignore` and prints one stdout notice naming the managed-block patterns also listed above the start marker. It never edits the file.
- **A5** — new `specy_road/context_notice_cache.py`: `report_context_warnings(root, warn, cached=)` captures the stderr of `warn_if_context_over_limits`. With `cached`, it compares a sha256 of that text to `.specyrd/cache/context-warnings.sha256`. If the hash is unchanged, it prints the single stderr line `context: N warnings unchanged (validate --context shows them)`, which keeps `--strict` failing. If the hash changed, it prints the warnings in full and records the new hash. `validate_at` calls `report_context_warnings(root, warn_if_context_over_limits)` with no mode. Folding is on only when the validate CLI's `parse_validate_args` (in `validate_notices.py`, which adds `--context`) calls `fold_next_report(not args.context)`. That setting applies to the next report only: reading it clears it. So `upgrade`, which calls `validate_at(project)`, always prints the warnings in full. `agents_md_block.py` is unchanged. With no warnings, nothing is written and any stale hash is removed, so validating a clean repo (for example the dogfood fixture) writes no cache.

## Scope notes

- `validate_roadmap.py` diff against `origin/WIP/improvements-0-3-1`: three changed or added call lines (`report_context_warnings(...)`, `notice_repeated_ignore_patterns(root)`, `args = parse_validate_args(parser)`). The existing `validate_notices` import line also names the three new functions (`report_context_warnings` is re-exported from `validate_notices`). That line is the only non-call change, and the new calls cannot run without it. The signature, docstring, argparse and help changes from the first round were removed.
- Touch zones confirmed. No files changed outside them. `agents_md_block.py` was not changed.
- Existing tests updated because the acceptance changed behaviour:
  - `test_touch_zone_tracked.py`: one test now claims M1.1 so it is still named. The validate test checks the counted default and the full `--all` line.
  - `test_m13_7_notices.py`: the tail now includes the command line.
  - `test_validate_strict.py`: the second run is folded and still fails `--strict`; a third run with `--context` checks the full warning text.

## Fix round (review `gpt-6.1-sol-low` on `cc417326`)

- **Class 1, a change outside call lines in a call-line-only file:** the `--context` option, its parsing and the fold decision moved to `validate_notices.parse_validate_args` and `context_notice_cache.fold_next_report`. The `validate_at` signature, docstring, `--all` help and the separate import were reverted.
- **Class 2, a disposable cache or sidecar read that can abort a command:** `_changed` now compares raw bytes, so nothing is ever decoded. Read and write each suppress `OSError` on their own: any read failure is a miss, so the warnings print in full; a write failure is ignored. The unlink when there are no warnings already suppressed `OSError`.

## Probes

- Hash file with invalid UTF-8 (`\xff\xfe`…): miss, full warnings, hash rewritten, next run folds. Test: `test_a_non_utf8_hash_file_is_a_miss_and_is_rewritten`.
- Truncated hash file (10 bytes): miss, full warnings, hash rewritten. Test: `test_a_truncated_hash_file_is_a_miss`.
- A directory in place of the hash file: miss on every run; the unlink on a later run with no warnings fails quietly. Test: `test_a_directory_in_place_of_the_hash_file_is_a_miss_every_time`.
- A file in place of `.specyrd/cache/`: miss on every run; the write fails quietly. Test: `test_a_file_in_place_of_the_cache_dir_is_a_miss`.
- Hash file with mode 000 (non-root): miss on every run. Test: `test_an_unreadable_hash_file_is_a_miss`.
- `validate_at`'s call with no CLI flag (the `upgrade` path): never folds. Test: `test_without_the_validate_cli_flag_reports_never_fold`.
- CLI flag applies to one report only, so a flag set by one `main()` run cannot fold an in-process `upgrade` that follows. Test: `test_the_cli_flag_folds_one_report_only`. The full suite passes, so no in-process leak was found.
- `notice_repeated_ignore_patterns`, the other sidecar read in this leaf (the git root `.gitignore`):
  - a directory in place of the file: silent;
  - invalid UTF-8 (`errors="replace"`): notice printed, no error;
  - mode 000: silent;
  - a block missing its end marker: notice printed, no error.

  These were checked by hand. The function catches `OSError` and decodes with replace.
- `ignore_report._top_ignore` / `observe` (A3 path): an existing read, already wrapped by `attempt()`, which turns any failure into `ignore check skipped: …`. Unchanged.
- `touch_zone_tracked` reads no files, only `git ls-files`, which already returns `None` on failure. Registry claims: entries that are not dicts are skipped.
- `git diff origin/WIP/improvements-0-3-1 -- specy_road/bundled_scripts/validate_roadmap.py`: one import line plus three call lines.

## Verification

- `python -m pytest -q -n 4`: 4409 passed, 1 failed before the `test_validate_strict.py` update. All 7 tests in that file pass after it. After the fix round and the merge: 4459 passed.
- `specy-road file-limits`, `validate` / `export --check` / `digest --check` on the dogfood fixture, and `ruff check` all pass.

## Added

- `touch_zone_tracked.LISTED_LIMIT`: the cap of 10 named nodes (A1).
- `touch_zone_tracked._status`: a node's status, defaulting to Not Started, used for ranking and the per-status counts (A1).
- `touch_zone_tracked._rank`: the priority order, and which nodes are counted only (A1).
- `touch_zone_tracked._hidden`: the `N [more] node(s) (by status: …)` clause (A1).
- `warn_untracked_zones` kwargs `claims`, `show_all`: claims passed in rather than re-read; `--all` lists everything (A1).
- `_untracked_line` optional `hidden` argument: appends the counted clause (A1).
- `ignore_report.untrack_command`: the `git rm --cached` line, quoted with `shlex`, and a pointer to the rest when the list is capped (A3).
- `validate_notices._patterns`, `notice_repeated_ignore_patterns`: the repeated-pattern notice (A4).
- `context_notice_cache.py` (`HASH_FILENAME`, `_hash_path`, `_changed`, `report_context_warnings`): fold unchanged context warnings (A5).
- Guard in `report_context_warnings`: no warnings means no cache write and a stale hash is removed, so the fixture and clean repos stay clean (A5).
- `context_notice_cache.fold_next_report` / `_fold_next` and `report_context_warnings(cached=None)`: the CLI turns folding on for one report only; `validate_at` (upgrade) never folds. This replaced the first round's `validate_at(context_cache=)` kwarg (A5, call-line-only).
- `validate_notices.parse_validate_args`: adds `--context`, parses, and sets folding, keeping the option out of `validate_roadmap.py` (A5).
- `validate_notices.__all__`: marks `report_context_warnings` as a re-export for the single `validate_roadmap.py` import line (A5).
- Guard in `_changed`: bytes comparison (no decode) plus separate `OSError` suppression on read and write. Any unreadable hash is a miss (fix round).
- Tests in `tests/test_m13_12_context_cache.py`: invalid UTF-8, truncated, directory as the hash file, file as the cache dir, mode 000; no flag never folds; the flag folds one report only.
- Tests in `tests/test_m13_12_quieter_notices.py`: 85-node bounded line pinned exactly; the 10 cap with per-status counts; `show_all` lists 85; `.gitignore` comment in a repo with no stub pack, plus the template; the tracked-match command and hint; two repeats pin the notice and the file is unchanged; no repeats prints nothing; context first, unchanged and changed runs; uncached (upgrade / `--context`) always full; no warnings prints nothing.
- Mocks: none (the context tests use a small fake `warn` callable that prints to stderr).
