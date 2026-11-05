# Implementation summary: M21.10 doctor works in a repo with no remote

## What changed

- `specy_road/bundled_scripts/doctor.py`: before fetching, `cmd_doctor` calls `_no_remote_sections`, which resolves the remote with `resolve_integration_defaults` (the resolver `fetch_integration` uses) and runs `git remote get-url`. If that fails inside a repository, doctor prints the resolver's warnings and one stdout line naming the remote and what was skipped, and the only section is the stashes. The listing, `--fix` and orphaned-claim code below it are shared with the normal path, so `--fix` can only touch the listed stashes. Exit is `int(bad_config)`, or 1 when `--fix` fails on a stash.
- A configured remote goes through `_context` and `fetch_integration` unchanged, so `git fetch --prune <remote> failed` still exits 1. `branches prune` is untouched.
- "Nothing to tidy" on the no-remote path reads `Nothing to tidy: no toolkit stash.`, because the full sentence would claim branch, worktree and registry checks that did not run.
- `tests/test_doctor.py`: one table-driven test, local git only, no private patch.
- `CHANGELOG.md`: `[Unreleased]` Fixed entry.

## Touch zones

Confirmed, final list: `specy_road/bundled_scripts/doctor.py`, `tests/test_doctor.py`, `CHANGELOG.md`. No new module was needed.

## Decisions a reviewer should check

- **Not a git repository.** `git remote get-url` also fails there, which would have turned doctor's exit 1 into exit 0 with a "no remote" line. `test_doctor_emits_the_skew_warning` (outside the zones) requires a non-zero exit in a non-repository, so the skip needs a repository (`git rev-parse --git-dir`) and a non-repository keeps the old fetch error. This is narrower than the literal A1 wording only for that case; every failure of `get-url` inside a repository skips.
- **Checkout-error row.** It uses a failing `env_setup`, not the review-gate mismatch: that is a checkout error `report_checkout` reports without needing the integration branch.
- **Test size.** The active cap is `sr/constraints/file-limits.yaml` (400 lines), not the root `constraints/file-limits.yaml` (1000). `tests/test_doctor.py` is 399 lines, so the table is compact, and the test adds about +45 lines against the +60 estimate.
- **Resolver precedence.** Rows cover `--remote` and `SPECY_ROAD_REMOTE` naming an absent remote while `origin` exists. There is no row for a `git-workflow.yaml` remote other than `origin`, which was dropped to stay under the cap; the resolver call is the same one.
- **Docs not changed.** `docs/git-workflow.md:357` says "A failed fetch stops `doctor`", which is still true, but the file does not mention the no-remote skip. It is outside the touch zones, so a follow-up could add it. The `--help` text is also unchanged.

## Verification

- `python -m pytest -n 4 -q`: 5022 passed.
- `specy-road file-limits`: OK.
- Without the fix, 7 of the 9 rows fail; the two configured-remote rows pass, as they should (behaviour unchanged).
- By hand: `git init`, `init project`, commit, `doctor --repo-root <dir>` exits 0 with the skip line.

## Added

- `doctor._no_remote_sections`: detects the missing remote and prints the skip line, keeping `cmd_doctor` under the function cap.
- `doctor._stash_section`: the stash section, shared by `_sections` and the no-remote path.
- Guard `git rev-parse --git-dir` in `_no_remote_sections`: a non-repository keeps its existing fetch error (see above).
- Branch `for w in warns` in `_no_remote_sections`: `fetch_integration` is skipped on this path, so its warnings would otherwise be lost.
- Local `clean` in `cmd_doctor`: the "Nothing to tidy" text must not claim checks that were skipped.
- Local `root` in `cmd_doctor`: `ctx` does not exist on the no-remote path, and the orphaned-claim report needs the root.
- Test `test_doctor_without_a_remote_reports_what_needs_none`: A3's table, plus `--remote` and env rows for A1's precedence.
- Test helpers `_toolkit_stash`, `_failing_env_setup`, `_bare_origin`: setup for the table's rows.
- Mocks: none.

## Merge with the integration line

Merged `origin/WIP/improvements-0-3-1` to resolve the `cmd_doctor` conflict with M16.69: `_print_cursor_force(root)` runs right after `report_unpushed(root)`, before the remote check, so its advisory also appears with no remote. No M21.10 behaviour changed.
