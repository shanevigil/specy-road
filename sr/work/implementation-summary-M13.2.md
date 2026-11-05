# Implementation summary: M13.2

Upgrade previews as the new version, validates in a dry run, and names files it pushed over the line cap.

## Changes

- `specy_road/bundled_scripts/upgrade.py`
  - **A1:** The first line is `specy-road <v> upgrade: <project>`, or under `--dry-run` it is `previewing what specy-road <v> would write: <project>`. It then calls M13.1's `print_install_report()`, which prints the version, `sys.prefix` and every launcher on PATH (reused, not duplicated).
  - **A2:** `--dry-run` lists the same write plan the real run writes (see "Fix round 3: one plan"). It writes that plan into a temporary mirror of the checkout, commits the mirror once in its own git repo, runs `validate` and `digest --check` there, and exits with validate's code. The checkout is never written.
  - **A3:** `_apply()` records `{path: (lines, cap)}` for every file the project's `constraints/file-limits.yaml` caps, before and after the refreshes. It reads the config the way `file-limits` does: scan root, overlays, gitignore. For each file whose line count changed and is now over its cap, it prints either `this upgrade pushed it over its cap: old -> new lines (cap N)` or `already over its cap before this upgrade (...)`, so a file already over is not blamed. The dry run reports the same on the copy.
  - **A5:** The docstring (which is also `--help`) names `pip install -U`, `pipx upgrade specy-road` and `uv tool upgrade specy-road`. The old line "a new version's digest often differs" now points at validate's notices and `specy-road digest`. The `--dry-run` help text describes the copy validation.
  - **A6:** After writing, it parses `git worktree list --porcelain` the way `doctor._worktrees` does. For each worktree other than this one it prints one line: the path, the branch, "not upgraded; it still has the old managed files while sharing this install", and `Run there: cd <path> && specy-road upgrade`. With a single worktree it prints nothing.
- `specy_road/templates/project/constraints/file-limits.yaml` (**A4**): `exclude_path_globs` is now active with `AGENTS.md` and `CLAUDE.md`. A comment explains that root agent files are developer-owned and that specy-road budgets only its managed blocks and `.specyrd/` files, with a commented example of opting in by deleting them from the list. This repo's own `constraints/file-limits.yaml` is untouched.
- `tests/test_upgrade.py`: `test_dry_run_writes_nothing_and_skips_validate` asserted the behaviour A2 replaces. It is now `test_dry_run_writes_nothing_and_validates_a_copy`, which asserts that validate ran, the checkout files and `git status --porcelain` are unchanged, and no other-worktrees section appears with one worktree.
- `tests/test_upgrade_preview.py`: new tests for A1–A4 and A6.

Touch zones: confirmed accurate. `specy_road/file_limits_engine.py` was not changed; upgrade.py uses its public helpers (`collect_tracked_files`, `build_overlay_match_sets`, `resolve_limits`, `line_count`). No file went over a cap. `specy-road file-limits` passes.

**Modules, outside the listed zones:** fix round 3 deletes `specy_road/bundled_scripts/upgrade_preview.py` and adds `specy_road/bundled_scripts/upgrade_plan.py` (266 lines) and `tests/test_upgrade_plan_parity.py` (188 lines). Please swap `upgrade_preview.py` for `upgrade_plan.py` in this leaf's touch zones (`sr/roadmap/phases/M13.json`, `sr/roadmap/registry.yaml`), and add the test file if `tests/test_upgrade*.py` does not already cover it. `upgrade.py` is 319 lines.

## Verification

- `pytest -q tests/test_upgrade.py tests/test_upgrade_preview.py`: 13 passed.
- `pytest -q -n 4`: 3994 passed.
- `specy-road file-limits`: OK. `specy-road validate` and `export --check` on the dogfood fixture: OK. `ruff check` on the changed files: clean.
- Red-green: with HEAD's `upgrade.py` restored, 5 of the 6 tests in `tests/test_upgrade_preview.py` fail (exit 1). The template test passes there because it checks the template, not upgrade.py.

## Added

Round 3 removed these entries' code: `preview_files`, `copy_tree`, `fingerprint`, `changed_paths`, `snapshot_declined`, `restore_declined`, the `rglob` fallback, the `os.walk(followlinks=True)` materializing and the `contextlib` redirect in `_dry_run`. They are kept below as history. What replaces them is under "Fix round 3: one plan".


- `_capped_lines(project)`: `{path: (lines, cap)}` from the project's file-limits config. The before/after snapshot for A3.
- `_report_line_caps(before, after)`: names files newly pushed over their cap, and reports pre-existing overages as "already over" (A3).
- Guard `new <= cap or (rel in before and old == new)`: skips files under their cap and files whose line count the run did not change, so an untouched overage is not reported (A3).
- `_apply(project, checkout, prune)`: the real refresh wrapped in the line-cap snapshot (A3).
- `preview_files(checkout, project)` (now in `upgrade_preview.py`): `{path in the preview tree: regular source file}`. Sources are git's tracked and unignored files, `.specyrd/`, and `_block_previews`' managed-block files. Every link is followed to its content (fix round 1, F1/F2).
- Fallback to `rglob` when `git ls-files` fails: a project outside git still gets a copy (A2).
- `os.walk(followlinks=True)` with a realpath `seen` set: materializes a link to a directory without looping on a link cycle (F1).
- `copy_tree(files, dest)` (`upgrade_preview.py`): writes the materialized files with `copy2`, so the preview tree holds no links (F1).
- `fingerprint(checkout, files)` and `changed_paths(before, after)` (`upgrade_preview.py`), plus the compare in `_dry_run`: the hard guard. It takes `git --no-optional-locks status --porcelain=v1 -z --ignored` and a sha256 of every preview input. If either changed, it prints `dry run modified <paths> …; this is a bug` and exits 2 (F1).
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

- `_DECLINED` and the return value of `_refresh`: the checkout-relative paths the refresh refused, skipped or failed to write. They come from its own reported outcomes plus `copy_missing_docs`' refusals (round 2).
- `declined=` keyword on `copy_missing_docs`: reports a doc refused for a link out of the repository (round 2).
- `snapshot_declined(copy, declined)` / `restore_declined(copy, kept)` (`upgrade_preview.py`): put the declined paths back in the copy after the preview refresh. This keeps preview/real parity (round 2).
- `PermissionError` branch in `copy_tree`: an unreadable source becomes an empty file with the same mode in the copy, so every reader fails alike (round 2).
- `--ignore-errors` on the copy's `git add`: one unreadable file must not leave the copy with no commit (round 2).
- `_block_previews` against an empty root: gets the managed-block file names without reading the checkout; reading it crashed the preview on an unreadable `AGENTS.md` (round 2).
- `tests/test_upgrade_parity.py`: three dry-then-real parity tests under one injected validator (round 2):
  - an external `AGENTS.md` link (Sol's regression);
  - an `AGENTS.md` link inside the repo;
  - an unreadable `AGENTS.md`.

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
| ignored managed-block file | `CLAUDE.md`, `AGENTS.md`, `.specyrd/AGENTS*.md`, `.gitignore`, `.cursorindexingignore` | Selected by `_block_previews`, which since round 2 runs against an empty root and writes only to scratch temp dirs, so it is included regardless of ignore rules. Materialized like any other file. Covered by the ignored CLAUDE.md test. |
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

## Fix round 2 (Sol F1, A2): preview/real parity

The base was merged with `origin/WIP/improvements-0-3-1`; the fix is commit `8e1174e2`.

The dry run now makes the same refuse/skip/write decision for each path as the real run:

1. **The decision is made once, on the real checkout, by the real refresh's own predicates.** The listing phase runs the real refreshes with `dry_run=True` on the checkout. `_refresh` now returns every path whose reported outcome starts with `refused`, `skipped` or `failed`, plus the docs `copy_missing_docs` refuses. Those outcomes come from `managed_block.resolves_outside` / `_write`, `specyrd_skills.ensure_link`, `refresh_stubs._write_if_changed` and `apply_managed_block`'s read failure.
2. **That set is passed into the preview.** Before the preview refresh, `snapshot_declined` records each declined path's bytes in the copy, or that it is absent. After the refresh, `restore_declined` puts exactly those paths back. Their end state in the copy is therefore what the real run leaves: not refreshed.
3. **Materializing never changes whether a path is refreshed.** Paths the real run writes are left as the preview refresh wrote them. Paths it declines are undone. Materialization can only remove refusals, never add one, because the copy has no links. So these two cases cover every path.

Red-green: with `upgrade.py` from `08c54ec5`, the external-link case returns dry `(0, no error)` against real `(1, error)`, Sol's finding. The unreadable case raises `PermissionError` in the dry run only. Both pass with the fix.

Verification: `pytest -q tests/test_upgrade_parity.py tests/test_upgrade_preview.py tests/test_upgrade.py tests/test_skill_mirrors.py tests/test_init_project.py` → 31 passed. `specy-road file-limits` → OK. As instructed, the full suite was not rerun.

## Fix round 2: preview/real parity

| Path kind | Real run decision | Preview decision | Test |
|---|---|---|---|
| regular file (tracked or untracked) | written when the refresh changes it | written (same refresh code on a byte copy) | `test_upgrade.py::test_dry_run_writes_nothing_and_validates_a_copy`, `test_upgrade_preview.py::test_a_file_the_upgrade_pushes_over_its_cap_is_named` |
| symlink in (resolves inside the checkout; for a managed block, inside its own directory) | written through the link | written (materialized file); not in the declined set | `test_upgrade_parity.py::test_agents_md_linked_inside_the_repo_is_refreshed_in_both`, `test_upgrade_preview.py::test_dry_run_never_writes_through_a_link_into_the_checkout` (schema via alias, written through) |
| symlink out (managed block, skill or doc whose path resolves outside the repo or out of its own directory) | refused (`refused: a symlink leads outside the repository`) or skipped | refused: the path is in the declined set, so its pre-refresh copy is restored | `test_upgrade_parity.py::test_agents_md_linked_out_of_the_repo_is_refused_in_the_preview_too` (both exit 1 with the same error) |
| ignored managed-block file (e.g. `CLAUDE.md` in `.gitignore`) | refreshed | refreshed: copied regardless of ignore rules via `_block_previews`' selection | `test_upgrade_preview.py::test_dry_run_validates_an_ignored_claude_md_with_its_text_and_the_refreshed_block` |
| managed file not ours (exists, never recorded by the manifest) | skipped (`skipped (not ours)`) | skipped: in the declined set, restored | same mechanism as symlink out (shared `skipped` prefix). No dedicated test; the outcome string is the one `_write_if_changed` / `ensure_link` report |
| unreadable managed file | `failed` (the block read raises, caught by `apply_managed_block`) | `failed`: the copy holds an empty file with the same mode 000, so the same read fails; it is also in the declined set | `test_upgrade_parity.py::test_an_unreadable_agents_md_fails_alike_in_both` (same refresh outcome line and same end result in both) |
| refresh-profiles destination under a link | `ValueError`, upgrade exits 1 | the same `ValueError` is raised by the listing phase on the real checkout, before any copy is made | existing behaviour; not a new test |

Known limits, flagged and not changed:

- **Link aliasing inside the repo.** For example, `CLAUDE.md -> AGENTS.md` in the same directory. Both runs refresh both paths, so the decisions match. But in the real run the two blocks land in one file, while the copy holds two separate files. Keeping the link in the copy would break the round-1 rule that the preview tree holds no links.
- **Unreadable files crash validate.** The validate reader `validate_stale_commands.file_unregistered_commands` raises `PermissionError` on an unreadable `AGENTS.md`, in both the real and the dry run. This is pre-existing and outside this leaf's zones.

## Fix round 3: one plan (Sol F1, F2; A2)

The base was merged with `origin/WIP/improvements-0-3-1` (`b850d49b`). The fix is commit `22edc79a`.

**Failure class.** In every round, the preview made a decision the real run makes differently. Round 1 was link isolation, round 2 refusals, and round 3 aliases (F1) and manifest ownership (F2). The cause was that the preview tree had a different shape from the checkout: links were materialized into files. The refresh code therefore saw different inputs, and the preview patched the outcomes afterwards. Round 3 removes that class: the decisions are made once, and both modes write the same result.

**Design** (`specy_road/bundled_scripts/upgrade_plan.py`):

1. `Mirror(checkout, dest, skip=project/work)` copies the checkout under `dest/repo`, without `.git` or `work/`, and **keeps every link**:
   - A relative link keeps its text when it resolves to the mirrored location of its real target. A link that does not (an absolute link, or one that climbs out of the checkout) is re-pointed at that mirrored location.
   - A target outside the checkout is mirrored under `dest/outside/<its real path>`. That location is outside the mirror's repository too, so `resolves_outside` and `ensure_link`'s `os.readlink` comparison decide exactly as on the checkout.
   - Unreadable files stay unreadable (same mode), and directory modes are copied. The mirror is `git init`ed so `git_root` works as on the checkout.
2. `make_plan(checkout, project, refresh)` runs the **real** refreshes (`upgrade._refresh`, which calls `refresh_schemas`, `refresh_profiles`, `copy_missing_docs` and `refresh_stubs`, all with `dry_run=False`) once on the mirror. It diffs the mirror before and after that run; links are not followed in the diff.
   - The refresh prints its own report; `preview` changes only the verb ("would write" / "wrote").
   - Mirror paths in the output, and in an `OSError`'s filename, are shown as the checkout's.
3. `apply_plan(plan, locate)` writes the plan:
   - The real run uses the identity `locate`, after `conflicts(plan)` checks that no target changed since the plan was made. On a conflict it writes nothing and exits 1.
   - The dry run uses `Mirror.to_sandbox` of a second, fresh mirror, then validates it.
   - Order: removals deepest first, then directories shallowest first, then links and file writes.
4. The dry-run guard is `Plan.changed_since()`: the state now of every path the mirror read, plus any new path in the checkout. Any difference exits 2, as before.

**Plan fields** (`Entry`):

- `path`: how the refresh names it (checkout-relative, or absolute outside the checkout).
- `target`: the real path it lands on, links followed.
- `action`: `write` / `link` / `mkdir` / `remove`, or `refuse` / `skip` / `fail` for a path the refresh leaves as it is.
- `data`: the final bytes of a `write`.
- `link`: the final text of a `link`.
- `mode`: the final file mode.
- `before`: the target's state when the plan was made. This is the conflict precondition.

`Plan` also holds `checkout`, `skip` and `states` (every mirrored path's state, for the dry-run guard).

**Former preview-only decisions, removed:**

- Materializing every link into a regular file (`preview_files`, `os.walk(followlinks=True)`, `copy_tree`). This caused F1: two files where the real run has one.
- Choosing what to copy: git tracked/unignored files, plus `.specyrd/`, plus `_block_previews`' block-file names, plus an `rglob` fallback. The mirror now takes everything but `.git` and `work/`, so ignored files are present as on the checkout.
- `snapshot_declined` / `restore_declined`: restoring declined bytes after a refresh that had decided differently. This caused F2: the manifest kept a refused skill.
- The `_DECLINED` set passed from a checkout `dry_run=True` listing into the preview. The listing *is* now the plan run.
- Creating an empty file in place of an unreadable one, in the copy only. The mirror does the same for both modes.
- `fingerprint` / `changed_paths` (sha256 of the preview inputs plus `git status`). Replaced by `Plan.changed_since` over the mirror's own record.
- The dry run's separate `_refresh(dry_run=False)` on the copy, silenced with `redirect_stdout`.

**Behaviour changes for the real run**, from the same design:

- A refresh that raises (`refresh-profiles` under a link, a read-only `docs/`) now raises in the mirror, before anything is written to the checkout. Before, `refresh-schemas` had already written.
- A target that changes between planning and writing is not overwritten.

**Parity tests** (`tests/test_upgrade_plan_parity.py`). Each layout runs dry, then real, on the same checkout under one injected validator that records the whole tree it is given: every file and link, read through the link, with relative link texts, `.specyrd/manifest.json` included, and `.git`/`work/` excluded. The test asserts:

- the dry run left the checkout byte-identical;
- both exits are 0;
- the dry copy's tree equals the real checkout's tree;
- the tree changed, so the comparison is not vacuous.

Layouts:

- `claude-md-aliases-agents-md`: `CLAUDE.md -> AGENTS.md`.
- `canonical-skill-linked-outside`: a manifest-recorded `.agents/skills/specyrd-validate/SKILL.md` linked to a file outside the repo.
- `agents-md-linked-outside`.
- `ignored-claude-md`: `CLAUDE.md` in `.gitignore`.
- `stale-managed-block`: `AGENTS.md` with an old `specy-road` block.
- `nested-project-root`: `init project` into `sr/`.

Sol's injected-validator probes are kept as reported:

- `test_sol_f1_an_alias_fails_the_claude_import_check_in_both`: dry and real both exit 1 with `error: CLAUDE.md has no current import`.
- `test_sol_f2_a_refused_canonical_skill_is_unowned_in_both_manifests`: dry and real both exit 1, and the skill is unowned in both manifests. The outside file is unchanged.

Both also assert that the dry run left the checkout unchanged.

Red-green: with `upgrade.py` and `upgrade_preview.py` from `2f316a45`, 5 of the 8 new tests fail: both Sol tests, and the alias, external-skill and external-AGENTS layouts. The ignored-CLAUDE, stale-block and nested layouts already agreed there; they guard against regressions. All 8 pass with the fix.

Verification: `pytest -q -n 4 tests/test_upgrade.py tests/test_upgrade_preview.py tests/test_upgrade_parity.py tests/test_upgrade_plan_parity.py tests/test_skill_mirrors.py tests/test_init_project.py tests/test_refresh_stubs.py` → 63 passed. `specy-road file-limits` → OK. `ruff check` on the changed files → clean. As instructed, the full suite was not run.

**Cost and limits:**

- The real run now mirrors the checkout too. On this checkout (2,181 paths, 31 MB without `.git`/`work/`) the mirror takes 0.7 s. A large ignored tree (a `.venv`, `node_modules`) is copied as well, because an ignored file can be an input to a refresh decision.
- A directory link to something large outside the checkout is copied as it was in rounds 1–2. A link to an ancestor of the checkout does not copy the checkout twice.

## Probes

Each probe ran dry, then real, on the same repo, through the public `run_upgrade`, under one recording validator (scratch script, not committed). It compared exits, the checkout after the dry run, and the two validated trees.

- `CLAUDE.md -> AGENTS.md` (F1): both exit 1 under Sol's validator, and the trees are equal under the recording one. Fixed (was dry 0 / real 1).
- Recorded canonical skill linked outside (F2): both exit 1, the skill is unowned in both manifests, and the outside file is untouched. Fixed (was dry owned / real unowned).
- `AGENTS.md` linked outside: equal trees, exit 0 with the recording validator; round 2's block validator still gives 1/1.
- `AGENTS.md` linked inside the repo (round 2 test): passes. The link is kept in the mirror, and the block is refreshed through it in both runs.
- Unreadable `AGENTS.md` (round 2 test): passes, with the same `(failed)` line and the same end result.
- Ignored `CLAUDE.md`: equal trees; the copy carries the developer text and the import.
- Stale managed block: equal trees.
- Nested project root `sr/`: equal trees.
- Old stubs with `--prune`: equal trees. Pruned files and the directories they emptied are removed alike.
- `.claude/skills -> ../.agents/skills` directory link with `--prune`: equal trees. The `readlink`/`resolve` checks in `ensure_link` see the same link.
- Schema linked through an external alias of the checkout (round 1 test): equal trees, written through in both, and the dry run leaves the checkout untouched.
- `docs/` linked to a directory outside: equal trees, refused in both, and the outside directory stays empty.
- `model-profiles/` linked outside: the same `ValueError` in both. The real run now writes nothing before raising.
- Read-only `docs/`: the same `PermissionError` in both, naming the checkout's path (not the mirror's). The real run writes nothing.
- A link into the project's `work/` (excluded from the mirror): the target is mirrored on demand, and the trees are equal.
- A link cycle `a <-> b`: the mirror builds and the trees are equal.
- A directory link to an ancestor of the checkout: the mirror builds without copying the checkout twice, and the trees are equal.
- A checkout with no `.git`: the dry run leaves it untouched, and the trees are equal.
- A concurrent edit of `AGENTS.md` between planning and writing: `conflicts(plan)` names it, and the real run writes nothing.
- A dry run that writes into the checkout (existing guard test): still exits 2 and names the path.
- Other importers of the removed module: none (grep). It remains named only in the roadmap zones listed above.

## Fix round 4 (sol-low F1/F2, composer-2.5)

Review at `25631350` blocked on hard links in the mirror and on `len(seen) == 2` in the parity parametrized test.

- **F1 (hard link):** `Mirror._copy_file` tracked `(st_dev, st_ino)` and used `os.link` to the first sandbox path for each inode instead of always `copy2`, so two hard-linked names stay one file in every mirror (dry-run copy included). Layout `agents-md-and-claude-md-hard-linked` and `test_sol_low_f1_hard_linked_agents_and_claude_see_the_same_bytes_in_both` run `run_upgrade` dry then real under a validator that requires equal bytes; both exit 0 and the checkout is untouched by dry-run.
- **F2 (test integrity):** the parametrized parity test records validated trees in separate `dry_trees` and `real_trees` lists (one monkeypatch per run) and asserts `dry_trees[-1] == real_trees[-1]` without pinning how many times `validate_at` runs.

Verification: `pytest -q -n 4 -p no:cacheprovider tests/test_agents_md_report.py tests/test_skill_mirrors.py tests/test_upgrade.py tests/test_upgrade_parity.py tests/test_upgrade_plan_parity.py tests/test_upgrade_preview.py tests/test_init_project.py tests/test_refresh_stubs.py` → 85 passed. `specy-road file-limits --repo-root sr` → OK.

## Probes (fix round 4)

- `os.link(AGENTS.md, CLAUDE.md)` with byte-equality validator (sol-low F1): dry and real both exit 0; checkout unchanged by dry-run. Fixed (was dry 1 / real 0).
- Parametrized parity layouts including new hard-link layout: dry and real trees equal under recording validator; no `len(seen) == 2` assertion. Pass.
- Symlink alias layout and Sol F1/F2 injected validators: unchanged; still pass.
- `Mirror.build()` on a tiny tree with hard-linked files: second name is same inode as first in sandbox (`os.stat` ino match). Pass.

## Added

Fix round 4 only (`none` entries omitted where nothing new was added outside the items below):

- `Mirror._hardlinks` and `build()` clearing it: maps checkout inode to the first copied sandbox path so later paths with the same inode are linked, not copied (sol-low F1).
- Branch in `_copy_file` using `os.lstat` + `os.link` for duplicate inodes (sol-low F1).
- `_hardlink_alias` layout and `agents-md-and-claude-md-hard-linked` in `LAYOUTS`: regression for hard-linked managed files (sol-low F1).
- `test_sol_low_f1_hard_linked_agents_and_claude_see_the_same_bytes_in_both`: public `run_upgrade` dry-then-real under byte-equality validator (sol-low F1).
- Parity test uses separate `dry_trees` / `real_trees` and compares last observations per run (sol-low F2).

## Fix round 5 (sol-low F1 test integrity, composer-2.5)

Review at `fb1677d5` blocked on `owned_seen == [False, False]` in `test_sol_f2_a_refused_canonical_skill_is_unowned_in_both_manifests` (class: **injected-validator observation list length** pinned to exactly two calls).

- **F1:** Replaced the exact two-element list with `assert owned_seen and not any(owned_seen)`, keeping the dry/real exit and error parity and the outside-file byte assertion.

Merged `origin/WIP/improvements-0-3-1` before the fix (merge commit on branch).

Verification: same targeted pytest as round 4 → 85 passed. `specy-road file-limits` → OK.

## Probes (fix round 5)

- Grep `tests/test_upgrade*.py` for `len(...) == N` and `owned_seen == [` call-count pins: only the F2 line above; fixed.
- Parametrized parity test still uses `dry_trees[-1] == real_trees[-1]` without length pin: pass (re-run targeted suite).
- Sol F2 test after change: dry/real `(1, [error…])`, all ownership observations false, outside skill bytes unchanged: pass.

## Added

Fix round 5:

- none (assertion-only change in existing test; no new helpers, guards, mocks or tests)
