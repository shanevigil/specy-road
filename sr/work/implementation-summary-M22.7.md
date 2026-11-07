# Implementation summary: M22.7 — ready changelog reminder

## Touch zones (confirmed)

`specy_road/bundled_scripts/review_cli.py` imports `add_ready_parser` from `review_ready_merge` and does not call `cmd_ready` itself; `add_ready_parser` already points the `ready` subcommand at `review_ready_merge.cmd_ready`. No change outside the zones.

Final touch zones: `specy_road/changelog_check.py`, `specy_road/review_ready_merge.py`, `tests/test_ready_changelog_warning.py`, `docs/orchestration-review.md`, `CHANGELOG.md`.

## Change

`specy-road ready` still writes READY and returns the same exit code. After a successful write, next to the trial-merge lines, it prints one stderr warning when the branch changes a product path and `CHANGELOG.md`'s `## [Unreleased]` section at HEAD has no more non-blank lines than at the merge base. A missing changelog at the base counts as an empty section. No changelog or no that heading at HEAD, no product path, or the phrase `no CHANGELOG entry` in the leaf's acceptance or planning sheet stays silent. Git failing to run, or a changelog read failing for any reason other than the file being absent, prints nothing.

A product path is a changed path other than `CHANGELOG.md`, anything under `tests/`, and bookkeeping. Bookkeeping in a nested layout is every path under the project prefix (`sr/` here). Otherwise it is `is_trial_merge_bookkeeping` (`roadmap/`, `planning/`, `work/`, `roadmap.md`, `roadmap-context.md`). The warning names `## [Unreleased]`, up to three product paths, and how to exempt the leaf.

## Added

### Helpers

- `missing_entry_warning` — the one pure decision (changed paths, project prefix, changelog text at base and HEAD, exemption text) so the warning does not depend on git.
- `_unreleased_nonblank` — counts non-blank lines under `## [Unreleased]` up to the next `## ` heading, so editing an existing line does not count as a new entry.
- `_unreleased_heading` — matches `## [Unreleased]` with only trailing space after it, so a version heading is a different section.
- `_product` — drops `CHANGELOG.md`, `tests/`, nested project paths, and unnested trial-merge bookkeeping from the paths the warning names.
- `_changelog_at` — reads `CHANGELOG.md` with `git show`; an absent path is empty text, and any other failure is no warning.
- `_exempt_text` — joins the node's acceptance lines and its planning sheet so either can carry `no CHANGELOG entry`.
- `_changelog_warning` — after ready has written, resolves the target once, reads the diff and both changelog texts, and calls the pure function.
- `_cli` — runs the ready CLI in the new test the same way `tests/test_ready_command.py` does.

### Branches or guards

- Exemption phrase, any case, returns None — a leaf that says `no CHANGELOG entry` is not warned.
- No `## [Unreleased]` heading at HEAD returns None — a repository with no changelog or no that heading stays silent.
- A missing heading at the base counts as zero lines — a changelog that is new on the branch, with an empty section, still warns.
- A higher non-blank count at HEAD returns None — a line added under `[Unreleased]` is silent.
- No product path returns None — tests-only, nested `sr/`-only, and unnested roadmap/planning/work changes stay silent.
- `git show` that never ran, or failed for a reason other than the path being absent, returns None — the reminder stays advisory.
- A planning sheet that cannot be read returns None — a failed read does not warn.
- Acceptance that is not a list, or a planning path that is missing or not a string, still builds the exemption text from what is there.
- `cmd_ready` prints the reminder only when ready already returned 0 — refusals and the READY file are unchanged.

### Mocks

- none

### Tests

- `test_missing_entry_warning` — one table for the pure function: package change with no entry (warns and names the section, at most three paths), an added line, an edited line, a line under a version heading only, a new changelog with an empty section, docs-only, tests-only, nested `sr/`-only, unnested bookkeeping, acceptance and sheet exemptions, no changelog, and no heading.
- `test_ready_changelog_reminder` — ready CLI warns, stays silent when a line was added, and warns when `CHANGELOG.md` is new at HEAD with an empty section; each exits 0 with a valid READY file.
