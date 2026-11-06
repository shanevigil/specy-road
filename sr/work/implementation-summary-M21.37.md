# Implementation summary: M21.37 — one safe-write rule for the setup and upgrade writers

Branch `feature/rm-safe-write-rule-setup-writers`, base `e3246433`, implementation commit `90cf6e93`.

## What changed

- **`specy_road/safe_write.py` (new, A1).** `check`, `mkdirs`, `write`, `copy`, `remove`, `prune_empty`, `open_lock`, `SafeWriteError(OSError)`, constants `FILE`/`DIRECTORY`. Resolves the root once, takes the path lexically (`normpath`; a `..` that leaves the root is refused), and walks with `lstat`. Every ancestor below the root must be a real directory. The final component depends on the operation (table in the module docstring). Messages use `irregular_destination`'s sentence: `<path> is <kind>[ (to <readlink>)], not <expected>`. `write`/`copy` create the temp file with `O_EXCL` (mode 0o666 less umask, so new files get the same mode `write_text` gave them; a rewrite keeps the file's mode; `copy` keeps mode and times like `copy2`). They re-`lstat` the parent and destination right before `os.replace`. `open_lock` adds `O_NOFOLLOW` where it exists; otherwise the `lstat` refusal of a final link in `check` is the guard.
- **`managed_block`.** `refused_link` returns the rule's refusal (any link; `any_link` is kept for callers but ignored). `apply_managed_block(strict=True)` refuses a link at the path before reading it and writes through `safe_write.write`. A refusal comes back as the outcome `refused: <why>` rather than an exception, because the function never raises. `resolves_outside` is unchanged for its other callers.
- **`agent_ignores`.** Both ignore-file blocks use `strict=True`. `_seed` writes through `safe_write.write`.
- **`init_project` (A2).** `_copy_templates` checks every destination with the rule before the first copy, with or without `--force`, then checks `lexists` (so a dangling link counts as present), then copies with `safe_write.copy`. A new `_scaffold` pre-checks `.gitignore`, `.cursorindexingignore` and `.specyrd/manifest.json`, then runs the old write sequence. `run_init_project` prints `error: <message>` and returns 1. Nothing is written when one of these checks refuses.
- **`refresh_schemas`.** Checks each destination before reading it (dry run included) and writes with `safe_write.copy`. `main` catches `SafeWriteError`.
- **`specyrd_init`.** `_save_manifest` goes through `safe_write.write`. `run_init` calls `_refuse_unsafe_manifest` before anything is written, which prints `error:` and exits 1.
- **`export_roadmap_md`, `digest_cli`, `generated_files`, `do_next_task_register`, `upgrade_generated`.** All write through `safe_write.write`.
  - `export` and `digest` print `error:` and exit 1.
  - `digest` uses the rule for the default output, a relative `-o`, or an absolute `-o` inside the checkout. An explicit absolute `-o` outside the checkout keeps the plain write, and `-` still goes to stdout.
  - `refused_generated_files` now refuses in-repo links.
  - Pickup keeps its tracked-only selection.
  - `regenerate` (upgrade) prints `refused <rel> (<why>)`.
- **`refresh_stubs`.**
  - Write branch: see the deviation below.
  - `_prune` checks every orphan's ancestors before deleting any. It removes a symlink orphan as an entry and cleans up empty parents with `prune_empty`.
  - `main` prints `error: <why>` and exits 1 for a rule refusal (outcome `refused: <why>`, not the old `REFUSED` constant).
- **`upgrade_plan` / `upgrade` (A3).**
  - `refused_changes` and `apply_plan` check every `plan.changes()` entry's `target` with `safe_write.check(plan.checkout, target, None)` before the first mutation. A refusal raises, naming each path, and nothing is applied to the checkout or to the dry run's copy. Declined entries are not checked.
  - `make_plan` rewrites mirror paths in a `SafeWriteError` to the checkout's.
  - `run_upgrade` catches `SafeWriteError` around the dry run and the apply, printing `error:` and returning 1. `main` catches it too.
- **`archive_restore` (A4).** `_preflight` checks, lexically from `root` with no `resolve()`:
  - `record.chunk`, before it is read;
  - each target chunk `roadmap/<rel>`;
  - every planning `stored` and `origin`;
  - `roadmap/manifest.json`, the ledger, and `roadmap/archive/planning/<id>` (as a directory).

  This runs before the first write, move or unlink. A refusal is raised as `ValueError("restore refused, nothing was changed: …")`. `archive_cli` (outside the zones) only catches `ValueError`, so raising that type is what gives `error:` and exit 1 there.
- **Docs and CHANGELOG (A5).** `docs/install-and-usage.md` now says any symlink on the path is refused and that `upgrade` exits non-zero on a refusal even when validate passes. The CHANGELOG `[Unreleased] Fixed` entry records the behaviour change for in-repo links at the generated files.

## Deviations, and the reason for each

1. **`refresh_stubs` stub writes keep `resolves_outside` for the ancestors.** Two outside-zone tests require it:
   - `tests/test_m13_7_notices.py` supports an in-repo symlinked skills directory (`.agents/skills -> ../.claude/skills`).
   - `tests/test_prerelease_files.py` and `tests/test_upgrade_plan_parity.py` require a stub or skills directory linked *out* to stay a per-file `refused: a symlink leads outside the repository` report with exit 0, and the declined skill to drop out of the manifest.

   So the write branch refuses a link out with `REFUSED` as before, then applies the rule from the stub's own directory: a link at the stub itself (in-repo or dangling) is refused with exit 1, and the write is `safe_write.write`. The A5 "stub link" row is covered for an in-repo link (`test_refresh_stubs_refuses_a_linked_stub_and_still_makes_the_skill_links`). A stub linked out is still exit 0, as those tests require.
2. **Ignore-file blocks report a refusal and do not raise.** `tests/test_m13_7_gitignore_symlinks.py` (outside the zones) calls `apply_and_report` with a top-level `.gitignore` symlink and expects it to return. Strict mode therefore returns `refused: <why>` and writes nothing. `init project` gets its `error:` and exit 1 from the `_scaffold` pre-check. `specyrd init` and `refresh-stubs` report the outcome line, and `refresh-stubs` also exits 1.
3. **`run_upgrade` returns 1 on a refusal rather than raising.** `tests/test_upgrade_preview.py::test_dry_run_never_writes_through_a_link_into_the_checkout` calls `run_upgrade` directly and expects an exit code.

## Touch zones

All edits are inside the listed zones. No file outside them needed changing, and no new module beyond `specy_road/safe_write.py` (already listed). `specy-road file-limits` passes.

## Verification

- `pytest -n 8` full suite: 5925 passed.
- `ruff check specy_road tests scripts`, `scripts/check_clones.py`, `scripts/check_test_private_imports.py` and `scripts/check_machine_paths.py`: pass.
- `specy-road validate|export --check|digest --check --repo-root tests/fixtures/specy_road_dogfood` and `specy-road file-limits`: pass.

## Added

- `specy_road/safe_write.py`: the shared rule (A1). Public: `check`, `mkdirs`, `write`, `copy`, `remove`, `prune_empty`, `open_lock`, `SafeWriteError`, `FILE`, `DIRECTORY`. Private helpers: `_kind`, `_refusal`, `_locate`, `_walk`, `_recheck`, `_temp`, `_replace`, `_keep_mode`.
- `managed_block.apply_managed_block(strict=...)` and the strict branch in `_write`: the ignore files go on the rule (A1).
- `init_project._scaffold`: the pre-check of the ignore files and the manifest before any write, split out to keep `run_init_project` under the function cap (A2).
- `specyrd_init._refuse_unsafe_manifest`: refuses a linked `.specyrd/manifest.json` before anything is written, with exit 1 (A2/A3).
- `upgrade_plan.refused_changes`: the `apply_plan` invariant over `plan.changes()` targets (A3).
- `upgrade_plan.make_plan`: a `SafeWriteError` branch that names the checkout's paths rather than the mirror's (A3).
- `upgrade.run_upgrade` and `upgrade.main`: `SafeWriteError` handling (A3).
- `refresh_schemas.main`, `export_roadmap_md._write_export` and `digest_cli.cmd_digest`: `SafeWriteError` → `error:`, exit 1 (A3).
- `refresh_stubs._write_if_changed`: the rule check from the stub's directory (A2).
- `refresh_stubs.main`: exits 1 on a rule refusal (A3).
- `refresh_stubs._prune`: the pre-check pass, `safe_write.remove` and `prune_empty` (A2).
- `archive_restore._preflight`: one lexical pre-check of every restore path (A4).
- `digest_cli`: the branch between "inside the checkout or relative" and "explicit absolute outside" (A2, absolute `-o` decision).
- `tests/test_safe_write.py`: each operation × final kind (absent, file, dir, FIFO, in-repo link, outward link, dangling link), the ancestor kinds, `..` out, the message shape, mkdirs/write parents and mode, prune_empty stops, and a link swapped in before replace (A5). The swap test monkeypatches the public `os.chmod`, the step just before the re-check; no private name is patched.
- `tests/test_setup_writers_refuse_links.py`: one row per entry point (A5):
  - init with and without `--force`: final link out, dangling, `docs/` and `schemas/` parent, in-repo link, `.gitignore` in-repo link;
  - refresh-schemas, upgrade real and `--dry-run`: grok's schema link out, `schemas/` dir link, dangling;
  - `apply_plan` writes nothing to the checkout or to the copy when one change lands outside;
  - specyrd manifest file and dir links;
  - export and digest: final, dangling, in-repo; digest relative `-o` final and parent;
  - pickup with none and one tracked, plus a linked tracked file;
  - refresh-stubs linked stub, with the skill links still made;
  - `upgrade --prune` orphan under a linked directory, with a sibling and as the only entry;
  - archive restore: chunk out, linked `roadmap/phases`, linked origin, linked stored, a second move unsafe.
- `tests/test_writers_refuse_links_out.py`: the generated-file `link_in` rows (init --force, regenerate_generated_files, finish) now expect a refusal, and the expected text is the rule's sentence (A5).
- `tests/test_upgrade.py`: `REFUSED_DIGEST` and `REFUSED_INDEX` match the new `refused <rel> (<rule message>)` line prefix.
- Mocks: `os.chmod` (monkeypatch, restored) in the swap test; `sys.argv` for `export_roadmap_md.main`. No call counts or order are asserted.
