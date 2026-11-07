# Implementation summary: M22.7 — ready changelog reminder

## Touch zones (confirmed)

`specy_road/bundled_scripts/review_cli.py` imports `add_ready_parser` from `review_ready_merge` and does not call `cmd_ready` itself; `add_ready_parser` already points the `ready` subcommand at `review_ready_merge.cmd_ready`. No change outside the zones.

Final touch zones: `specy_road/changelog_check.py`, `specy_road/review_ready_merge.py`, `tests/test_ready_changelog_warning.py`, `docs/orchestration-review.md`, `CHANGELOG.md`.

## Change

`specy-road ready` still writes READY and returns the same exit code. After a successful write, next to the trial-merge lines, it prints one stderr warning when the branch changes a product path and `CHANGELOG.md`'s `## [Unreleased]` section at HEAD has no more non-blank lines than at the merge base. A missing changelog at the base counts as an empty section. No changelog or no that heading at HEAD, no product path, or the phrase `no CHANGELOG entry` in the leaf's acceptance or planning sheet stays silent. Git failing to run, or a changelog read failing for any reason other than the file being absent, prints nothing. A configured planning sheet that cannot be read as text (missing, a directory, or unreadable) is the same kind of failure and stays silent; an empty file is a successful read.

A product path is a changed path other than `CHANGELOG.md`, anything under `tests/`, and bookkeeping. Bookkeeping in a nested layout is every path under the project prefix (`sr/` here). Otherwise it is `is_trial_merge_bookkeeping` (`roadmap/`, `planning/`, `work/`, `roadmap.md`, `roadmap-context.md`). The warning names `## [Unreleased]`, up to three product paths, and how to exempt the leaf. A backslash or non-printable character in a displayed path is escaped, so that warning stays one line; other printable characters are kept.

## Added

### Helpers

- `missing_entry_warning` — the one pure decision (changed paths, project prefix, changelog text at base and HEAD, exemption text) so the warning does not depend on git.
- `_display_path` — escapes `\\` and every non-printable character in a path so the warning is one line. Printable characters, including commas and non-ASCII, are kept.
- `_unreleased_nonblank` — counts non-blank lines under `## [Unreleased]` up to the next `## ` heading, so editing an existing line does not count as a new entry.
- `_unreleased_heading` — matches `## [Unreleased]` with only trailing space after it, so a version heading is a different section.
- `_product` — drops `CHANGELOG.md`, `tests/`, nested project paths, and unnested trial-merge bookkeeping from the paths the warning names.
- `_changelog_at` — reads `CHANGELOG.md` with `git show`; an absent path is empty text, and any other failure is no warning.
- `_exempt_text` — joins the node's acceptance lines and its planning sheet so either can carry `no CHANGELOG entry`. A configured sheet that cannot be read returns None, so the reminder stays silent.
- `_changelog_warning` — after ready has written, resolves the target once, reads the diff and both changelog texts, and returns the warning line, if any, for the same print loop as the trial-merge notes.
- `_sheet` — the fixture's one planning sheet, so the CLI cases can remove it, replace it with a directory, or empty it.

### Branches or guards

- Exemption phrase, any case, returns None — a leaf that says `no CHANGELOG entry` is not warned.
- No `## [Unreleased]` heading at HEAD returns None — a repository with no changelog or no that heading stays silent.
- A missing heading at the base counts as zero lines — a changelog that is new on the branch, with an empty section, still warns.
- A higher non-blank count at HEAD returns None — a line added under `[Unreleased]` is silent.
- No product path returns None — tests-only, nested `sr/`-only, and unnested roadmap/planning/work changes stay silent.
- `git show` that never ran, or failed for a reason other than the path being absent, returns None — the reminder stays advisory.
- A configured planning sheet that cannot be read as text returns None — missing path, directory, and unreadable file share that one failure; an empty file does not.
- Acceptance that is not a list, or a planning path that is missing or not a string, still builds the exemption text from what is there.
- `cmd_ready` prints the reminder only when ready already returned 0 — refusals and the READY file are unchanged.

### Mocks

- none

### Tests

- `test_missing_entry_warning` — one table for the pure function: package change with no entry (warns and names the section, at most three paths), an added line, an edited line, a line under a version heading only, a new changelog with an empty section, docs-only, tests-only, nested `sr/`-only, unnested bookkeeping, acceptance and sheet exemptions, no changelog, no heading, and a path containing a newline, carriage return, tab, another control character, a backslash, a line separator, and printable `é` (one printable line).
- `test_ready_changelog_reminder` — ready CLI warns, stays silent when a line was added, warns when `CHANGELOG.md` is new at HEAD with an empty section, stays silent when the configured sheet is missing or a directory, still warns when that sheet is an empty file, and stays one stderr line when a product path contains a newline; each exits 0 with a valid READY file.

## Fix round

A configured path that is not readable text was treated as an empty successful read, so `ready` still warned. The sheet is now read with one `read_text`; `OSError` and `ValueError` stay silent. The copied one-call `_cli` helper is inlined. `cmd_ready` prints the reminder on the trial-merge loop, so its complexity stays 3, the same as at the branch base (`trial_merge_warning` 5, `add_ready_parser` 1, unchanged).

## Probes

- Class: a configured path that is not readable text was treated as empty content, so the reminder still fired. `_exempt_text` missing sheet (`missing-sheet`): exit 0, READY written, no warning.
- Same class, directory instead of a file (`sheet-dir`): `read_text` raises `IsADirectoryError`, same handler, exit 0, READY written, no warning.
- Same function, empty file (`empty-sheet`): successful read, warning still printed. Empty content is not a failed read.
- Same function, no `planning_dir`: the read is not attempted; acceptance text alone is the exemption. Not a failed read.
- `_changelog_at` when `CHANGELOG.md` is a git tree: `git show` exits 0 with a listing and no `## [Unreleased]` heading, so HEAD stays silent. Absence is still the only case turned into empty text, and only when git says the path is not in the rev.
- `missing_entry_warning` does not read files. Empty base text is the absent-changelog input, covered by the table row "new changelog with empty unreleased", which warns.
- Class: a private test helper copied for a single call. The new file's `_cli` matched `tests/test_ready_command.py::_cli` and had one call; that call is inlined. No other helper in the new file copies one from `test_ready_command.py`. `test_ready_command._cli` has many calls, so it stays there.
- Class: a character in a displayed path that is not printable splits the one stderr warning. `missing_entry_warning` on `docs/line\nbreak.md` plus `\r`, `\t`, `\x01`, `\`, U+2028, and `é` returns one printable line; those controls are `\n`, `\r`, `\t`, `\x01`, `\\`, and `\u2028`, and `é` is kept.
- Same class through `cmd_ready` (`newline-path`): stderr is one line, exit 0, READY written, and the newline path is shown as `docs/line\nbreak.md` before `docs/x.md` and `src/a.py`.
- The warning's only interpolated repo text is those paths. Exemption text is not printed. Changelog body is not printed. `trial_merge_warning` does not receive these paths.
- A comma or space in a path is kept, so it is not separated from the comma between paths. That limit is stated on `missing_entry_warning` and in the ready paragraph of `docs/orchestration-review.md`. Argparse help lives in `review_gate_ready.py`, outside this leaf's zones, and was not edited.
- `cmd_ready` complexity stays 3, the same as at the branch base. `_display_path` is 1 and `missing_entry_warning` is 5.
