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

## Fix round 7 (review `gpt-6.1-sol-low` at `e3f70e09`; acceptance A1 skills-link text rule)

- **The class behind R1 and R2:** the skills-link verdict depended on what a link's target *means*. That meaning came from lexical normalisation (R1: `../hop/../real`) or from content the upgrade mirror may lack (R2: a target in `.git`). Each round patched one instance. A1 now fixes the rule as a property of the link's own text, so this fix removes the class instead.
- **The fix (`c2422f24`):** `specyrd_skills.skill_path` accepts a symlinked skills directory only when its raw `os.readlink` text is, byte for byte, `SKILLS_LINK_TEXT[skills]`:
  - `../.agents/skills` at `.claude/skills`;
  - `../.claude/skills` at `.agents/skills`.
- **How it is checked:** `safe_write.refused` runs the `lstat` walk on the un-normalised join `link.parent / text`. A linked `.agents` or `.claude` is refused, and the other directory must be a real directory. `os.path.normpath` is gone. The verdict now depends only on that text and on the `lstat` kinds of two in-repo directories, and the mirror copies both exactly. So refresh-stubs, upgrade and `--dry-run` cannot disagree.
- **R1:** `../tools/bounce/../skills` is refused everywhere: the text is wrong.
- **R2:** `../.git/skills` is refused everywhere, consistently, for the same reason. The review asked for consistent *success* here, but A1 (maintainer, 2026-11-06) refuses every other skills-link text, so the consistent verdict is refusal. `Mirror._ensure`'s `.git` exclusion no longer affects any skills verdict and is unchanged.
- **The refusal message** names both allowed values (A7): `<link> is a symlink (to <text>), not a real directory or a link to <allowed> (the skills directories may link only .agents/skills -> ../.claude/skills or .claude/skills -> ../.agents/skills)`.
- **`ensure_link`:** the dynamic `os.path.relpath` target is gone. The link text is `link_target()` (A1). When one skills directory links to the other, the per-skill link's place is the canonical skill itself, and `ensure_link` returns `unchanged`. Before, a dry run reported `created` there, and a run without the canonical directory would have made a self-loop link.
- **Docs:** `docs/install-and-usage.md`, CHANGELOG `[Unreleased]`, the `refresh_stubs` module docstring and upgrade's `_REFUSED_STEP` hint now name the two values. They tell an adopter with an alias such as `../tools/skills` to replace it with one of the two values or a real directory (A7).
- **Tests:** the one shape table, `test_every_entry_point_gives_the_same_skills_link_verdict`, now has 10 shapes × both directories × 3 entry points = 60 rows.
  - Allowed: `pair`, the exact relative text.
  - Refused: `absolute-pair` (absolute text naming the right directory), `pair-under-linked-parent`, `relative-alias` (A7), `relative-chained`, `absolute-under-linked-ancestor`, `dotdot-through-link` (R1), `git-dir` (R2), `outward`, `dangling`.
  - Refused rows require the exact `error:` line, exit 1, no traceback, and the link, the moved skills, `tools/` and the outside directory unchanged.
  - Allowed rows require that a real run refreshes the stale canonical file and that every `.claude/skills/<name>` holds a `SKILL.md` resolving to `.agents/skills/<name>`. `--dry-run` leaves it stale.
  - Red-green: with `specyrd_skills.py` from `e3f70e09`, all 18 `dotdot-through-link`, `git-dir` and `relative-alias` rows fail.
  - Removed rows: `relative-in-repo` and `absolute-in-repo`, formerly allowed and reversed by A1 (the alias is now `relative-alias`, refused), and `absolute-chained` (covered by `relative-chained` and `absolute-under-linked-ancestor`).

### Probes (fix round 7)

- `skill_path`, the only place a skills link is interpreted (callers: `check_install_paths`, `install_stubs`, `ensure_link`, `refresh_stubs._write_if_changed`): exact-text check before any path use. Result: no normalisation left. `grep normpath|relpath` in `specyrd_skills.py`, `refresh_stubs.py` and `upgrade_plan.py`: none on a skills path.
- `Mirror.build` copies relative link text verbatim. Result: `../.agents/skills` and `../.claude/skills` keep the same text and verdict in the mirror. The `pair` rows pass for upgrade and `--dry-run`.
- `.git`-target class beyond skills: a skills link into `.git` is refused by text everywhere. Result: consistent.
- `.git`-target class, steering files: `CLAUDE.md`/`AGENTS.md` linked into `.git` stay on `resolves_outside` (out of scope by A1). The mirror does not copy `.git` and its snapshot skips it, so upgrade would plan no write there where refresh-stubs writes into `.git`. Result: the upgrade side writes less, never outside the checkout; recorded, not changed.
- `.claude/skills` with `.agents` itself a link: the canonical files are refused first by the plain rule (`.agents is a symlink`), and the per-skill links are skipped as declined. Result: exit 1, nothing written; the table's row asserts that line.
- Cycle (`.claude/skills -> ../.agents/skills` and `.agents/skills -> ../.claude/skills`): `skill_path` refuses it (the other is not a real directory). But `refresh_stubs_report.resolve_linked` (`specy_road/bundled_scripts/refresh_stubs_report.py:53`, **outside the touch zones**) then raises `RuntimeError: Symlink loop` from `Path.resolve()` while printing the report. Result: a traceback for this layout, which predates this leaf. No row added; a follow-up needs that file in the zones.
- `_prune` and `mirrored_copies` do not use the exception: an orphan or mirror under a linked skills directory is refused or skipped by the plain rule. Result: unchanged, stricter.
- Full suite after the change: 6124 passed. `ruff check specy_road tests`: pass. `specy-road file-limits`: OK.

## Fix round 8 (review `gpt-5.6-sol-high` at `ab728acf`; `gpt-6.1-sol-low` at `e3f70e09`)

Commit `09093cc2`. `refresh_stubs_report.py` is now in the touch zones (the brief lists it).

- **Class.** A symlink loop on a path a command writes. The rule refuses a loop: `lstat` sees a symlink. But code that reads, resolves or makes a directory before the rule runs meets the loop first and raises something that is not a `SafeWriteError`: pathlib's `RuntimeError("Symlink loop from ...")` (`resolve()` before Python 3.13), `OSError` `ELOOP`, or `FileExistsError` from `mkdir(exist_ok=True)` over a looping link. The CLI boundaries caught only `SafeWriteError`, so each such loop printed a traceback. Sol's two cases are instances: the report printer (`resolve_linked`) resolved a refused entry's parent, for the exact-text two-skills cycle and for a generic stub directory linked to itself.
- **Design.** There is one translation, at the boundary. `safe_write.loop_refusal(e)` turns a loop error into the rule's refusal of the looping link: the shallowest component of the error's path that is a symlink `stat` cannot follow, in the usual sentence (`<link> is a symlink (to <text>), not a directory`). Any other error returns `None` and is raised again. `exit_on_refusal` and the new `refusal_of` use it. Every migrated command goes through them: `refresh-stubs`, `refresh-schemas` and `upgrade` (`main`), `specyrd init` (`run_init`, decorated), `init project` (`run_init_project`), and `export` and `digest` (already on `exit_on_refusal`). `upgrade_plan.make_plan` converts a loop met in the mirror before `_named_in_checkout`, so the message names the checkout's path. The result is `error: <path> is a symlink (to …)`, exit 1, no traceback.
- **Report printer.** `resolve_linked` resolves only an entry whose path passes the skills-link rule (`skill_path(…, None)`). A refused path wrote nothing and is printed as it is. This covers a refused entry and a `skipped` per-skill link under a looping skills directory alike: the cycle's link entries are `skipped (not ours)`, not `refused`, so a check on the outcome text alone missed them.
- **Tests.** The skills-link shape table gains a `cycle` row, 6 rows: both skills directories × refresh-stubs, upgrade and `--dry-run`. The m13_7 generic linked-parent test gains a `self-loop` parameter (2 rows, real and dry run). `test_a_symlink_loop_on_a_managed_path_is_refused_without_a_traceback` has 11 rows. Each row printed a traceback at `ab728acf`: `AGENTS.md` × refresh-stubs, upgrade, `--dry-run`, specyrd init and `init project --force`; `CLAUDE.md` × specyrd init; `.specyrd` × refresh-stubs, upgrade and `--dry-run`; and `.agents/skills/specyrd-brief` × refresh-stubs and upgrade. `test_safe_write`'s loop test (3 rows) covers `loop_refusal` for the read, resolve and mkdir errors, and returns `None` for a plain `FileExistsError`.

### Probes (fix round 8)

- Self-loop link (`X -> X`) at 12 managed paths (`AGENTS.md`, `CLAUDE.md`, `.gitignore`, `.cursorignore`, `schemas`, `schemas/roadmap.schema.json`, `.specyrd`, `.specyrd/manifest.json`, `.claude/skills/specyrd-brief`, `.agents/skills/specyrd-brief`, `roadmap.md`, `docs`) × 10 commands (refresh-stubs with and without `--prune`, upgrade real and `--dry-run`, refresh-schemas, export, digest, specyrd init, `init project` with and without `--force`), run as subprocesses against this worktree's package. Result: 13 tracebacks at `ab728acf`, 0 now. Every command that writes the path exits 1 with `error: <link> is a symlink (to <text>)`. A command that never writes the path exits 0, for example refresh-stubs with a looping `CLAUDE.md`: it refreshes only a `CLAUDE.md` that is a file, so it skips this one, as before. Upgrade with a looping `roadmap.md` gives the existing `refused roadmap.md (…)` report line and exit 1.
- The same 120 runs against the main checkout's package (`WIP/improvements-0-3-1`): many more tracebacks, including `schemas` and `.gitignore` loops. This leaf's rule had already closed those.
- Sol's exact-text two-skills cycle, CLI: refresh-stubs (real, `--dry-run`, `--diff`, `--prune`) all exit 1 with 26 `error:` lines and no traceback. Upgrade and `--dry-run` give the same; they never passed `repo_root` to the report printer, so they did not crash before either.
- Sol's generic self-loop parent, CLI: refresh-stubs real, `--dry-run`, `--diff` and `--prune` all exit 1, no traceback.
- Other `resolve()`/`realpath` calls in the zones: `managed_block.resolves_outside`, `specyrd_skills.ensure_link` and `_is_disposable_copy`, `archive_restore`, `upgrade_plan` (`realpath`, which does not raise on a loop), `specyrd_init._validate_generic_commands_dir`, and the root resolves in each `main`. Result: each runs inside one of the boundaries above, so a loop there is now an `error:` line. The probe matrix exercised `resolves_outside` (`AGENTS.md`, `CLAUDE.md`) and the mkdir paths (`schemas`, `.specyrd`, `docs`).
- `restore-archive` (`archive_cli`, outside the zones) is not on `exit_on_refusal`. Its preflight is lexical `lstat`, so a loop is refused as a `SafeWriteError` before any `resolve()`. Its CLI already handled those. Not changed.
- Considered and reverted: keeping a refused stub's manifest record. A refused recorded stub drops out of `.specyrd/manifest.json`, so a generic pack under a linked directory is forgotten after one refused real run, and the next run exits 0. `test_upgrade_plan_parity::test_sol_f2_a_refused_canonical_skill_is_unowned_in_both_manifests` pins that drop as an earlier review decision (Sol F2), so I left it alone. Recorded for the maintainer.
- `gpt-6.1-sol-low` R1/R2 (at `e3f70e09`) were resolved in round 7 by the exact-text rule. Both shapes stay refused across setup, refresh-stubs and both upgrade modes (the `dotdot-through-link` and `git-dir` rows). R2 asked for "consistent successful" behaviour; it is consistently refused instead, because A1 allows only the two link texts.
- Red-green: with the package files from `ab728acf`, all 11 loop rows, the 2 `cycle` refresh-stubs rows and the 2 `self-loop` m13_7 rows fail. With the fix they pass.
- Full suite: 6146 passed (`pytest -n 4`). `ruff check specy_road tests`: pass. `specy-road file-limits`: OK.

## Fix round 9 (review `grok-4.7-high` at `85466059`; `gpt-6.1-sol-low` at `e3f70e09`)

Commit `906fc4f3`.

- **grok's finding.** `specyrd init` wrote `.specyrd/README.md` with `Path.write_text`, after `mkdir`, outside the rule. A dangling link there created the outside target (exit 0). With `--force`, a link to an existing file had its target's bytes replaced. `refresh-stubs` already refused the same path.
- **Class.** A path that `specyrd init` writes but `_refuse_unsafe_paths` does not check, and that is not written through `safe_write`. Every write in `run_init` needs both the preflight and a `safe_write` write.
- **Fix.** `_refuse_unsafe_paths` now checks `.specyrd/manifest.json` and `.specyrd/README.md` before anything is written. `_write_readme_and_gui_stub` writes the README with `safe_write.write(repo_root, …)`, so its parent `mkdir` goes through the rule as well. A linked README gets `error: <path> is a symlink (to …), not a regular file`, exit 1, with or without `--force`, and nothing in the checkout or outside changes.
- **Tests.** `test_specyrd_init_refuses_a_linked_manifest_or_ignore_file` gains the `readme-link-out` and `readme-dangling` layouts and a `force` parameter (10 rows, up from 3). The README rows also assert that the dangling target was never created. Red-green: with `specyrd_init.py` from `85466059`, all 4 README rows fail; with the fix they pass.
- **Sol R1/R2.** Already resolved in round 7 by the exact-text rule; see the round 8 probes. No change this round.

### Probes (fix round 9)

- Every write in `specyrd_init.run_init`. Result:
  - stubs, canonical skills and skill links: `check_install_paths` plus `install_stubs` and `ensure_link` (skills-link rule);
  - manifest: preflight plus `safe_write.write`;
  - README: fixed here;
  - `.gitignore` and the Cursor ignore files: `check_ignore_files` plus the strict managed block;
  - `AGENTS.md` and `CLAUDE.md`: `resolves_outside`, kept by A1;
  - `~/.specy-road/gui-settings.json`: in `$HOME`, not in the checkout, so outside the rule's owned root. Unchanged.
- The opt-in hooks of `specyrd init` (`--install-guard-hooks`, `--install-pre-push`), in `specy_road/specyrd_hooks.py` (**outside the touch zones**, not named in A2): `_write_json` (`.claude/settings.json` and similar), the hooks README under `.specyrd/hooks/<agent>/`, and `.git/hooks/pre-push` use `Path.write_text`, not the rule. Same class, but these writes only happen behind opt-in flags. Not changed here; a follow-up must add that file to the zones.
- Remaining `write_text`, `write_bytes`, `mkdir`, `unlink`, `rmdir` and `copy` calls in the zoned modules. Result: each one is either on the rule, or behind a preflight (`archive_restore`, after `_preflight`; `upgrade_plan` apply, after `check_changes`), or allowed by the brief, or a temporary directory:
  - allowed by the brief: `managed_block._plain_write` (the `resolves_outside` callers only) and `digest_cli` (an explicit absolute `-o` outside the checkout);
  - temporary directories: the `upgrade_plan` mirror and the `refresh_stubs` dry-run copy.
  - No other unchecked checkout write found.
- `refresh-stubs` on a linked `.specyrd/README.md`: still exit 1 with `error:` (grok's probe). `specyrd init` and `refresh-stubs` now agree.
- Full suite: 6153 passed (`pytest -n 4`). `ruff check specy_road tests`: pass. `specy-road file-limits`: OK.

## Fix round 10 (review `gpt-5.6-sol-high` at `6fdd5a59`; `gpt-6.1-sol-low` at `e3f70e09`; `grok-4.7-high` at `85466059`)

Commit `b86b42ce`. `specy_road/specyrd_hooks.py` is now in the touch zones.

- **Sol-high's finding.** The opt-in hook installs of `specyrd init` wrote outside the rule. These are the harness file (`.claude/settings.json`, `.codex/hooks.json`, `.cursor/hooks.json`), `.specyrd/hooks/<agent>/README.md` and `.git/hooks/pre-push`, written with `mkdir` and `Path.write_text`. Sol-high showed that a linked `.cursor/hooks.json` overwrote the outside JSON.
- **Class.** Same as round 9: a path `specyrd init` writes that the preflight does not check and that is not written through `safe_write`.
- **Fix:**
  - New `specyrd_hooks.hook_destinations` lists every path the opt-in installs would write. `specyrd_init._refuse_unsafe_paths` checks all of them before the first write, so `--dry-run` is covered too.
  - `_write_json`, the hooks README and `install_pre_push_hook` write through `safe_write.write`. Before reading the existing harness JSON, its path goes through `safe_write.check`.
  - The pre-push hook keeps its earlier mode. An existing file keeps its own mode; a new file gets `0o666` less the umask. Execute bits are added in both cases, and the mode is set on the temp file before the replace, not with a `chmod` afterwards.
- **Tests.** New `test_specyrd_init_refuses_a_linked_hook_destination` (10 rows). It covers each agent's harness file, the hooks README and `.git/hooks/pre-push`, each with a final link and with a linked parent. Each row expects exit 1 with `error:` naming the path, no traceback, and no change in the checkout or outside. For the final rows, it also checks that no file was added under `.git/hooks`. Red-green: with `specyrd_hooks.py` and `specyrd_init.py` from `6fdd5a59`, 9 of 10 rows fail. The one that passes, the `.claude` parent link, was already refused by the skills check.
- **Sol R1/R2** (`gpt-6.1-sol-low` at `e3f70e09`) and **grok's README finding**: resolved in rounds 7 and 9. No change this round. The `relative-alias`, `dotdot-through-link` (R1) and `git-dir` (R2) rows of the shape table still pass, all expecting refusal. The acceptance allows only the two exact skills-link texts, so R2's `.git` target is refused everywhere, consistently, and never left dangling.

### Probes (fix round 10)

- Every write in `specyrd_init.run_init`, now including the hooks. Every path is checked by `_refuse_unsafe_paths` and written through the rule, except `AGENTS.md` and `CLAUDE.md` (`resolves_outside`, kept by A1) and `~/.specy-road/gui-settings.json`, which is outside the checkout. Result: no unchecked write left.
- Other callers of `install_orchestration_hooks` and `install_pre_push_hook` in the package: none outside `specyrd_init`. Only `tests/test_orchestration_guard_hooks.py` calls them directly, and it passes. Result: no path skips the preflight in a CLI run, and a direct call still refuses at the write.
- A worktree, where `.git` is a file, with `--install-pre-push`. Result: `error: <wt>/.git is a regular file, not a directory`, exit 1, nothing written. Before: stubs written, then a `mkdir` traceback.
- A dry run with a linked hook destination. Result: refused by the preflight (exit 1), like the other `specyrd init` paths.
- Remaining `write_text`, `mkdir`, `unlink`, `copy`, `chmod` and `replace` calls across all zoned modules (grep). Result: the same set as round 9, minus `specyrd_hooks`, which no longer has any.
- Full suite before the final split: 6162 passed, plus 1 file-limits failure (`run_init` at 81 lines). That was fixed by moving the hook list into `_refuse_unsafe_paths`. After the fix, the file-limits, setup-writers, guard-hooks and doc-link tests all pass (203). `ruff check specy_road tests`: pass. `specy-road file-limits`: OK.

## Writer audit (coordinator, round 10)

Method: for every entry point I read the call graph. I also ran each one under `strace` (`openat` with a write flag, `mkdir`, `rename`, `symlink`, `unlink`, `rmdir`, `chmod`) in a scratch repo. The runs were `init project`, then `init project --force`; `specyrd init --ai claude-code --install-orchestration-hooks --install-pre-push-hook --extras gui`, then `--ai cursor` and `--ai codex` with the hooks, and `--ai generic --force`; `refresh-stubs --prune`; `refresh-schemas`; `export`; `digest`; and `digest -o docs/d.md`. A write on the rule shows as a `.<name>.<hex>.tmp` file renamed onto the destination. Any other written path is in the table below with its reason.

| Writer | Path(s) | Entry points | On the rule? | Why |
|---|---|---|---|---|
| `init_project._copy_templates` → `safe_write.copy` | every template file (`roadmap/`, `schemas/`, `constitution/`, `docs/`, …) | init project | yes, each checked before the first copy | A2 |
| `init_project._write_generated` → `generated_files.regenerate_generated_files` → `safe_write.write` | `roadmap.md`, `roadmap-context.md` | init project; pickup and upgrade also reach it | yes; with `--force` checked before the first write, without it a present name (a dangling link included) is skipped | A2 |
| `export_roadmap_md.reexport_roadmap_md` and `main` → `safe_write.write` | `roadmap.md` | export | yes | A2 |
| `digest_cli._write_output` → `safe_write.write` | `roadmap-context.md`, a relative or in-checkout `-o` | digest | yes | A2 |
| `digest_cli._write_output`, plain write | an explicit absolute `-o` outside the checkout | digest | deliberately not | A2: the person's own destination |
| **`history_cache.save_cache` / `ensure_cache_dir`** (`mkdir`, `write_text`, `mkstemp` + `os.replace`) | `.specyrd/cache/`, `.specyrd/cache/.gitignore`, `.specyrd/cache/roadmap-history.json` | digest (through `render_digest` → `history_index`); init project `--force`, pickup and upgrade (through `regenerate_generated_files`) | no: **owned by M21.39** (coordinator decision 2026-11-06; M21.39's acceptance on WIP covers `save_cache` and `ensure_cache_dir`), not changed here | outside this leaf's touch zones. Reproduced: with `.specyrd/cache` linked to an outside directory, `digest` writes `roadmap-history.json` and `.gitignore` there, exit 0; with `.specyrd/cache/.gitignore` a dangling link, it creates the outside target |
| `refresh_schemas.refresh_schemas` → `safe_write.copy` | `schemas/*.json` | refresh-schemas, upgrade | yes, all checked before the first copy | A2 |
| `specyrd_init._save_manifest` → `safe_write.write` | `.specyrd/manifest.json` | specyrd init, init project (`_record_layout`), refresh-stubs | yes; specyrd init and init project check it before the first write; refresh-stubs writes it last, and a refusal is exit 1 | A2 |
| `specyrd_init._write_readme_and_gui_stub` → `safe_write.write` | `.specyrd/README.md` | specyrd init | yes, checked before the first write | A2 (round 9) |
| `specyrd_init._write_readme_and_gui_stub`, plain write | `~/.specy-road/gui-settings.json` | specyrd init `--extras gui` | deliberately not | in `$HOME`, not in a tree specy-road owns; written only when absent; not named by A1 or A2 |
| `specyrd_skills.install_stubs` → `safe_write.write` (through `skill_path`) | canonical `SKILL.md` files, generic stub files | specyrd init, refresh-stubs (`_write_if_changed`) | yes, under the skills-link rule; specyrd init checks all of them first (`check_install_paths`) | A1, A2 |
| `specyrd_skills.ensure_link` (`os.symlink`, `unlink`, `rmtree` of its own copied fallback, `_symlinks_work` probe) | `.claude/skills/<name>` links | specyrd init, refresh-stubs | the path is checked by `skill_path` (every ancestor real, and the skills-link text); the link itself is created by `os.symlink` | A1/A2: "the is_link_path branch keeps ensure_link"; its copy fallback goes through `safe_write.write` |
| `refresh_stubs._prune` (`safe_write.remove`, `prune_empty`; `shutil.rmtree` of a real orphan directory after `check`) | recorded orphans, verbatim `.cursor`/`.codex` skill copies | refresh-stubs `--prune`, upgrade `--prune` | yes; every orphan is checked before the first delete | A2 |
| `agent_ignores.apply_agent_ignores` → strict `managed_block` → `safe_write.write` | `.gitignore`, `.cursorindexingignore` | init project, specyrd init, refresh-stubs | yes; init and specyrd init check both first (`check_ignore_files`) | A1 |
| `agents_md_block.apply_agents_files` (`resolves_outside`, `mkdir`, `write_text`) | `AGENTS.md`, `.specyrd/AGENTS.md`, `.specyrd/AGENTS.team.md` | init project, specyrd init, refresh-stubs | deliberately not | A1 keeps `resolves_outside` for `agents_md_block`: a link out is a `refused` report line; an in-repo alias is kept |
| `agent_guide_block.apply_agent_guide_block` (`resolves_outside`) | `CLAUDE.md` | specyrd init `--ai claude-code`, refresh-stubs | deliberately not | A1, as above |
| `specyrd_hooks._write_json` → `safe_write.write` | `.claude/settings.json`, `.codex/hooks.json`, `.cursor/hooks.json` | specyrd init `--install-orchestration-hooks` | yes, checked before the first write (`hook_destinations`) | round 10, Sol-high |
| `specyrd_hooks.install_orchestration_hooks` → `safe_write.write` | `.specyrd/hooks/<agent>/README.md` | same | yes, as above | round 10 |
| `specyrd_hooks.install_pre_push_hook` → `safe_write.write` | `.git/hooks/pre-push` | specyrd init `--install-pre-push-hook` | yes, as above | round 10 |
| `refresh_stubs._block_previews` | a temporary directory | refresh-stubs `--diff` | n/a | temporary directory; reads the checkout only |

Regression rows, one per writer class, final link and linked parent:

| Writer class | Final symlink | Symlinked parent |
|---|---|---|
| template copy | `test_init_project_refuses_a_link[final-link-out]` | `[docs-parent-link]`, `[schemas-parent-link]` |
| schema copy | `test_schema_refresh_and_upgrade_refuse_a_linked_schema[schema-link-out]` | `[schemas-dir-link]` |
| manifest | `test_specyrd_init_refuses_a_linked_manifest_or_ignore_file[file-link-out]`, and new `test_init_project_refuses_a_link[manifest-link-out]` | `[specyrd-dir-link]`, and new `test_init_project_refuses_a_link[specyrd-parent-link]` |
| `.specyrd/README.md` | `[readme-link-out]` | `[specyrd-dir-link]` (the same directory) |
| ignore files | `[gitignore-in-repo-link]` (init and specyrd init) | n/a: they sit at the git root |
| generated files | `test_export_and_digest_refuse_a_linked_output[*-final-link-out]`, the pickup rows | `test_digest_refuses_a_linked_relative_output[parent-link]`; `roadmap.md` itself sits at the project root |
| stubs and skill files | `test_managed_writes_refuse_a_symlink_out_of_the_repo` (SKILL.md, refresh and specyrd) | its `.claude/skills` and `.agents/skills` dir rows; the shape table; the m13_7 linked-generic-parent rows |
| skill links | n/a: a link is the kind expected at that name, and a foreign one is `skipped (not ours)` | the shape table (`outward`, `relative-alias`, `pair-under-linked-parent`, …) |
| hook files | `test_specyrd_init_refuses_a_linked_hook_destination[*-final]` | `[*-parent]` |
| prune | `test_safe_write` (a symlink orphan is removed as an entry, its target intact) | `test_upgrade_prune_refuses_an_orphan_under_a_linked_directory` |
| archive restore | `[chunk-out]`, `[origin-linked]`, `[stored-linked]` | `[phases-linked]`, `[unpack-linked]` |
| history cache | none here: owned by M21.39 | none here: owned by M21.39 |

### History cache: owned by M21.39

- Coordinator decision (2026-11-06): `history_cache.save_cache` and `ensure_cache_dir` belong to M21.39, whose acceptance on WIP now covers them. They are not changed in this leaf. The same helper is also used by the pickup hint (`on_complete_pickup`), the brainstorm lock, `search_index` and `context_notice_cache`.
- No writer reachable from these entry points belongs to M21.38 (review writers).

### Probes (writer audit)

- The `strace` runs listed above, in a scratch repo: every write path is in the table. Result: the only writer that is neither on the rule nor deliberately excluded is the history cache, which M21.39 owns.
- `digest` with `.specyrd/cache` linked to an outside directory. Result: `roadmap-history.json` and `.gitignore` were written outside, exit 0.
- `digest` with `.specyrd/cache/.gitignore` a dangling link to outside. Result: the outside target was created, exit 0.
- `export` and `refresh-schemas` (already current) under `strace`. Result: no write other than their outputs.
- An incident during the audit: my first `strace` run inherited `SPECY_ROAD_REPO_ROOT` (this worktree's `sr/`). `init project --force` and `digest -o docs/d.md` therefore wrote into the worktree's `sr/`. I restored the 18 modified tracked files with `git checkout HEAD --` and removed the 7 new untracked files they created. The precondition status was clean before, and none of those files is ignored. The precondition check is clean again. The main checkout was not touched (checked by ctime). The rerun unset the variable and checked the worktree's status before and after: unchanged.

## Fix round 11 (review `gpt-5.6-sol-high` at `49e2481b`; `gpt-6.1-sol-low` at `e3f70e09`; `grok-4.7-high` at `85466059`)

Commit `18fd2053`.

- **Sol's finding.** Archive restore preflighted each path lexically and threw away the path `safe_write.check` returned. The later steps used other spellings of the same path: `(root / rel).resolve()` in `_shallow_view`, `_write_back`, `_restore_planning_sheets` and the `src` it unlinks, the raw join in `archive_planning_dir`'s `rmtree`, and the raw capsule join in `undeepen_archive`. Take `origin = planning/jump/../victim.md` with `planning/jump` linked to an outside directory. The check saw `planning/victim.md`, but the move replaced `<outside>/../victim.md`.
- **The class.** A path that is checked under its lexical spelling and then used under its raw or resolved spelling. The two differ only when a `..` follows a symlinked component.
- **The fix, a design change in `archive_restore`.** A new `_checked(root, rel, expected)` returns the path `safe_write.check` gives. Every read, write, move, unlink and `rmtree` in restore uses that returned path: no `.resolve()` and no raw join is left in the module. The parent `mkdir`s go through `safe_write.mkdirs`. `_checked` also refuses a path whose checked form differs from `resolved root / rel`, which means a `..` component. The reason is that `undeepen_archive` (outside the zones) and `archive_planning_dir` re-join the raw record strings. Refusing those spellings means the raw spelling and the checked path always name the same file, even in code this module cannot change. Archive writes these paths in normal form, so no record it writes is affected.
- **Test.** `test_archive_restore_refuses_before_the_first_change` gains the `origin-cancelled` layout (Sol's reproduction): `planning/jump -> outside/inner`, with origin `planning/jump/../<sheet>`. It asserts the refusal names the path and that the repository, the outside tree and the ledger are unchanged. Red-green: with `archive_restore.py` from `49e2481b` the row fails; with the fix it passes.
- **Sol R1/R2 and grok's README finding (earlier commits).** Resolved in rounds 7 and 9 and still in place at this tip:
  - R1: the exact-text skills-link rule; `dotdot-through-link` is refused.
  - R2: `git-dir` is refused consistently, because A1 allows only the two link texts.
  - Grok's README finding: `.specyrd/README.md` is preflighted and written through `safe_write.write`, with `readme-*` rows.
  - Their rows in the shape table and the specyrd table pass at `18fd2053`.

### Probes (fix round 11)

- Every `safe_write.check`, `check_all` and `refused` caller in the package, checked for whether it uses the returned path or keeps writing through `safe_write`. Results:
  - `refresh_stubs._prune` and `specyrd_hooks` use the returned path.
  - `init_project`, `refresh_schemas`, `specyrd_init`, `agent_ignores` and `managed_block` (strict) write through `safe_write.write`/`copy`, which walk again and write to the path they walked.
  - The names they check are fixed or come from template enumeration, with no `..`.
  - Not reachable.
- `specyrd_skills.skill_path`: `link.parent / allowed`, where `allowed` is the fixed text `../.agents/skills` or `../.claude/skills`. Its `..` cancels `.claude` or `.agents`, which `check(repo_root, link, None)` has just verified to be a real directory. So the lexical and OS meanings agree. Not reachable.
- `upgrade_plan.check_changes` / `apply_plan`: every `e.target` comes from `Mirror.to_real` of an `os.walk` path (no `followlinks`, no `..`) or from `os.path.realpath`. So the checked and applied spellings are the same. Not reachable.
- `digest -o sub/link/../f` (relative): `safe_write.write` writes the lexical `sub/f` that it checked, inside the checkout. That can differ from the OS meaning of what the user typed, but it never leaves the checked path. Recorded, not changed (A2 keeps relative `-o` on the rule).
- Deep restore: the capsule path, the unpacked chunk, `refs/<id>.json`, and `stored` and `origin` derived from the capsule all go through `_checked` before `undeepen_archive` runs. A `..` anywhere in them, or in the archive id, is refused before the first change.
- Leaf tests plus the archive suites: 383 passed. Full suite (`pytest -n 4`): 6168 passed. `ruff check specy_road tests`: pass. `specy-road file-limits`: OK.

### Caller audit (coordinator, round 11)

Commit `9a2fcfbc` adds the rows. This table covers every caller of `safe_write.check`, `check_all` and `refused`, and of `managed_block.refused_link`, which is `refused` under another name, in `specy_road/` at this tip. The question for each is whether the path is used again, after the check, in a spelling other than the one checked. The two spellings can differ only when the raw path has a `..` after a symlinked component, so "fixed name" below means a constant or bundled name with no `..`.

| Caller | What it uses after the check | Verdict |
|---|---|---|
| `archive_restore._checked` / `_preflight`, `_shallow_view` (chunk read), `_deep_view` (capsule read), `_write_back` (target chunks), `_restore_planning_sheets` (stored, origin), `restore_archive` (`src` unlink, planning dir `rmtree`) | Before: the raw join or `.resolve()` of the record's spelling, plus raw re-joins in `undeepen_archive` (capsule, chunk, refs, planning) and `archive_planning_dir`. Now: only the path `check` returned, and `_checked` refuses a `..` spelling, so the raw re-joins outside the zones name the same file. | **Fixed** (`18fd2053`). Rows: `origin-cancelled`, `chunk-cancelled`, `stored-cancelled` (shallow), `capsule-cancelled` (deep). All 4 fail with the `49e2481b` restore. |
| `archive_restore._prune_empty_archive` | `root / roadmap/archive` (constant, checked as a directory in the preflight); `os.walk` entries, kept only when real directories by `lstat`; `safe_write.remove` for the ledger | Safe |
| `restore_archive` → `_sync_includes`, `write_archive_index` | `manifest_path` / `archive_dir` (constant names; `resolve()` equals the lexical path because `roadmap/` and `roadmap/archive/` were checked as real directories) | Safe |
| `refresh_stubs._prune` | the path `check` returned, for `rmtree`, `safe_write.remove` and `prune_empty` (orphans come from the manifest and may have `..`) | Safe |
| `specyrd_hooks.merge_harness_hooks` | the returned `dest`, for the JSON read and `_write_json` (`safe_write.write`) | Safe |
| `specyrd_hooks.install_pre_push_hook` | the returned `dest`, for its mode and `safe_write.write` | Safe |
| `specyrd_skills.skill_path` (all branches) | returns the path `check` returned; `link.parent / allowed` is the fixed text whose `..` cancels `.claude` or `.agents`, which the line before verified to be a real directory | Safe |
| `skill_path` callers: `check_install_paths`, `install_stubs`, `ensure_link`, `refresh_stubs._write_if_changed`, `refresh_stubs_report._refused` | the returned path for every write (`safe_write.write`) and link; the report's `resolve_linked` only reads raw paths for display | Safe |
| `specyrd_skills.mirrored_copies` (`refused` on a mirror dir) | fixed `MIRROR_DIRS` and bundled skill names; it only lists the copies, and deleting them goes through `_prune` | Safe |
| `init_project._copy_templates` | `out` from template enumeration (no `..`) for `lexists`; write through `safe_write.copy`, which walks again | Safe |
| `init_project._scaffold` (manifest, generated files under `--force`) | fixed names; written later through `safe_write.write` | Safe |
| `agent_ignores.check_ignore_files`, `managed_block._read` (strict) | fixed names at the git root; read raw (same file), written through `safe_write.write` | Safe |
| `specyrd_init._refuse_unsafe_paths` | fixed `.specyrd` names and `hook_destinations` (constants); written through `safe_write.write` / `specyrd_hooks` | Safe |
| `refresh_schemas.refresh_schemas` | `schemas/<bundled name>`, read raw for comparison (same file), written through `safe_write.copy` | Safe |
| `upgrade_plan.check_changes` / `apply_plan` | `locate(e.target)`; every target is `Mirror.to_real` of an `os.walk` path (no `followlinks`, no `..`) or an `os.path.realpath` | Safe |
| `upgrade._copy_load_order_docs` (`refused_link`) | `docs/<bundled rule path>`, written through `safe_write.copy` | Safe |
| `upgrade` `digest --check` gate, `upgrade_generated.regenerate`, `generated_files.refused_generated_files` / `regenerate_generated_files` (`refused_link`) | fixed `roadmap.md` / digest names; read raw (same file), written through `safe_write.write` | Safe |
| `review_rejected` and `review_delegate_packet` (`refused_link`) | review writers, outside the zones (M21.38) | Not audited here: M21.38 owns them |
| `archive_ops` and `archive_deep` (archive, deepen) | not callers of the rule: they use `resolve()` and `resolves_outside`, outside the zones | Out of scope: not on the rule in this leaf. Restore no longer hands them a `..` spelling. |

`history_cache.py` was not changed (M21.39).

## Fix round 12 (review `gpt-5.6-sol-high` at `6d9c2556`; `gpt-6.1-sol-low` at `e3f70e09`; `grok-4.7-high` at `85466059`)

Commit `a787ec3f`.

- **Sol's finding.** `managed_block._write` caught every `OSError` from the strict write as `failed`. A `.gitignore` swapped to a link after the preflight was refused by `safe_write`'s re-check before replace (outside bytes safe), but `refresh-stubs` reported `.gitignore (failed)` and exited 0.
- **The class.** A `SafeWriteError` from a write that runs after the command's preflight, turned into an outcome that is not an error. It reaches every caller of the strict managed block: `refresh-stubs`, `upgrade` and `upgrade --dry-run` (via `refresh_stubs`), and `init project` and `specyrd init` (via `agent_ignores.apply_and_report`).
- **The fix.** `_write` keeps the error as `refused: <why>`, which is the outcome `_read` already gives for the same refusal. `refresh-stubs` and `upgrade` already turn that outcome into `error:` and exit 1 (`rule_refusal`). `init project` and `specyrd init` reported it as a line and exited 0. They now call a new `managed_block.raise_rule_refusal(written)` after `apply_and_report`, which raises `SafeWriteError`. Both commands already print that as `error:` and exit 1 (`_scaffold`'s handler and `exit_on_refusal`). In `specyrd_init` the two calls sit in a new `_apply_ignores` helper, which keeps `run_init` under the 80-line function cap.
- **Test.** New `test_an_ignore_file_linked_right_before_replace_is_an_error`, with 5 rows: `refresh-stubs`, `upgrade`, `upgrade --dry-run`, `specyrd init` and `init project --force`. Each row makes `.gitignore` stale. It patches the public `os.chmod`, the step just before the re-check, the same hook as the primitive's swap test, so that when the `.gitignore` temp file is chmod'ed the destination is swapped to a link to an outside file. It asserts exit 1, an `error:` line naming `.gitignore is a symlink`, no traceback, and the outside bytes unchanged. Red-green:
  - With `managed_block.py` from `6d9c2556`, all 5 rows fail.
  - With the `managed_block` fix but without the `raise_rule_refusal` calls, the two init rows fail.
- **Sol R1/R2 and grok's README finding (earlier commits).** These were fixed in rounds 7 and 9 and are unchanged at this tip. Their rows still pass: the shape table's `dotdot-through-link` and `git-dir` (both refused under A1's two-value rule) and the `readme-*` layouts.

### Probes (fix round 12)

- `managed_block.apply_managed_block`, `_read`: strict mode already maps `SafeWriteError` to `refused: <why>`. Consistent with the fix.
- `managed_block.remove_managed_block`: non-strict, so it never calls `safe_write`. Not reachable.
- `agent_ignores._seed`: a swap at seed time is caught as `OSError` and returns `False`. The strict block that follows then reads the path through `_read`, which refuses the link as `refused: <why>`, so the class is closed there too. Not changed.
- `refresh_stubs._write_if_changed`: already maps `SafeWriteError` to `refused: <why>` (line 133), which `_exit_on_rule_refusals` turns into exit 1. Consistent.
- `specyrd_skills.ensure_link`: `except OSError` covers only `os.symlink`. Its fallback `safe_write.write` raises past it to `exit_on_refusal`. Not swallowed.
- `init_project._scaffold` (`except (OSError, RuntimeError)` → `error:`), `upgrade_plan` line 272 (names the checkout path), `specyrd_init._refuse_unsafe_paths`: each turns a refusal into an error. Consistent.
- `specyrd_init._load_manifest`, `refresh_schemas` line 55, `upgrade` line 260, `upgrade_plan` lines 43 and 159, `specyrd_skills` lines 203, 212 and 311, `archive_restore` line 107: reads or probes only, with no `safe_write` write inside the `try`. Not reachable.
- `AGENTS.md` / `CLAUDE.md` blocks (non-strict, `resolves_outside`): `_plain_write` never raises `SafeWriteError`. Out of the class.
- Full suite (`pytest -n 4`) at the fix: 6176 passed. `ruff check`: pass. `specy-road file-limits`: OK.

## Touch zones

All edits are inside the listed zones (`specy_road/specyrd_hooks.py` added in round 10). No file outside them needed changing, and no new module beyond `specy_road/safe_write.py` (already listed). `specy-road file-limits` passes.

## Verification

- `pytest -n 4` full suite at `a787ec3f`: 6176 passed.
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
- Fix round 7: `specyrd_skills.SKILLS_LINK_TEXT` (the two allowed link texts, replacing `SKILLS_DIRS`); in `skill_path`, the exact-text branch (A1, removes the R1/R2 class); in `ensure_link`, the `link == canonical` guard (one skills directory linked to the other: no self-loop link, and dry and real runs agree). Tests: the shape table's `pair`, `absolute-pair`, `pair-under-linked-parent`, `relative-alias`, `dotdot-through-link` (R1) and `git-dir` (R2) rows, and the `OTHER_SKILLS` helper map; no mock.
- Fix round 8: `safe_write.loop_refusal` (a loop met before the rule, as the rule's refusal; the class), `safe_write._loops` (its `stat` test) and `safe_write.refusal_of` (one boundary call for `exit_on_refusal` and `init project`); `refresh_stubs_report._refused` (the report resolves only a path the rule allows); `exit_on_refusal` at the `refresh-stubs`, `refresh-schemas` and `upgrade` mains and on `specyrd_init.run_init`; the loop branch in `upgrade_plan.make_plan` (names the checkout's path). Tests: the `cycle` shape row (6), the m13_7 `self-loop` parameter (2), `test_a_symlink_loop_on_a_managed_path_is_refused_without_a_traceback` (11 rows: each a traceback before) and `test_a_symlink_loop_is_refused_as_the_looping_link` (3); no mock.
- Fix round 9: the `.specyrd/README.md` check in `specyrd_init._refuse_unsafe_paths` and its `safe_write.write` (grok: a linked README was written through). Tests: the `readme-link-out` and `readme-dangling` layouts and the `force` parameter in `test_specyrd_init_refuses_a_linked_manifest_or_ignore_file` (7 more rows); no mock.
- Fix round 10: `specyrd_hooks.hook_destinations`, used by the preflight; the `guard_hooks` and `pre_push` arguments of `specyrd_init._refuse_unsafe_paths`; the safe-write calls and the pre-check before the harness JSON is read in `specyrd_hooks`; the pre-push mode branch, so the file keeps its own mode or the umask's, plus execute bits. Test: `test_specyrd_init_refuses_a_linked_hook_destination` (10 rows); no mock.
- Writer audit: the `manifest-link-out` and `specyrd-parent-link` rows in `INIT_LAYOUTS` (the init-project manifest class, final and parent; they pass on the current code, coverage only); no helper, no mock.
- Fix round 11: `archive_restore._checked` (returns the checked path, used for every restore operation, and refuses a `..` spelling that a raw re-join elsewhere would read differently), replacing the old `_check` body; `safe_write.mkdirs` for the restore's parent directories. Tests: the `origin-cancelled` (Sol's reproduction), `chunk-cancelled`, `stored-cancelled` and `capsule-cancelled` (deep) layouts in `test_archive_restore_refuses_before_the_first_change`, plus their `_cancelled` setup helper (the coordinator's caller audit: one row per restore path the fix covers); no mock.
- Fix round 12: the `SafeWriteError` branch in `managed_block._write` (a refusal at replace is `refused: <why>`, not `failed`); `managed_block.raise_rule_refusal` (one call for `init project` and `specyrd init`, so a rule refusal outcome exits 1 the way `refresh-stubs` and `upgrade` already do); `specyrd_init._apply_ignores` (keeps `run_init` within the function cap). Test: `test_an_ignore_file_linked_right_before_replace_is_an_error` (5 rows: refresh-stubs, upgrade, upgrade --dry-run, specyrd init, init project --force); it patches the public `os.chmod` to swap the link in.
- Mocks: `os.chmod` (monkeypatch, restored) in the swap tests; `sys.argv` for `export_roadmap_md.main`. No call counts or order are asserted.
