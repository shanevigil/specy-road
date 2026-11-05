# Implementation summary: M13.2

Upgrade previews as the new version, validates in a dry run, and names files it pushed over the line cap.

## Changes

- `specy_road/bundled_scripts/upgrade.py`
  - **A1:** The first line is `specy-road <v> upgrade: <project>`, or under `--dry-run` it is `previewing what specy-road <v> would write: <project>`. It then calls M13.1's `print_install_report()`, which prints the version, `sys.prefix` and every launcher on PATH (reused, not duplicated).
  - **A2:** `--dry-run` still lists the "would write" lines. It then copies the checkout into a `TemporaryDirectory`: git's tracked and unignored files, plus every `.specyrd/` file, without `.git` or the project's `work/`. It `git init`s the copy and commits it once, applies `_refresh(dry_run=False)` there with its output silenced, runs `validate` and `digest --check` on the copy, and exits with validate's code. The checkout is never written.
  - **A3:** `_apply()` records `{path: (lines, cap)}` for every file the project's `constraints/file-limits.yaml` caps, before and after the refreshes. It reads the config the way `file-limits` does: scan root, overlays, gitignore. For each file whose line count changed and is now over its cap, it prints either `this upgrade pushed it over its cap: old -> new lines (cap N)` or `already over its cap before this upgrade (...)`, so a file already over is not blamed. The dry run reports the same on the copy.
  - **A5:** The docstring (which is also `--help`) names `pip install -U`, `pipx upgrade specy-road` and `uv tool upgrade specy-road`. The old line "a new version's digest often differs" now points at validate's notices and `specy-road digest`. The `--dry-run` help text describes the copy validation.
  - **A6:** After writing, it parses `git worktree list --porcelain` the way `doctor._worktrees` does. For each worktree other than this one it prints one line: the path, the branch, "not upgraded; it still has the old managed files while sharing this install", and `Run there: cd <path> && specy-road upgrade`. With a single worktree it prints nothing.
- `specy_road/templates/project/constraints/file-limits.yaml` (**A4**): `exclude_path_globs` is now active with `AGENTS.md` and `CLAUDE.md`. A comment explains that root agent files are developer-owned and that specy-road budgets only its managed blocks and `.specyrd/` files, with a commented example of opting in by deleting them from the list. This repo's own `constraints/file-limits.yaml` is untouched.
- `tests/test_upgrade.py`: `test_dry_run_writes_nothing_and_skips_validate` asserted the behaviour A2 replaces. It is now `test_dry_run_writes_nothing_and_validates_a_copy`, which asserts that validate ran, the checkout files and `git status --porcelain` are unchanged, and no other-worktrees section appears with one worktree.
- `tests/test_upgrade_preview.py`: new tests for A1–A4 and A6.

Touch zones: confirmed accurate. `specy_road/file_limits_engine.py` was not changed; upgrade.py uses its public helpers (`collect_tracked_files`, `build_overlay_match_sets`, `resolve_limits`, `line_count`). No file went over a cap: upgrade.py is 315 lines and `specy-road file-limits` passes.

## Verification

- `pytest -q tests/test_upgrade.py tests/test_upgrade_preview.py`: 13 passed.
- `pytest -q -n 4`: 3994 passed.
- `specy-road file-limits`: OK. `specy-road validate` and `export --check` on the dogfood fixture: OK. `ruff check` on the changed files: clean.
- Red-green: with HEAD's `upgrade.py` restored, 5 of the 6 tests in `tests/test_upgrade_preview.py` fail (exit 1). The template test passes there because it checks the template, not upgrade.py.

## Added

- `_capped_lines(project)`: `{path: (lines, cap)}` from the project's file-limits config. The before/after snapshot for A3.
- `_report_line_caps(before, after)`: names files newly pushed over their cap, and reports pre-existing overages as "already over" (A3).
- Guard `new <= cap or (rel in before and old == new)`: skips files under their cap and files whose line count the run did not change, so an untouched overage is not reported (A3).
- `_apply(project, checkout, prune)`: the real refresh wrapped in the line-cap snapshot (A3).
- `_copy_checkout(checkout, project, dest)`: the temp copy for the A2 dry-run validate.
- Fallback to `rglob` when `git ls-files` fails: a project outside git still gets a copy (A2).
- Re-pointing absolute symlinks into the checkout: a write through such a link lands in the copy, never in the checkout (A2, "checkout is never written").
- `git init` / `add` / `commit` of the copy with an inline identity, gpgsign off and `--no-verify`: validate's touch-zone and ignore checks read git, and without one commit it would report notices the real run does not.
- `_dry_run(project, checkout, prune)`: the preview listing, then the copy, refresh, line caps and validate. Exits with validate's code (A2).
- `contextlib.redirect_stdout/stderr` around the refresh on the copy: avoids printing every refresh line twice.
- `_other_worktrees(checkout)` / `_print_other_worktrees(checkout)`: the A6 listing. Skips bare entries and this worktree; a detached worktree is shown as `detached at <sha>`.
- Test `test_header_names_the_install_and_a_dry_run_says_it_previews` (A1).
- Test `test_dry_run_exits_with_a_validate_error_only_the_refreshed_copy_raises`: a monkeypatched `validate_at` fails only when a file that only the refresh writes is present. Asserts exit 1, that validate ran on a temp copy, and that checkout files and `git status` are unchanged (A2).
- Mock: `monkeypatch.setattr(upgrade, "validate_at", ...)` injects the new version's validate error (A2).
- Test `test_a_file_the_upgrade_pushes_over_its_cap_is_named`: dry run and real run, with old/new counts and the cap (A3).
- Test `test_a_file_already_over_its_cap_is_not_blamed_on_the_upgrade`: reported once as "already over", never "pushed over" (A3).
- Test `test_a_fresh_project_does_not_cap_the_root_agent_files`: 1000-line root AGENTS.md/CLAUDE.md are not collected and the scan passes; `planning/README.md` is still capped; the opt-in comment is present (A4).
- Test `test_other_worktrees_are_named_as_not_upgraded`: a linked worktree on `feature/x` is pinned by exact line (A6).
- Assertion in `test_dry_run_writes_nothing_and_validates_a_copy`: no other-worktrees section with a single worktree (A6).
