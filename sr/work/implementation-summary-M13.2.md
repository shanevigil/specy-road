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
- `_preview_files(checkout, project)`: `{path in the preview tree: regular source file}`. Sources are git's tracked and unignored files, `.specyrd/`, and `_block_previews`' managed-block files. Every link is followed to its content (fix round 1, F1/F2).
- Fallback to `rglob` when `git ls-files` fails: a project outside git still gets a copy (A2).
- `os.walk(followlinks=True)` with a realpath `seen` set: materializes a link to a directory without looping on a link cycle (F1).
- `_copy_checkout(files, dest)`: writes the materialized files with `copy2`, so the preview tree holds no links (F1).
- `_fingerprint(checkout, files)` plus the before/after compare in `_dry_run`: the hard guard. It takes `git --no-optional-locks status --porcelain=v1 -z --ignored` and a sha256 of every preview input. If either changed, it prints `dry run modified <paths> …; this is a bug` and exits 2 (F1).
- `git init` / `add` / `commit` of the copy with an inline identity, gpgsign off and `--no-verify`: validate's touch-zone and ignore checks read git, and without one commit it would report notices the real run does not.
- `_dry_run(project, checkout, prune)`: the preview listing, then the copy, refresh, line caps and validate. Exits with validate's code (A2).
- `contextlib.redirect_stdout/stderr` around the refresh on the copy: avoids printing every refresh line twice.
- `shlex.quote` on the worktree path in the printed `cd` (F3).
- `_other_worktrees(checkout)` / `_print_other_worktrees(checkout)`: the A6 listing. Skips bare entries and this worktree; a detached worktree is shown as `detached at <sha>`.
- Test `test_header_names_the_install_and_a_dry_run_says_it_previews` (A1).
- Test `test_dry_run_exits_with_a_validate_error_only_the_refreshed_copy_raises`: a monkeypatched `validate_at` fails only when a file that only the refresh writes is present. Asserts exit 1, that validate ran on a since-removed temp directory outside the checkout (the call count is not pinned, per F5), and that checkout files and `git status` are unchanged (A2).
- Mock: `monkeypatch.setattr(upgrade, "validate_at", ...)` injects the new version's validate error (A2). It also captures the copy's CLAUDE.md (F2) and writes into the checkout to trip the guard.
- `tests/upgrade_repo_helpers.py`: public `old_repo`, `OLD_STUB` and `SHIPPED_DOC`, moved out of `tests/test_upgrade.py` so no test imports another module's private helper (F4).
- Test `test_dry_run_never_writes_through_a_link_into_the_checkout`: a schema linked through an external alias of the same checkout. Checkout bytes and `git status --ignored` are unchanged (F1).
- Test `test_dry_run_validates_an_ignored_claude_md_with_its_text_and_the_refreshed_block`: validate on the copy sees the developer text plus `@.specyrd/AGENTS.md`, and the checkout's CLAUDE.md is unchanged (F2).
- Test `test_a_dry_run_that_touches_the_checkout_fails_as_a_bug`: a write into the checkout during the preview exits 2 and names the path (F1 guard).
- Test `test_a_file_the_upgrade_pushes_over_its_cap_is_named`: dry run and real run, with old/new counts and the cap (A3).
- Test `test_a_file_already_over_its_cap_is_not_blamed_on_the_upgrade`: reported once as "already over", never "pushed over" (A3).
- Test `test_a_fresh_project_does_not_cap_the_root_agent_files`: 1000-line root AGENTS.md/CLAUDE.md are not collected and the scan passes; `planning/README.md` is still capped; the opt-in comment is present (A4).
- Test `test_other_worktrees_are_named_as_not_upgraded`: a linked worktree on `feature/x`, at a path containing a space, is pinned by exact line. The printed `cd` is run in bash and lands in that worktree (A6, F3).
- Assertion in `test_dry_run_writes_nothing_and_validates_a_copy`: no other-worktrees section with a single worktree (A6).

## Fix round 1 (Sol F1–F5)

The base was merged with `origin/WIP/improvements-0-3-1` (`64badf7b`); the fix is commit `14408a04`.

- **F1:** the preview tree is built by construction from regular files only. `_preview_files` follows every link to its file or directory content, and `_copy_checkout` writes bytes, never a link. A hard guard fingerprints the checkout before and after the preview. On any change it exits 2 with `error: dry run modified <paths> in <checkout>; this is a bug in specy-road upgrade`. The guard uses `git --no-optional-locks status` and reads files, so it writes nothing.
- **F2:** the managed-block files come from `refresh_stubs._block_previews` itself, run against a scratch temp dir, so no second list exists. Files git ignores are copied.
- **F3:** the worktree path in the printed `cd` is `shlex.quote`d.
- **F4:** the shared setup is now in `tests/upgrade_repo_helpers.py`.
- **F5:** the `len(validated) == 1` assertion is gone.

Red-green: with `upgrade.py` from `42b807dd`, the four new or extended tests fail. The F1 test reproduces Sol's overwrite of `schema-storage/roadmap.schema.json`. All four pass with the fix.

Verification: `pytest -q tests/test_upgrade.py tests/test_upgrade_preview.py tests/test_skill_mirrors.py tests/test_init_project.py` → 28 passed. `specy-road file-limits` → OK (`upgrade.py` is 358 lines). As instructed, the full suite was not rerun.

## Fix round 1: isolation audit

Paths the preview copies, then refreshes in the copy:

| Kind | Example | How isolation holds |
|---|---|---|
| regular, tracked or untracked-unignored | `roadmap/**`, `constraints/file-limits.yaml`, `AGENTS.md` | `copy2` writes new bytes under the temp dir; the refresh opens only paths under the temp dir. |
| symlink to a file inside the checkout (relative, or absolute via an alias) | `schemas/roadmap.schema.json -> ../alias/schema-storage/…` | Materialized: the temp path is a regular file holding the target's bytes. Writing it replaces the temp file only. Covered by `test_dry_run_never_writes_through_a_link_into_the_checkout`. |
| symlink to a file outside the checkout | a shared `schemas/` file elsewhere | Same: content copied, link not kept. The external file is only read. |
| symlink to a directory (inside or outside) | `.cursor/skills -> ../.agents/skills`, an external schemas dir | Walked with `followlinks=True`; each file is materialized under the link's path in the temp tree, with a realpath set against cycles. No temp directory is a link. |
| broken symlink | — | Skipped (neither file nor dir); the refresh in the copy sees it as absent. |
| ignored managed-block file | `CLAUDE.md`, `AGENTS.md`, `.specyrd/AGENTS*.md`, `.gitignore`, `.cursorindexingignore` | Selected by `_block_previews`, whose writes go to its own scratch temp dir, so it is included regardless of ignore rules. Materialized like any other file. Covered by the ignored CLAUDE.md test. |
| `.specyrd/` (any, including ignored local files) | `.specyrd/manifest.json`, `.specyrd/AGENTS.local.md` | Walked and materialized. |
| new files the refresh creates | `schemas/orchestration.schema.json`, `.agents/skills/*`, `docs/*` | Created under the temp project because every parent is a real temp directory. |
| excluded | `.git/`, the project's `work/` | Never copied; the copy gets its own `git init` and one commit. |

Writes that could still reach the checkout: none by construction. As a backstop, the fingerprint guard (status including ignored, plus a hash of every input) fails the run with exit 2. Covered by `test_a_dry_run_that_touches_the_checkout_fails_as_a_bug`.

Printed commands in `specy-road upgrade` output:

- `cd <shlex-quoted path> && specy-road upgrade` (other worktrees). Copy-runnable; the test runs the `cd` with a path containing a space.
- Next steps: `git diff`, `git status`, `specy-road digest`, `specy-road export`, `specy-road sync`. These contain no paths and are copy-runnable.
- From reused modules, unchanged by this leaf:
  - `which -a specy-road` and `pipx install specy-road` / `uv tool install specy-road` (version_skew): no paths, copy-runnable.
  - `specy-road refresh-profiles --profiles all` (refresh_profiles): copy-runnable.
  - `run: specy-road digest` (digest): copy-runnable.
  - `specy-road edit-node <NODE_ID> --set touch_zones=<paths>` (validate notice): a template with placeholders, not meant to run verbatim.
- **Not fully copy-runnable:** `rm <paths>` from `refresh_stubs._report_orphans`, printed by a non-`--prune` run with old stubs. It joins checkout-relative stub paths unquoted. Today these are toolkit-written names (`.cursor/commands/specyrd-*.md`, with the project prefix). They break only if the project root's path inside the checkout contains a space or a shell character. `specy_road/bundled_scripts/refresh_stubs.py` is outside this leaf's touch zones, so it is left unchanged and flagged here.
