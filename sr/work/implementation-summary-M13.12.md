# Implementation summary: M13.12

Quieter, accurate validate notices. Commit `36e8aabf` on
`feature/rm-quieter-accurate-validate-notices-untracked-touch-zones-the-managed-gitignore-comment-and-tracked-files-under-new-ignore-rules`.

## Acceptance

- **A1** — `warn_untracked_zones()` (`touch_zone_tracked.py`) now takes `claims=` (the registry entries `run_validation` already loaded) and `show_all=`. Nodes are ranked: claimed or In Progress, then any other status, then Not Started non-leaves, then Not Started unclaimed leaves. At most `LISTED_LIMIT` (10) are named; the rest, including every Not Started unclaimed leaf, are counted: `and N more node(s) (by status: Blocked 9, Not Started 66); `specy-road validate --all` lists every one`. With `show_all`, every node is named. `validate_roadmap_checks.py` changes only the call line (still 398 lines). `--all` help text in `validate_roadmap.py` now mentions it. `warn_written_zones` (add-node/edit-node) is unchanged.
- **A2** — `_GITIGNORE_NOTE` and the init template's `.gitignore` comment now say "`.specyrd/manifest.json`, when present, stays tracked". This is a rewording, so the block is the same in every repo. Existing repos see the managed block as `updated` on their next refresh-stubs or upgrade.
- **A3** — `ignore_report.print_matches`: for tracked matches it prints `git rm --cached -- <quoted paths>` (the listed tracked paths, run from the git root, never run for you), plus `git ls-files -ci --exclude-standard` when more exist than are listed. It then prints `UNTRACK_HINT`, which now reads: keep tracking a file meant to be shared (the rule only hides new files); untrack one that is session scratch.
- **A4** — `notice_repeated_ignore_patterns(root)` (`validate_notices.py`, called from `validate_at`) reads the git root's `.gitignore` and prints one stdout notice naming the managed-block patterns also listed above the start marker. It never edits the file.
- **A5** — new `specy_road/context_notice_cache.py`: `report_context_warnings(root, warn, cached=)` captures the stderr of `warn_if_context_over_limits`. With `cached`, it compares a sha256 of that text to `.specyrd/cache/context-warnings.sha256`. If the hash is unchanged, it prints the single stderr line `context: N warnings unchanged (validate --context shows them)`, which keeps `--strict` failing. If the hash changed, it prints the warnings in full and records the new hash. `validate_at` got `context_cache: bool = False`, so `upgrade` (which calls `validate_at(project)`) always prints the warnings in full. The validate CLI passes `context_cache=not args.context`, and the new `--context` flag prints them in full. `agents_md_block.py` is unchanged. With no warnings, nothing is written and any stale hash is removed, so validating a clean repo (for example the dogfood fixture) writes no cache.

## Scope notes

- `validate_roadmap.py` changes go beyond call lines: the `validate_at` kwarg plus docstring line, the `--context` argparse option and `--all` help text, and one import line for each new call. The CLI flag that A5's own message names needs these.
- Touch zones confirmed. No files changed outside them. `agents_md_block.py` was not changed.
- Existing tests updated because the acceptance changed behaviour:
  - `test_touch_zone_tracked.py`: one test now claims M1.1 so it is still named. The validate test checks the counted default and the full `--all` line.
  - `test_m13_7_notices.py`: the tail now includes the command line.
  - `test_validate_strict.py`: the second run is folded and still fails `--strict`; a third run with `--context` checks the full warning text.

## Verification

- `python -m pytest -q -n 4`: 4409 passed, 1 failed before the `test_validate_strict.py` update. All 7 tests in that file pass after it.
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
- Guard in `_changed`: an `OSError` on the cache counts as changed, so the warnings print in full and validate never fails on the cache (A5).
- Guard in `report_context_warnings`: no warnings means no cache write and a stale hash is removed, so the fixture and clean repos stay clean (A5).
- `validate_at(context_cache=False)` and the validate `--context` flag: upgrade prints in full; the CLI folds unless `--context` (A5).
- Tests in `tests/test_m13_12_quieter_notices.py`: 85-node bounded line pinned exactly; the 10 cap with per-status counts; `show_all` lists 85; `.gitignore` comment in a repo with no stub pack, plus the template; the tracked-match command and hint; two repeats pin the notice and the file is unchanged; no repeats prints nothing; context first, unchanged and changed runs; uncached (upgrade / `--context`) always full; no warnings prints nothing.
- Mocks: none (the context tests use a small fake `warn` callable that prints to stderr).
