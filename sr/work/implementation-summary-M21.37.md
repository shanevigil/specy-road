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

## Fix round 1 (review `gpt-6.1-sol-low` at `14c0c8da`)

Merged `origin/WIP/improvements-0-3-1` first (`825298ac`). Fix commit: `2337de03`.

- **R3: refusal after an earlier change. Fixed.** `restore_archive` now builds one view of the restore before changing anything.
  - Shallow record: `_shallow_view` checks the chunk before reading it.
  - Deep record: `_deep_view` checks the capsule, then reads it without writing. From it, it derives the shallow record `undeepen_archive` will write (`roadmap/archive/chunks/<id>.json` and the planning `stored` paths) and the paths it removes (capsule and reference).
  - `_preflight` then checks every path: touched files, target chunks, `stored`/`origin`, manifest, ledger, and the archive and planning directories. It runs before `undeepen_archive`.
  - An unreadable capsule gives no view, and `undeepen_archive` refuses with its own message before changing anything.
- **R4: cleanup that follows a link. Fixed.** `_prune_empty_archive` walks `roadmap/archive` with `os.walk` and `lstat`. Anything but the ledger and real directories, including a symlink of any kind, keeps the whole directory. Only real directories are `rmdir`ed, and the ledger is removed with `safe_write.remove`.
- **R2: containment against the wrong root, and equality excluded. Fixed.** `digest` computes containment with `Path.is_relative_to` (which includes equality) against the resolved checkout (`git_root`, else the project). Every path at or under it goes through `safe_write.write` with the checkout as root, so `-o <checkout>` is refused as a directory with exit 1. The bounded rule is stated in `-o`'s help: compared lexically with the resolved checkout. An absolute path outside the checkout is written as given.
- **R3, same class elsewhere: refresh-schemas. Fixed.** It checked each destination just before copying it. It now checks all of them before the first copy.
- **R1: not done. It needs changes outside the touch zones**, so this part of the leaf stops here. Applying the rule from `repo_root` in `refresh_stubs._write_if_changed`, and exiting 1 on a stub linked out, contradicts three files outside the zones:
  - `tests/test_prerelease_files.py::test_managed_writes_refuse_a_symlink_out_of_the_repo`: the `refresh` rows for `.agents/skills`, `.agents/skills/specyrd-validate/SKILL.md` and `.claude/skills` assert `returncode == 0` and the old `refused: a symlink leads outside the repository` text.
  - `tests/test_m13_7_notices.py`: `test_a_symlinked_skills_dir_reports_each_skill_once_with_the_link` and `test_a_reverse_symlinked_skills_dir_reports_each_skill_once_and_runs_agree` require writes through an in-repo symlinked `.agents/skills` or `.claude/skills` directory, a supported M13.7 layout.
  - `specy_road/specyrd_skills.py`: `specyrd init` writes the same `SKILL.md` files through `resolves_outside`, so refresh-stubs alone would disagree with init.

  To finish R1, add these three paths to the zones, together with the decision to drop the M13.7 symlinked-skills-directory layout. Then: route the write branch through `safe_write.write(repo_root, ...)`, delete the `resolves_outside` branch and its exception in `refresh_stubs.main`, and change those expectations to `error:` with exit 1.

## Probes

- R2, containment by string prefix or against the project instead of the checkout: searched the diff for `startswith` / `is_relative_to` / `relpath` containment checks.
  - `digest_cli`: fixed.
  - `safe_write._locate`: `relpath` with an empty-parts result, so equality is handled; the root then fails the final-kind check.
  - `upgrade_plan.refused_changes`: checks against `plan.checkout` (resolved); correct.
  - `init_project` and `refresh_schemas`: own the project root by design (their files live under it); correct.
- R2, output equal to the root: `test_digest_checks_an_absolute_output_against_the_checkout[checkout]` gives exit 1 with `is a directory`.
- R2, nested project with an absolute `-o` under a linked checkout directory: the `[checkout-sibling-link]` row is refused, outside unchanged.
- R3, a mutation before a later refusal, writer by writer:
  - archive restore, shallow and deep: fixed. New deep rows (`phases-linked`, `origin-linked`, `unpack-linked`) fail at `14c0c8da` and pass now.
  - refresh-schemas: fixed. The stale-earlier-schema rows fail at `14c0c8da` and pass now.
  - init: `_scaffold` checks before the first write; already so.
  - specyrd init: manifest check first; already so.
  - upgrade: `apply_plan` checks everything first; already so.
  - `_prune`: checks all orphans before any delete; already so.
  - `regenerate` and `regenerate_generated_files`: per-file refusal is the documented design (they report and go on).
- R3, `refresh-stubs --prune` from the CLI: the stub refresh runs before the prune check, so a refused prune leaves the refreshed stubs (the same writes as a run without `--prune`) and deletes nothing. Under `upgrade` it runs in the mirror and nothing is applied. Left as is.
- R4, cleanup that lists or removes through a link:
  - `_prune_empty_archive`: fixed. The regression test fails at `14c0c8da`.
  - `shutil.rmtree(archive_planning_dir)`: its directory is checked as a real directory, and `rmtree` unlinks inner links without following them.
  - `refresh_stubs._prune`: `rmtree` only for an lstat real directory, `prune_empty` stops at links.
  - `upgrade_plan.apply_plan` `rmdir`/`unlink`: targets are checked by the rule first.
- Full suite after the fixes: 5980 passed. `ruff check specy_road tests scripts` and `specy-road file-limits`: pass.

## Fix round 2 (review `gpt-6.1-sol-low` at `d1911074`)

Merged `origin/WIP/improvements-0-3-1` first (no conflicts). Fix commit: `cfcb4760`.

- **R3: a lexical `..` that climbs above the root and comes back in. Fixed in the primitive.**
  - `safe_write._locate` no longer normalizes first. A new `_below` applies `.` and `..` in order from the root anchor (as given, normalized, or resolved), and any `..` that climbs above it is refused, whatever follows. The rule is stated in `_locate`'s docstring.
  - `digest` now hands its `-o` to the rule as given, not normalized.
  - Tests: `test_dot_dot_out_of_the_root_is_refused` gains `../root/back` and `a/../../root/back`.
- **R2: a refusal that still exits 0. Fixed for every reachable instance in the zones.**
  - `upgrade._check` returns the failing next step: validate errors, or a refused generated file. `run_upgrade` and `_dry_run` exit 1 on either. The module docstring and the dry-run message now state the exit rule.
  - The same class appeared in two more places:
    - `init project --force` used to report a linked generated file as `skipped (...)` with exit 0. `_scaffold` now checks the generated files (with `--force`, which rewrites them) before any write, so it exits 1.
    - `specyrd init` reported a linked ignore file as a `refused:` outcome with exit 0. New `agent_ignores.check_ignore_files` is used by both `init project` and `specyrd init` (`_refuse_unsafe_paths`) before anything is written.
  - The dead refused-branch in `_write_generated` is removed.
  - Tests: `test_upgrade.py` rows for dangling, outward and tracked-index links now expect exit 1; a new `dry-run-in-repo-link` row; the `test_writers_refuse_links_out.py` `init --force` rows expect `error:` and exit 1; the specyrd row is renamed `test_specyrd_init_refuses_a_linked_manifest_or_ignore_file`, with a `gitignore-in-repo-link` row.
  - The new rows fail against `d1911074` (9 failures) and pass now.
- **R1: still not done.** The touch zones are unchanged after the merge, and the contradicting files are unchanged too:
  - `tests/test_prerelease_files.py`: refresh rows assert exit 0 and the old text;
  - `tests/test_m13_7_notices.py`: writes through an in-repo symlinked skills directory;
  - `specy_road/specyrd_skills.py`: `specyrd init` writes the same files on `resolves_outside`.
  - Also pinned outside the zones: `tests/test_upgrade_plan_parity.py::test_dry_run_copy_and_real_checkout_end_byte_identical[canonical-skill-linked-outside]` asserts `dry == real == 0` for a canonical skill linked outside. That is the same exit-0-on-refusal class (R2) for upgrade's per-file declined stub entries.

  Both need those paths added to the zones, plus the maintainer decision to drop the M13.7 symlinked-skills-directory layout. With that, the change is: `safe_write.write(repo_root, ...)` in `refresh_stubs._write_if_changed`; drop the `resolves_outside` branch and the `REFUSED` exception in `main`; treat a declined `refuse` entry as exit 1 in `run_upgrade`; update those expectations.

## Probes (fix round 2)

- R3, paths normalized before the rule could see a `..`: searched every changed caller.
  - `digest_cli`: fixed; it passes `out` as given.
  - `archive_restore`: `root / rel` raw; `chunk-out` and `..` rows refused.
  - `init_project`, `refresh_schemas`, `refresh_stubs`, `specyrd_init`, `generated_files`, `do_next_task_register`, `export_roadmap_md`: build `root / name` from fixed names; no normalization.
  - `upgrade_plan.refused_changes`: targets are `realpath` results (no `..` left), checked against the resolved checkout.
- R3, the primitive's anchors: a root given relative, with `..` in it, or through a link still matches a path spelled from it, because the anchors are absolute-as-given, normalized and resolved. Existing suites that call it with such roots pass (full suite 5997 passed).
- R2, a refusal that leaves exit 0, command by command:
  - `upgrade` real and `--dry-run`: fixed.
  - `init project --force`: fixed.
  - `specyrd init` ignore file: fixed.
  - `refresh-stubs`: exit 1 for a rule refusal; the outward `REFUSED` case is R1, blocked.
  - `upgrade` declined stub entries: blocked by `test_upgrade_plan_parity`.
  - `export`, `digest`, `refresh-schemas`: exit 1 already.
  - `archive_cli` restore: `ValueError`, exit 1.
  - `regenerate_generated_files`, called from archive/GUI/finish outside the zones: prints and returns the refused names; its callers' exit codes are outside the zones. Not changed.
- Full suite: 5997 passed. `ruff check specy_road tests scripts`: pass. `specy-road file-limits`: pass.

## Fix round 3 (review `gpt-6.1-sol-low` at `512fee21`): stopped, needs paths outside the touch zones

Merged `origin/WIP/improvements-0-3-1` (no conflicts). The merge did not change the touch zones or the contradicting tests. No code change this round. Both required changes are the open R1 from rounds 1 and 2:

- **R1: stub writes from `repo_root`, refusing linked ancestors.** `tests/test_m13_7_notices.py::test_a_symlinked_skills_dir_reports_each_skill_once_with_the_link` and `::test_a_reverse_symlinked_skills_dir_reports_each_skill_once_and_runs_agree` require writing `SKILL.md` through an in-repo symlinked `.agents/skills` or `.claude/skills` directory. `specy_road/specyrd_skills.py` (`specyrd init`) writes the same files on `resolves_outside`.
- **R2: refresh-stubs and upgrade exit 1 on an outward stub refusal.**
  - `tests/test_prerelease_files.py::test_managed_writes_refuse_a_symlink_out_of_the_repo` (the `refresh` rows) asserts `returncode == 0` and the old `refused: a symlink leads outside the repository` text.
  - `tests/test_upgrade_plan_parity.py::test_dry_run_copy_and_real_checkout_end_byte_identical[canonical-skill-linked-outside]` asserts `dry == real == 0`.
  - A3's acceptance text also says "declined entries are not changes and keep their refresher's per-file refusal". Turning upgrade's declined stub entries into exit 1 needs that text amended, and I may not edit acceptance.

### Probes (fix round 3)

- Touch zones after the merge: unchanged; none of the four paths above is listed.
- `tests/test_upgrade_plan_parity.py:143` (`assert dry == real == 0`): still present.
- `tests/test_prerelease_files.py:81` (`returncode == 0`): still present.
- `tests/test_m13_7_notices.py:38` and `:61`: still present.

### Needed to proceed

1. Add `tests/test_prerelease_files.py`, `tests/test_m13_7_notices.py`, `tests/test_upgrade_plan_parity.py` and `specy_road/specyrd_skills.py` to M21.37's touch zones.
2. Get a maintainer decision to drop the M13.7 symlinked-skills-directory layout.
3. Amend A3's "declined entries keep their refresher's per-file refusal".

The code change is then:
- `safe_write.write(repo_root, ...)` in `refresh_stubs._write_if_changed`, with the `resolves_outside` branch and `main`'s `REFUSED` exception removed;
- `run_upgrade` and `_dry_run` exit 1 when the plan has a `refuse` entry;
- the same rule in `specyrd_skills` for the canonical skill files;
- those tests' expectations updated.

## Fix round 4 (maintainer decisions 2026-11-06; review `gpt-6.1-sol-low` at `512fee21`)

Merged `origin/WIP/improvements-0-3-1` (`163ca582` and after). That merge added `specy_road/specyrd_skills.py`, `tests/test_prerelease_files.py`, `tests/test_m13_7_notices.py` and `tests/test_upgrade_plan_parity.py` to the zones and amended A1, A2, A3 and A5. Fix commit: `7ca2adff`.

**Superseded:** Sol's "remove the exception" (R1) is superseded by the maintainer's decision, **for the in-repo skills-directory link only**. Everything else in R1 and R2 is implemented.

- **R1, the class: a writer that resolves away a linked ancestor (`dest.parent` as root, `resolves_outside`).** One helper, `specyrd_skills.skill_path(repo_root, rel, expected)`, implements the skills-link rule.
  - When `rel` is under `.agents/skills` or `.claude/skills` and that directory is a symlink, the single component is swapped for its target. The target must be a real directory inside the repository, reached in one hop.
  - The safe-write rule then applies from `repo_root` to the result.
  - Refused: a chained link (the target is a link or under one), a dangling one, one leaving the repository, and any other link on the path.
  - Users: `refresh_stubs._write_if_changed` (the file branch; the `resolves_outside` branch is gone), `specyrd_skills.install_stubs` and `specyrd_skills.ensure_link` (their `resolves_outside` checks are gone), and `specyrd_init` via `check_install_paths` before anything is written.
  - `mirrored_copies` skips a mirror directory the rule refuses, instead of using `resolves_outside`.
  - `specyrd_skills` no longer imports `resolves_outside`.
- **R2, the class: a refusal that leaves exit 0.** One predicate, `managed_block.rule_refusal(outcome)`: a `refused: <why>` outcome of the rule is an error, while `REFUSED` (the `resolves_outside` writers) is not.
  - `refresh-stubs` (`_exit_on_rule_refusals`) prints `error: <why>` and exits 1.
  - `upgrade` (`_declined`) prints `error: <why>` and records the entry as action `error`. Like any declined entry it applies nothing, and the rest of the plan applies. `_check` makes the real run and `--dry-run` exit 1 when the plan has an `error` entry.
  - `specyrd init` exits 1 before writing, through its check of the install paths.
  - Report lines, as decided: `agents_md_block` / `agent_guide_block` (`REFUSED`), `upgrade_templates`, `refresh_profiles`, and shipped docs.
  - `copy_missing_docs` is now on the rule (`refused_link`, `safe_write.copy`) and keeps its `skipped` report line. The digest read guard uses `refused_link`. `upgrade.py` no longer imports `resolves_outside`.
- **Mirror paths.** `make_plan` now maps the mirror's `outside/` paths back in the printed output too, so a refusal reads the same in the dry run and the real run. It does this through `Mirror.real_text` and `_named_in_checkout`.
- **Docs.**
  - `docs/install-and-usage.md` names the skills-link exception and the declined entries that stay report lines.
  - CHANGELOG records the stub and skill-file behaviour change.
  - Module docstrings updated: `refresh_stubs` (new paragraph), `upgrade` (the exit rule), `upgrade_plan.Entry` (action `error`), `specyrd_skills.ensure_link` and `install_stubs`, `safe_write.check_all` and `exit_on_refusal`.
- **Maintainer refactor rule (no function more complex than at the merge base `e3246433`):** checked with ruff C901 at `max-complexity=0`, base against now, for every changed module. None is higher. Earlier rounds had pushed 12 functions over, all now back at or below their base:
  - `refresh_stubs.main` 7 → 5;
  - in `upgrade`: `_check` 4 → 3, `_report_stubs_declined` 5 → 4, `run_upgrade` 7 → 5;
  - `refresh_schemas` 7 → 6, `export._write_export` 5 → 4, `digest.cmd_digest` 7 → 5, `init._copy_templates` 6 → 5, `_prune_empty_archive` 7 → 4;
  - in `managed_block`: `_write` 6 → 4, `apply_managed_block` 6 → 5;
  - in `upgrade_plan`: `apply_plan` 9 → 8, `make_plan` 5 → 4.

  Tools: `safe_write.check_all` and `exit_on_refusal`, `upgrade_plan.check_changes` (replaces `refused_changes`), and small extractions. There is no `noqa: C901`. New functions are at most 6 (`safe_write._below`, `mkdirs`).

### Probes (fix round 4)

- `resolves_outside` left in the leaf's writers, by `grep`: only `managed_block` (defines it), `agents_md_block`, `agent_guide_block` (through `managed_block` non-strict), `upgrade_templates` and `refresh_profiles._contained`, as A1 allows. None in `specyrd_skills`, `refresh_stubs` or `upgrade`.
- In-repo skills-directory link, both directions (`.agents/skills → .claude/skills` and back): `test_m13_7_notices` layouts still write (dry and real).
- A stub under a linked parent that is not a skills directory (generic pack): error, exit 1, nothing written through it (`generic-dir-linked`, dry and real).
- Skills link that is chained, dangling, or outward (outward and back in): error naming the link, exit 1 (`test_only_an_in_repo_skills_directory_link_is_written_through`, 8 rows).
- refresh-stubs and specyrd init with a stub, skill file or `.claude/skills` linked out (`test_prerelease_files`): exit 1 with `error: <path> is a symlink`. `AGENTS.md` linked out (init) stays a report line with exit 0.
- upgrade real and `--dry-run` with a canonical skill linked outside (`test_upgrade_plan_parity`): both exit 1. The rest of the plan applies, and the trees match between dry and real. The manifest drops the skill in both. The refusal line is identical in both, now that `outside/` is mapped back.
- `rule_refusal` against `REFUSED`: the `agents-md-linked-outside` parity row still exits 0. The `CLAUDE.md` alias rows are unchanged.
- An ignore file refused for a link (strict managed block) under upgrade is a `refused:` outcome, so it is an `error`. That is the same class, and ignore files are not on the maintainer's report-line list.
- Full suite: 6001 passed. `ruff check specy_road tests scripts`: pass. `specy-road file-limits`: pass.

## Fix round 5 (review `gpt-6.1-sol-low` at `b25f3c86`)

WIP merge: already up to date. Fix commit: see the commit after `b25f3c86` (`fix(M21.37): a skill link's relative target ...`).

- **R1, the class: a relative path computed from a path's logical location (before the skills-link swap) but used at its relocated location.**
  - `ensure_link` wrote `link_target(agent, name)`, which counts `..` from `.claude/skills`' logical depth, into the directory `skill_path` relocated the link to. Through a `.claude/skills` alias at another depth the link pointed nowhere.
  - Now `canonical` and `link` are both located by the skills-link rule, and the text is `os.path.relpath(canonical, link.parent)`, from where the link really lands.
  - The default layout gets the same text (`../../.agents/skills/<name>`), so `test_specyrd_skills`' `link_target` assertion still holds. `link_target` is kept as the default-layout text, and its docstring now says so.
  - The UNCHANGED comparison uses `canonical.resolve()`.
- **Test:** `test_skill_links_resolve_through_a_skills_directory_alias_at_another_depth` runs `specyrd init`, then `refresh-stubs` remaking a deleted link. It has two rows, `.claude/skills` and `.agents/skills`, each aliased to `tools/deep/skills` (depth 3).
  - The `.claude/skills` row fails on `b25f3c86` and passes now.
  - The `.agents/skills` row passes on both, because the link sits in the real `.claude/skills` and its text goes through the alias. It is kept as coverage of the other clause.

### Probes (fix round 5)

- Other relative text built from a logical path and used after `skill_path` relocates it: `grep` for `link_target`, `os.symlink`, `relpath` and `readlink` in the leaf's writers.
  - `specyrd_skills.ensure_link`: fixed (the only writer of link text).
  - `install_stubs` and `refresh_stubs._write_if_changed`: write content to the absolute relocated path; no relative text.
  - The copy fallback in `ensure_link`: absolute `link / "SKILL.md"`.
  - `upgrade_plan.Mirror`: copies existing link text with the structure preserved, so an alias keeps its depth in the mirror.
- Readers that take the logical path: `mirrored_copies` and `_is_disposable_copy` read through an in-repo alias, and compare `resolve()`d paths, which is depth-independent. Report text (`refresh_stubs_report.resolve_linked`) only displays. None writes.
- Complexity against `e3246433`: `ensure_link` is no higher; it is the same branches with one more call inside the existing `try`.
- Full suite: 6003 passed. `ruff check specy_road tests scripts`: pass. `specy-road file-limits`: pass.

## Fix round 6 (coordinator; review `gpt-6.1-sol-low` at `591a4781`)

WIP merge: already up to date. Fix commit: `42796a63`. The maintainer's skills-link decision stands; this round only makes every entry point apply it to the same link shape.

- **The class: the upgrade mirror showed a link in a different shape from the checkout.**
  - `Mirror.build` rewrote an absolute link text to `to_sandbox(realpath(src))`, and rewrote a relative one that resolved elsewhere to its resolved target.
  - So `skill_path` and `safe_write` saw a single hop in the mirror where the checkout had a chain, a target under a linked directory, or a `..` that climbs out and back in.
  - The result: `upgrade` and `--dry-run` accepted what `refresh-stubs` refused.
- **Design change, removing the class rather than patching the instance.** The mirror now lays out the filesystem as the checkout sees it: the checkout sits at `outside/<its absolute path>` (`repo = to_sandbox(checkout)`).
  - **Link text:** every link keeps its own text, one hop: a relative text verbatim, an absolute one with `outside/` in front. A chain, a linked ancestor or a lexical climb resolves in the mirror exactly as in the checkout. The old realpath fix-up loop is gone.
  - **Content:** content the copy lacks (a target out of the checkout, or under `skip`) is copied to its real path's place (`_place`). A link text naming that place another way reaches it through one more link, and only a path already outside the checkout can cross it. The verdict for such a path is "outside", which does not depend on its shape.
  - **Ordering:** all links of a round are created before any content is placed, so `mkdir` never makes a real directory where a link belongs. That was a latent bug the new table exposed.
  - **Simplifications:** `to_sandbox`, `to_real` and `real_text` are one prefix each now. `snapshot` walks `outside` once.
  - **Invariant:** stated in `Mirror`'s docstring: `upgrade`, `upgrade --dry-run` and `refresh-stubs` give the same verdict for the same checkout.
- **Tests: one table, the single place for skills-link shapes.** `test_every_entry_point_gives_the_same_skills_link_verdict` covers 7 shapes × {`.agents/skills`, `.claude/skills`} × {`refresh-stubs`, `upgrade`, `upgrade --dry-run`} = 42 rows.
  - Shapes: relative in-repo and absolute in-repo (allowed); relative chained, absolute chained, absolute under a linked ancestor, outward, and dangling (refused).
  - Refused rows: `error: <link> is a symlink (to <text>), not a link to a real directory in the repository` (the same line from all three entry points), exit 1, no traceback, and the bytes and link texts of the real skills directory and of `outside` unchanged.
  - Allowed rows: exit 0. After a real run the stale canonical skill is refreshed and every `.claude/skills` link resolves to its canonical skill from where it lands (the real directory is at depth 3).
  - The rows that fail on `591a4781` are all 8 upgrade / `--dry-run` rows for absolute chained and absolute under a linked ancestor, for both directories.
  - Folded into the table and removed: round 5's `test_skill_links_resolve_through_a_skills_directory_alias_at_another_depth`, and the outward, chained and dangling rows of `test_m13_7_notices`. Its refusal test keeps only the non-skills linked directory, renamed `test_a_stub_under_a_linked_directory_that_is_not_a_skills_directory_is_refused`.

### Probes (fix round 6)

- Every place the mirror maps a path, checked for a link hidden from `safe_write` or `skill_path`:
  - `build` link text: fixed (own text, one hop).
  - `_ensure` content: placed at its real path's place, reached only from a lexically different name. For an in-checkout name the mirror's own links make `lexists` true, so no extra link is added inside the checkout's tree.
  - `to_real` and `_diff`: lexical over the mirror walk, which does not follow links. Unchanged in meaning.
  - `check_changes`: targets from `_diff`. Unchanged.
  - `apply_plan(plan, copy.to_sandbox)` (dry run): same prefix mapping.
- Limit: a link whose text goes through a link **under `skip`** (`work/`, not mirrored). The mirror makes that path from directories plus one link, so the link under `work/` is not reproduced. No writer in the refresh writes under `work/`. Stated here as the bound.
- Limit: a skills link into `.git`. `_ensure` does not copy git internals, so the mirror's link dangles (refused) where the checkout's target is a real directory. Not a write path anyone uses; recorded as the second bound.
- Verdict and line identical across the three entry points: the table asserts the same `error:` line, because `real_text` maps `outside/` back.
- Earlier mirror users still pass:
  - `test_upgrade_preview` (Sol F1 schema through an external alias of the checkout; a git-less copy), `test_upgrade_plan_parity` (hard links, `CLAUDE.md` alias, `AGENTS.md` linked outside, nested project), `test_upgrade_parity` and `test_upgrade_work_templates`;
  - full suite: 6037 passed.
- Complexity against `e3246433`: no changed function higher. `Mirror.build` is the same count. `_ensure` is 3 (the content copy is `_place`).
- `ruff check specy_road tests scripts`: pass. `specy-road file-limits`: pass.

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
- Fix round 1:
  - `archive_restore._shallow_view`, `_deep_view` and `_check`: one view and check of every restore path before the first change, deep records included (R3).
  - `_prune_empty_archive`: rewritten to walk by `lstat` (R4).
  - `digest_cli`: checkout containment via `git_root` and `is_relative_to` (R2).
  - `refresh_schemas`: a separate check pass before the copy pass (R3 class).
  - Tests: `test_digest_checks_an_absolute_output_against_the_checkout` (2 rows); deep rows in `test_archive_restore_refuses_before_the_first_change` and the `_unpack_linked` layout; `test_restoring_the_last_record_keeps_an_unrelated_linked_directory`; the stale-earlier-schema setup in `test_schema_refresh_and_upgrade_refuse_a_linked_schema`.
- Fix round 2:
  - `safe_write._below`: the in-order `..` rule (R3).
  - `agent_ignores.check_ignore_files`: one pre-check of the ignore files for `init project` and `specyrd init` (R2 class).
  - `specyrd_init._refuse_unsafe_paths`: replaces `_refuse_unsafe_manifest` (R2 class).
  - `init_project._scaffold`: the generated-file check under `--force` (R2 class).
  - `upgrade._check`: returns the failing step (R2).
  - Tests: re-entry cases in `test_dot_dot_out_of_the_root_is_refused`; the `dry-run-in-repo-link` row and the exit-1 rows in `test_upgrade.py`; the `gitignore-in-repo-link` row; the `init --force` expectation.
- Fix round 4:
  - Helpers: `specyrd_skills.skill_path`, `SKILLS_DIRS` and `check_install_paths` (the skills-link rule); `managed_block.rule_refusal` (the R2 predicate); `safe_write.refused`, `check_all` and `exit_on_refusal` (consolidation).
  - Extractions to stay within the complexity rule: `upgrade._declined`, `refresh_stubs._exit_on_rule_refusals`, `digest_cli._write_output`, and `managed_block._read`, `_plain_write` and `_strict_write`.
  - `upgrade_plan`: `check_changes`, `Mirror.real_text`, `_named_in_checkout`.
  - Tests: in `test_m13_7_notices`, `test_only_an_in_repo_skills_directory_link_is_written_through` replaces the two tests whose expectations the decision reverses. The `test_prerelease_files` refresh and specyrd rows expect exit 1. The `test_upgrade_plan_parity` canonical-skill row and `test_sol_f2` expect exit 1 and the refusal line. The digest checkout test now goes through `main`.
- Fix round 5: in `ensure_link`, the relocated-link `relpath` target (R1). Test: `test_skill_links_resolve_through_a_skills_directory_alias_at_another_depth` (2 rows).
- Fix round 6: `upgrade_plan.Mirror` layout (`repo = to_sandbox(checkout)`), round-based link creation, `_ensure` and `_place` (the class). Test: `test_every_entry_point_gives_the_same_skills_link_verdict` (42 rows, the single shape table); removed the round-5 alias test and the m13_7 skills-shape rows it covers.
- Mocks: `os.chmod` (monkeypatch, restored) in the swap test; `sys.argv` for `export_roadmap_md.main`. No call counts or order are asserted.
