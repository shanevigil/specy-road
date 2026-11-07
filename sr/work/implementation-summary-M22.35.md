# Implementation summary for M22.35

## Summary

`specy-road upgrade` no longer copies gitignored files into its temporary directory. The mirror is built from what git tracks, untracked files git does not ignore, and the paths the refreshes read (so an ignored `CLAUDE.md` is still there). A nested repository is left out even when git lists the directory. A dry run copies the checkout once, prints one line before that copy, and reuses the tree for the copy it validates. The plan is unchanged when the only difference is large ignored content.

- **A1.** Tracked files, untracked non-ignored files, and files the refreshes read are copied. `.env`, an ignored directory such as `node_modules`, and a nested repository are not, on a real run or a dry run. The temp directory is listed while it still exists.
- **A2.** A dry run calls `Mirror.build` once and `Mirror.reuse` for the validation copy. It prints `copying tracked and untracked files into a temporary directory; ignored files are not copied` before the copy. Existing parity tests still require the dry run's result to match the real run.
- **A3.** `test_ignored_secrets_and_a_nested_repo_stay_out_of_the_mirror` and `test_large_ignored_content_does_not_change_the_plan`. `docs/upgrading.md` and the CHANGELOG `[Unreleased]` Fixed entry describe the copy.

## Decisions a reviewer should check

1. **What the refreshes read is an explicit set, not a trace of every `open`.** It is `CLAUDE.md`, the ignore files, the manifest and the paths it records, the agents files, shipped schemas, profiles and load-order docs, `roadmap/orchestration.yaml`, `constraints/file-limits.yaml`, and the skill, stub and skill-link paths refresh-stubs stats. A path is added only when it exists. Anything else that is gitignored stays out.
2. **A link whose target was left out is still placed, and named.** `Mirror._place` copies that target so the link resolves as before, and prints `upgrade: copying ignored <path> because a link in the checkout points at it` when the target is an ignored path inside the checkout. A symlink at `node_modules` would still copy that tree; the line is the report the planning sheet asks for.
3. **`changed_since` no longer treats every ignored path as a checkout edit.** It compares paths the mirror read, then walks only far enough to see a new non-ignored path. Ignored directories that hold nothing the mirror read are not entered. `check-ignore` and `ls-files` pass `-c core.fsmonitor=` so those calls do not run the caller's fsmonitor; the dry-run global-config test still requires the marker to stay empty.
4. **The validation copy is a snapshot of the plan mirror, taken before the refresh.** `snapshot_outside` drops `.git` and keeps an unreadable file as an empty file of the same mode, which is what `Mirror._copy_file` already does. `reuse` retargets absolute symlinks from the plan mirror's `outside` to the validation copy's, then `git init`s. The dry run still has two inits (plan mirror, validation copy); the second init is not a second walk of the checkout.
5. **`build_without_git` in `tests/test_upgrade_preview.py` now accepts the new `build` keywords.** The assertion is unchanged: a mirror whose `.git` was removed still exits 2 with `git init failed in the temporary copy`. The dry run checks that immediately after `build`, because the validation copy's init is a separate call the wrapper does not see.

## Known limits, left as they are

- While the dry-run scratch environment is active, git does not read the caller's global excludes file. That is the existing rule (the plan's mirror reads no global config). A file ignored only by a global excludes file can be copied on a dry run and omitted on a real run. Repo `.gitignore` and `info/exclude` apply on both.
- `work/` is still not copied, symlink or not.
- An ignored directory that a symlink points at is copied whole, with one report line. The maintainer decides if that path has to be copied.

## Changes

- `specy_road/bundled_scripts/upgrade_plan.py`: selected copy, reuse, `changed_since`.
- `specy_road/bundled_scripts/upgrade.py`: the extra paths, and a dry run that builds once.
- `tests/test_upgrade_preview.py`: the two acceptance tests, and the `build` wrapper's signature.
- `docs/upgrading.md`, `CHANGELOG.md`.

**Final touch zones:** `specy_road/bundled_scripts/upgrade_plan.py`, `specy_road/bundled_scripts/upgrade.py`, `tests/test_upgrade.py`, `tests/test_upgrade_preview.py`, `docs/upgrading.md`, `CHANGELOG.md`. `tests/test_upgrade.py` needed no edit. Call sites outside the zones (`tests/test_upgrade_parity.py`, `tests/test_upgrade_plan_parity.py`, `tests/test_upgrade_work_templates.py`, and the other upgrade importers) were not edited; the parity and work-template modules pass.

## Verification

- `pytest -n 4 tests/test_upgrade.py tests/test_upgrade_preview.py tests/test_upgrade_parity.py tests/test_upgrade_plan_parity.py tests/test_upgrade_work_templates.py`: 112 passed.
- `specy-road file-limits`: OK. The warnings are pre-existing files over the soft alert.

## Added

Helpers and branches:

- `_ancestors`: parent directories of the paths to copy, so an ignored directory that contains one of them is still entered.
- `_ignored`: one `check-ignore -v` batch per directory; a git failure is `GitFailed` (exit 2), the same as the other git calls upgrade depends on.
- `_appeared`: new non-ignored checkout paths after the dry run; ignored directories that were not read are not walked, so they are not reported as edits.
- `_copy_keeping_mode`: the dry-run snapshot of an unreadable file stays an empty file of the same mode; `shutil.copytree` would raise `Error` and the unreadable-`AGENTS.md` dry run would not match the real run.
- `snapshot_outside`: the pre-refresh tree the validation copy reuses, without `.git`.
- `_retarget`: absolute symlinks in that snapshot point at the validation copy, not the plan mirror.
- `Mirror.reuse`: the validation mirror; second `git init`, no second checkout walk.
- `Mirror._init_git`: the init both `build` and `reuse` need, unchanged command.
- `Mirror._resolve_links`: the existing link loop, moved out of `build` so `build` stays within the line cap.
- `Mirror._copy_selected`, `_listed`, `_without_skipped`, `_skip_rel`, `_under_nested`, `_link_parents`, `_walk`: the copy. `_under_nested` and a directory that itself contains `.git` drop nested repositories, including one git lists as `nested/repo/`. `_link_parents` keeps a symlink ancestor so the walk does not replace it with a real directory.
- `Mirror._report_ignored`: the on-demand report when a link target inside the checkout is gitignored.
- `if not (mirror.repo / ".git").is_dir()` in `_dry_run`: the existing no-`.git` failure still fires on the plan mirror.
- `_present`, `_recorded_paths`, `_skill_paths`, `_mirror_extras`: the paths the refreshes read, copied even when git ignores them.
- `-c core.fsmonitor=` on `ls-files` and `check-ignore`: those calls must not run the caller's fsmonitor (decision 3).
- `changed_since` no longer walks every ignored path: an ignored file the mirror did not read is not a "dry run modified" hit.

Tests:

- `test_ignored_secrets_and_a_nested_repo_stay_out_of_the_mirror`: lists the temp directory while it exists, on both paths; an ignored `.env`, `node_modules`, and a nested repo are absent; an untracked `keep-me.txt` and `AGENTS.md` are present; the dry run prints the copy line once.
- `test_large_ignored_content_does_not_change_the_plan`: the dry-run plan with a 1MB ignored tree and a secret equals the plan without them.
- `build_without_git` forwards `build`'s new keywords so the existing no-`.git` assertion still runs (decision 5).

Mocks: none.
