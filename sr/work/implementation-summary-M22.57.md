# Implementation summary: M22.57 `promotion-without-wip-history`

## What changed

Promotion to `main` is one commit whose only parent is `main`'s recorded tip. The candidate tree is the selected WIP snapshot (`git read-tree -u --reset`), so a file the snapshot deleted is gone, and every path on M22.54's promotion denylist is removed before that commit. Nothing in the procedure merges the WIP line into `chore/release-*` or `main`. The release PR may land by squash or by GitHub's two-parent merge; the tag is the commit that landing adds to `main`. Both `docs/release-runbook.md` and `docs/toolkit-development.md` say this, and both drop their links to this repository's `.cursor/rules/`. The human-owned release steps (version choice, tag re-push, `pypi` approval, live-on-index confirmation) are unchanged.

On a pull request or push to `main`, `validate.yml` (already `fetch-depth: 0`) runs `--promotion` over `base..head`. The workflow reads `scripts/check_public_hygiene.py` and `scripts/public_hygiene_allow.txt` from the base commit when that commit has them, and the script does the same when invoked directly, so a candidate-local widening does not apply. Every newly reachable commit is judged, side branches included and merges diffed with `-m`: an addition, modification, or rename destination at a denied path is refused; a deletion passes. Message and identity checks still apply. A missing endpoint or a failed git query exits 1 and says the history is incomplete.

`release-publish.yml`'s existing build job, before either publish job, unpacks the sdist and the wheel into plain directories (the sdist's single top directory removed) and runs `--promotion --tree` on them, with no git index. `scripts/verify_wheel_contents.py` checks both archives for a denied member path and for denied text in a member. A scan or read failure exits non-zero, so the publish jobs, which need the build, do not start. The trusted-publisher steps are unchanged.

An sdist directory entry is not a file, whether or not its name ends with `/`. The single top directory is removed from the files that remain, so a hit names `docs/design-notes/x.md` rather than `pkg-1.0/docs/design-notes/x.md`. The same rule covers member text and `--archive`. The review named `_relative_members`; `--archive` was still judging stored names, so it had the same class and now uses that rule. The publish unpack scans the filesystem after `extractall`, which already yields one top directory, so the workflow was left as it is.

## Decisions

- The path denylist stays in the gate. `--drop-denied` is the runbook's removal step so the documented command and the check use one list. `git rm -f` is required there: after `read-tree`, HEAD is still `main`, so the snapshot's files are staged.
- A path that exists in the worktree but not in the base commit is "base has no allow file", not an incomplete history. `git show` says "exists on disk, but not in" for that case.
- An sdist member path is reported relative to the distribution root. A directory entry ends with `/` or has another member under it, and only then is the single top directory removed. A wheel's names are already relative to the wheel root, so they are not stripped (a wheel's single `specy_road/` prefix is the package, not an sdist wrapper).
- `--tree` scans only the given directories. The publish step points it at the unpacked archives and does not consult `git ls-files`.

## Final touch zones

The brief's eight, unchanged: `docs/release-runbook.md`, `docs/toolkit-development.md`, `.github/workflows/release-publish.yml`, `.github/workflows/validate.yml`, `scripts/verify_wheel_contents.py`, `scripts/check_public_hygiene.py`, `tests/test_verify_wheel_contents.py`, `tests/test_lean_gates.py`.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 python -m pytest -p no:cacheprovider -n 4 tests/test_lean_gates.py tests/test_verify_wheel_contents.py tests/test_package_data_dotfiles.py`: 117 passed.
- `ruff check specy_road tests scripts`: pass.
- `specy-road file-limits`: pass. `docs/release-runbook.md` is 922 lines after the integration merge and warns at the 750-line alert; the cap is 1000.

## Accepted limits

- The first promotion onto `main` is judged by the candidate's own script and allowlist, because `main` has neither yet. Later changes to that policy apply only after they land on `main`.
- Candidates already published are not rescanned. The publish scan does not judge archives already on an index.
- `scripts/lean_metrics.py` stays off the path denylist while M22.54 leaves it tracked.
- Squash drops per-commit WIP history from `main` on purpose. The WIP line keeps it.
- No CHANGELOG `[Unreleased]` line: `CHANGELOG.md` is outside the touch zones. `specy-road ready` warns and does not fail.
- A directory entry with neither a trailing slash nor a member under it is kept, because it cannot be told from a file. Two top directories, or a file that sits beside the top directory, are not stripped. Zip members are not stripped.

## Probes

- Reviewer's tar members `pkg-1.0` and `pkg-1.0/docs/design-notes/x.md`, through the wheel check: the hit names `docs/design-notes/x.md`.
- The same tar through `--promotion --archive`: the hit names `docs/design-notes/x.md`.
- Nested directory entries in both spellings (`pkg-1.0`, `pkg-1.0/`, `pkg-1.0/docs`, `pkg-1.0/docs/`, and the design-notes directory): the hit names `docs/design-notes/x.md`.
- Denied text in `pkg-1.0/README.md` beside a top directory entry: the hit names `README.md`.
- `extractall` of that tar: one top directory, file `docs/design-notes/x.md` under it; `--promotion --tree` on that directory names the same path. The publish workflow already scans that unpacked tree, so it was not changed.
- Two top directories: both prefixes stay. A file beside the top directory: the prefix stays. A zip member keeps its stored path. A directory entry with no child and no trailing slash does not rename a sibling file.
- `ruff check specy_road tests scripts`: pass. No function that exists on the integration branch gained a branch.

## Added

### Helpers

- `_HistoryIncomplete` and `_ScanFailed`: a range git failure and an unreadable archive or tree, each turned into exit 1.
- `_range_git`: a git query in the range whose failure is incomplete history.
- `_blob`: a file at `commit:path`, or none when the commit does not have it.
- `_incomplete`: the "history is incomplete" exit line.
- `_diff_destinations`: status and path from `git diff-tree -z`; a rename or copy contributes its destination.
- `changed_path_hits`: denied additions, modifications and rename destinations in `base..head`; deletions are not hits.
- `_file_members`: stored file names. A directory ends with `/` or has another member under it.
- `_relative_members`: sdist paths with the single top directory removed, after directory entries are dropped.
- `_member_texts` and `archive_promotion_hits`: member text and denied member paths for a wheel or an sdist. A read failure is a hit so the wheel check exits non-zero.
- `listed_files`: files under a directory, relative to it, with no git index.
- `_drop_denied`: `git rm -f` of every tracked path the denylist refuses.
- `_write_allow`, `_child_argv`, `_delegate_base`: run the base commit's script, with that commit's allow file, and pass `--root` so the extracted copy still scans the checkout.
- `_tree_hits`: file and path checks over `--tree` directories.
- `_span_hits`: messages, and under `--promotion` the identity check and `changed_path_hits`.
- `_release_allow_dir`: drops the temporary allow file after the run that created it.
- `_run`: the scan, after the base-policy delegation.
- `_hygiene`, `_required`, `_denied` in `scripts/verify_wheel_contents.py`: load the gate, keep the required-file check for a `.whl`, and refuse a denied member or denied text in any archive passed in.

### Branches and guards

- `FROM_BASE` skips a second delegation, so the base copy does not load itself again.
- A missing allow-file blob ("does not exist" or "exists on disk, but not in") is absence, not incomplete history.
- Diff status `D` is ignored; `A`, `M`, `T`, `R` and `C` at a denied destination are refused (tests: the promotion-range cases).
- `--tree` does not call `git ls-files` (test: the unpacked-tree scan).
- `git rm -f` in `--drop-denied`, because `read-tree` leaves the snapshot staged against `main` (test: the runbook promotion commit).
- Sdist prefix stripped only when every remaining file sits under one top directory. A directory entry does not count as that file (test: the tar fixture writes the entry with and without a trailing slash, and names `docs/design-notes/x.md`, not the `pkg-1.0/` form).
- `OSError` while reading a scanned file, and a bad zip or tar, exit 1 (test: unreadable zip and tar).

### Mocks

- none.

### Tests

- `test_public_hygiene_range_checks_every_message_and_names_a_missing_endpoint`: extended so a missing endpoint, including a missing base under `--promotion`, exits 1 and says the history is incomplete.
- `test_public_hygiene_promotion_range_judges_reachable_commits`: a WIP merge whose tip has no `sr/`, add-then-delete, a merge of that history, a modification then a deletion, and a rename onto a denied path then a deletion (each refused); deletion-only cleanup and a two-parent landing merge with no WIP history (each accepted).
- `test_runbook_promotion_commit_drops_denied_paths_and_keeps_one_parent`: `read-tree` plus `--drop-denied` leaves one parent, drops `sr/`, design notes, a `research` file and a file the snapshot deleted, and keeps the shipped template path. The promotion range is accepted.
- `test_public_hygiene_promotion_uses_the_base_allowlist`: a candidate `bot:` widening is still refused, because the base commit's script and allow file judge the range.
- `test_public_hygiene_promotion_scans_an_unpacked_tree`: `--promotion --tree` on a directory that is not a git checkout.
- `test_sdist_and_wheel_promotion_scan`: zip and tar; a denied member is named, denied text in an allowed member fails, shipped template paths pass. The tar fixture adds explicit directory entries, and the sdist text hit names `README.md`.
- `test_fails_when_the_archive_cannot_be_read`: a zip and a tar that are not archives exit non-zero.
- The existing required-file rows in `tests/test_verify_wheel_contents.py` are unchanged.
