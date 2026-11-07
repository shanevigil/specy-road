# Implementation summary for M22.35

## Summary

`specy-road upgrade` no longer copies gitignored files into its temporary directory. The mirror is built from what git tracks, untracked files git does not ignore, and the paths the refreshes read (so an ignored `CLAUDE.md` is still there). A nested repository is left out even when git lists the directory. A dry run copies the checkout once, prints one line before that copy, and reuses the tree for the copy it validates. The plan is unchanged when the only difference is large ignored content.

- **A1.** Tracked files, untracked non-ignored files, and files the refreshes read are copied. `.env`, an ignored directory such as `node_modules`, and a nested repository are not, on a real run or a dry run, including when a non-ignored symlink points at them. A global excludes file hides the same paths on both paths. The temp directory is listed while it still exists.
- **A2.** A dry run calls `Mirror.build` once and `Mirror.reuse` for the validation copy. It prints `copying tracked and untracked files into a temporary directory; ignored files are not copied` before the copy. An ignored `roadmap-context.md` that already matches the roadmap is in that copy, so the preview does not report a rewrite. Existing parity tests still require the dry run's result to match the real run.
- **A3.** `test_ignored_secrets_and_a_nested_repo_stay_out_of_the_mirror` and `test_large_ignored_content_does_not_change_the_plan`. `docs/upgrading.md` and the CHANGELOG `[Unreleased]` Fixed entry describe the copy.

## Decisions a reviewer should check

1. **What the refreshes read is an explicit set, not a trace of every `open`.** It is `CLAUDE.md`, the ignore files, the manifest and the paths it records, the agents files, shipped schemas, profiles and load-order docs, `roadmap/orchestration.yaml`, `constraints/file-limits.yaml`, the skill, stub and skill-link paths refresh-stubs stats, and the two generated files `regenerate` compares (`roadmap.md`, `roadmap-context.md`). A path is added only when it exists. Anything else that is gitignored stays out.
2. **A link does not bring an omitted checkout path in.** `Mirror._left_out` is the one rule: a checkout path git ignores, or a nested repository, is not created by `_place` and is not copied when `_copy_dir` walks a directory a link did place (the skipped `work/` directory). A symlink to a nested repository stays a symlink; `(path / ".git").exists()` follows links, so the link itself is not treated as the repository. There is no report line. A target outside the checkout is still copied whole, which is the containment rule.
3. **`changed_since` no longer treats every ignored path as a checkout edit.** It compares paths the mirror read, then walks only far enough to see a new non-ignored path. Ignored directories that hold nothing the mirror read are not entered. `check-ignore` and `ls-files` pass `-c core.fsmonitor=` so those calls do not run the caller's fsmonitor. The dry run passes the caller's environment, with `GIT_` variables removed, into those two commands only, so `core.excludesFile` applies. `git init`, `add` and `commit` in the copy still use the scratch environment. The dry-run global-config test still requires the fsmonitor marker to stay empty.
4. **The validation copy is a snapshot of the plan mirror, taken before the refresh.** `snapshot_outside` drops `.git` and keeps an unreadable file as an empty file of the same mode, which is what `Mirror._copy_file` already does. `reuse` retargets absolute symlinks from the plan mirror's `outside` to the validation copy's, then `git init`s. The dry run still has two inits (plan mirror, validation copy); the second init is not a second walk of the checkout.
5. **`build_without_git` in `tests/test_upgrade_preview.py` now accepts the new `build` keywords.** The assertion is unchanged: a mirror whose `.git` was removed still exits 2 with `git init failed in the temporary copy`. The dry run checks that immediately after `build`, because the validation copy's init is a separate call the wrapper does not see.

## Known limits, left as they are

- An excludes rule that exists only in a `GIT_` variable is ignored on both paths. Upgrade strips those variables before any git call, including the file selection. A `core.excludesFile` in the caller's gitconfig is read.
- `work/` is still not copied by the walk. A symlink to it copies that directory, and `_left_out` then drops ignored children. A non-ignored file inside `work/` is copied.
- A link whose target is outside the checkout is still copied whole. The checkout's ignore rules do not apply there.
- An untracked roadmap manifest or chunk hidden by a `.gitignore` rule is not copied, so `--dry-run` can fail where the real run passes (gpt-6.1-sol R1). This is the maintainer-accepted limit in the planning sheet (2026-11-07, `## Accepted limits`); it is a false failure, not a false pass, and is left unchanged.

## Changes

- `specy_road/bundled_scripts/upgrade_plan.py`: selected copy, reuse, `changed_since`.
- `specy_road/bundled_scripts/upgrade.py`: the extra paths, and a dry run that builds once.
- `tests/test_upgrade_preview.py`: the two acceptance tests, and the `build` wrapper's signature.
- `specy_road/sibling_repos.py` (added to the zones in round 3): `walk()` skips a child whose `.git` check raises `OSError`.
- `docs/upgrading.md`, `CHANGELOG.md`.

**Final touch zones:** `specy_road/bundled_scripts/upgrade_plan.py`, `specy_road/bundled_scripts/upgrade.py`, `tests/test_upgrade.py`, `tests/test_upgrade_preview.py`, `docs/upgrading.md`, `CHANGELOG.md`, `specy_road/sibling_repos.py`. `tests/test_upgrade.py` needed no edit. Call sites outside the zones (`tests/test_upgrade_parity.py`, `tests/test_upgrade_plan_parity.py`, `tests/test_upgrade_work_templates.py`, and the other upgrade importers) were not edited; the parity and work-template modules pass.

## Verification

- `pytest -n 4` on `tests/test_upgrade.py`, `tests/test_upgrade_preview.py`, `tests/test_upgrade_parity.py`, `tests/test_upgrade_plan_parity.py`, `tests/test_upgrade_work_templates.py`, `tests/test_agents_md_report.py`, `tests/test_setup_writers_refuse_links.py`, `tests/test_skill_mirrors.py`: 330 passed with `tests/test_sibling_repo_approvals.py` (round 3).
- `ruff check specy_road tests scripts`: passed.
- `specy-road file-limits`: OK. `tests/test_upgrade_preview.py` is 839 lines, over the soft alert and under the 1,000-line cap. The other warnings are pre-existing files.

## Probes

- R1, symlink to an ignored file: `env-link -> .env` on a real run and a dry run. The temp directory, listed while it exists, has the link and not `.env`; no copied file contains `SECRET=1`. Result: held.
- R1, symlink to an ignored directory: `modules-link -> node_modules`. The name `node_modules` is absent and no copied file contains `module.exports`. Result: held.
- R1, symlink to a nested repository: `nested-link -> vendor/other`. The link is in the copy, `vendor/other` is not, and `nested-secret` is not in any copied file. A first cut dropped the link itself (`(path / ".git").exists()` follows symlinks) and the dry run then reported `nested-link` as a checkout edit. Keeping the link and omitting the target fixes both. Result: held.
- R1, the other placement path: `_copy_dir` of the skipped `work/` directory when `work-link` points at it. `work/.env` (gitignored) was copied before the guard and is not copied after; `work/note.txt` is. Result: held.
- R1, ignored file the refresh reads: `CLAUDE.md` gitignored, dry run. `validate` on the copy still sees the user's text and the refreshed block. Result: held. The path is an extra, so `_left_out` never has to place it.
- R2, global `core.excludesFile`: `secret.env` listed in a file named from `HOME/.gitconfig`, both paths. The temp directory has `keep-me.txt` and not `secret.env`, and no copied file contains `GLOBALSECRET=1`. Result: held.
- R2, scratch isolation: the existing global-config test, fsmonitor marker and `specy.probe`, dry run and real run. The dry-run marker is empty and the copy's validate probe is unset; the real run's marker lines are the checkout path. Result: held.
- R3, ignored current digest: upgrade once, append `roadmap-context.md` to `.gitignore`, `git check-ignore` matches, bytes equal `render_digest`. Dry run does not print `would write roadmap-context.md` and prints `generated files already current`. The real run does not print `wrote roadmap-context.md` and the bytes are unchanged. Result: held.
- R3, the other generated name: `roadmap.md` is in the same `GENERATED_COMMITTED` tuple, so an ignored untracked `roadmap.md` is copied too. `regenerate` writes it only when the checkout tracks it, which `ls-files` already copies. Result: no separate failure path.
- Round 2, class: a directory that cannot be searched. `(path / ".git").exists()` raises `PermissionError`, and creating the directory makes `snapshot_outside`'s `copytree` raise `shutil.Error` when it lists it. One predicate, `_skipped_dir`, is what `_walk`, `_appeared`, `_left_out`, `_under_nested` and `_without_skipped` use. Result: the directory is not created.
- Round 2, `_walk` before `mkdir`: mode-000 `private/` on a real run and a dry run. The temp directory has `private-link` and `keep-me.txt`, not `private`, and no copied file contains `NOSEE`. Result: held.
- Round 2, `_left_out` through a link: `private-link -> private`. The link is copied and the target is not. Result: held.
- Round 2, `_appeared` and `snapshot_outside`: the dry run exits 0, so the directory is not reported as a checkout edit and the validation copy's `copytree` does not list it. Result: held.
- Round 2, the same class outside the copy: a real `run_upgrade` raised `PermissionError` on the checkout's `private/.git` from `specy_road/sibling_repos.py`, after the copy had finished. Result: stopped, named for the coordinator.
- Round 3, `sibling_repos.walk`: the `.git` check is now inside `try/except OSError` and the child is skipped, the same answer as `_skipped_dir`. `is_repo_top` runs only after that check succeeds, and `walk`'s own `iterdir` was already guarded. A standalone `sibling_repos()` on a repo with mode-000 `private/` raised before and returns now. Result: held.
- Round 3, real run: `test_an_unsearchable_directory_is_left_out_of_the_mirror[False]` now requires exit 0; with `sibling_repos.py` reverted it fails (red), with the fix it passes. Result: held.
- Round 3, other `(path / ".git").exists()` callers in `specy_road/` (`agent_ignores`, `schema_revision`, `worktree_env`, `review_files`, `worktree_delete_set`): they check the git root or its parents, not child directories of the checkout, so an unsearchable checkout subdirectory does not reach them. Result: not in this class, unchanged.
- R1 (gpt-6.1-sol), ignored roadmap JSON: maintainer-accepted limit in the planning sheet; no change.

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
- `Mirror._left_out`: the omission rule for a link target. A checkout path git ignores, or a nested repository, is not created. A path outside the checkout is not omitted. Replaces the report line, which copied the secret and then said so.
- `_skipped_dir`: one answer for a real directory the copy does not enter. It contains `.git`, or listing it raises. A symlink is not that directory. `_walk` uses it before `mkdir`, so an unsearchable directory is never in the tree `snapshot_outside` copies. `_appeared`, `_left_out`, `_under_nested` and `_without_skipped` use the same answer.
- `try/except OSError` around the `.git` check in `sibling_repos.walk`: an unsearchable child is skipped, so `validate` in a real upgrade does not stop on it.
- `_copy_dir` skips a child `_left_out` rejects: a link to `work/` was the other way an ignored file entered.
- `_without_skipped` keeps a symlink whose target contains `.git`: the link is not the nested repository.
- `_ensure` makes the alias symlink only when the target was actually placed: otherwise it would create the omitted path as a self-link.
- Dry-run `build(git_env=caller_env)`: file selection reads `core.excludesFile`; the copy's git commands do not.
- `GENERATED_COMMITTED` in `_mirror_extras`: `roadmap-context.md` and `roadmap.md` are in the validation copy when they exist, so a current ignored digest is not a predicted rewrite.
- `if not (mirror.repo / ".git").is_dir()` in `_dry_run`: the existing no-`.git` failure still fires on the plan mirror.
- `_present`, `_recorded_paths`, `_skill_paths`, `_mirror_extras`: the paths the refreshes read, copied even when git ignores them.
- `-c core.fsmonitor=` on `ls-files` and `check-ignore`: those calls must not run the caller's fsmonitor (decision 3).
- `changed_since` no longer walks every ignored path: an ignored file the mirror did not read is not a "dry run modified" hit.

Tests:

- `test_ignored_secrets_and_a_nested_repo_stay_out_of_the_mirror`: lists the temp directory while it exists, on both paths; an ignored `.env`, `node_modules`, and a nested repo are absent, including through `env-link`, `modules-link` and `nested-link`; the secret text is absent; an untracked `keep-me.txt` and `AGENTS.md` are present; the dry run prints the copy line once.
- `test_a_global_excludes_file_keeps_a_secret_out_of_both_mirrors`: a `core.excludesFile` in the caller's gitconfig keeps `secret.env` out of both temp directories.
- `test_an_ignored_current_digest_is_not_predicted_as_a_rewrite`: an ignored `roadmap-context.md` that matches the roadmap is not a `would write` and not a `wrote`.
- `test_an_unsearchable_directory_is_left_out_of_the_mirror`: a mode-000 directory and a link to it stay out of both temp directories, and both the real run and the dry run exit 0.
- `test_large_ignored_content_does_not_change_the_plan`: the dry-run plan with a 1MB ignored tree and a secret equals the plan without them.
- `build_without_git` forwards `build`'s new keywords so the existing no-`.git` assertion still runs (decision 5).

Mocks: none.
