# Implementation summary: M11.43 — init project reports exactly what it writes

Branch `feature/rm-init-project-reports-writes`, base `36c36470`, change commit `aee5b371`.

## What changed

- **One reported list (A1).** `run_init_project` now collects every path it creates or changes into one list and prints it with the same text in both modes (`would write <entry>` / `wrote <entry>`): the template files, `AGENTS.md (<outcome>)`, `.cursorindexingignore (<outcome>)`, `.gitignore (<outcome>)` and `.specyrd/manifest.json (<outcome>)`. The ignore blocks go through `agent_ignores.apply_and_report`, as `specyrd init` does. The dry-run count line now counts that list (`dry-run: N path(s) would be written or changed under <root>`), and skipped files are listed in both modes. Paths are relative to the git root, so a nested project reports `sr/roadmap/...` and `.gitignore` (the old dry run printed absolute paths, the real run dst-relative ones).
- **Outcomes are the same in both modes.** For a new `AGENTS.md` the real run wrote the H1 first, so the block reported `updated` where the dry run said `created`; `init_project` now reports a file that did not exist as `created`. The manifest's outcome is worked out by comparing the bytes `_save_manifest` would write with the file on disk, so an unchanged manifest is not listed.
- **The dry run finds the git root (A1, A3).** The git root is now looked up from the nearest existing ancestor of the project directory, so `--dry-run` into a directory that does not exist yet (`init project sr`) sees the same repository as the real run.
- **`.gitignore` (A2).** The template's four run-time rules (`work/.on-complete-*.yaml`, `work/prompt-*.md`, `work/pr-body-*.md`, `work/.milestone-session.yaml`) moved into the git-root managed block (`agent_ignores.SESSION_WORK_FILES` in `GITIGNORE_LINES`), and the block's note now mentions them. The template `.gitignore` keeps all of its original explanatory comments, including the review hand-off note (`docs/orchestration.md` pointer; approving reviews recorded as Reviewed-by trailers on the mark-implementation-reviewed commit). Each comment now names the path it explains, and a short header points to the managed block. Only the rule lines are gone. The template is never copied. When the roots coincide and `.gitignore` is missing, it is the start of the new file, with the block applied below it, and it is reported as `created`. An existing `.gitignore` is reported as `updated` when its block changes, never `skipped (exists)`. The blocks are now always applied: before, they were applied only when one of the ignore files already existed at the git root.
- **Nested layout (A3).** When the project root sits below the git root, nothing is written to `<project>/.gitignore`: the git-root block carries the rules with the `sr/` prefix. The template header is not used there, because its comments name unprefixed paths.
- **Outside a git repository** the project directory is used as the root: the blocks are written there with no prefix, so the `.gitignore` still holds the rules, as before. No manifest is recorded, as before.
- `run_init_project` was split into `_copy_templates`, `_apply_agents_md`, `_profile_selection` and `_record_layout` (which now reports). That brings it under the C901 limit, so the `# noqa: C901` baseline comment is gone.
- `docs/pm-workflow.md`: one sentence in the layouts paragraph about the nested `.gitignore` and the dry-run listing.

Existing consumer repos: `refresh-stubs` will show their `.gitignore` block as updated, because the block has four more rules.

## Touch zones (final)

All the edits are inside the listed zones: `specy_road/init_project.py`, `specy_road/agent_ignores.py`, `specy_road/templates/project/.gitignore`, `tests/` (new `tests/test_init_project_reports.py`) and `docs/pm-workflow.md`. No new module. `file-limits` passes.

## Verification

- `pytest -n auto`: 3301 passed, 2 skipped (exit 0).
- `pytest -q tests/test_init_project_reports.py tests/test_init_project_gitignore.py tests/test_agent_ignores.py tests/test_agents_md_block.py tests/test_project_layouts.py tests/test_init_profiles_subset.py tests/test_package_data_dotfiles.py`: 95 passed (re-run after restoring the template comments for the gpt-6.1-sol review, R1).
- `specy-road file-limits`: OK.
- `ruff check specy_road/init_project.py specy_road/agent_ignores.py tests/test_init_project_reports.py`: clean.
- Red-green: all 6 new tests fail against base `36c36470`. The check ran on a `git archive` copy of the base with the new test file, which defines `SESSION_WORK_FILES` inline because the base has no such constant.

## Added

### Helpers
- `init_project._MANIFEST`: the manifest's path, used for both the comparison and the reported entry.
- `init_project._record_layout(top, prefix, written, *, dry_run)` (reworked): reports the manifest's outcome, and under dry run reports without writing.
- `init_project._apply_agents_md`: reports AGENTS.md, and reports a file that did not exist as `created`, so the dry run and the real run agree.
- `init_project._copy_templates`: the template copy loop, which now leaves `.gitignore` out and returns git-root-relative entries. Taken out of `run_init_project` to keep it under the complexity limit.
- `init_project._profile_selection`: the `--profiles` parsing that used to be inline, taken out for the same reason.
- `agent_ignores.SESSION_WORK_FILES`: the four run-time rules moved from the template, so the tests can name them.
- `agent_ignores._seed`: starts a missing `.gitignore` with the template header. It never writes through a symlink, and it reports whether the file is new.
- `gitignore_seed` keyword on `apply_agent_ignores` / `apply_and_report`: lets `init project` give the header without a second code path.

### Branches / guards
- `.gitignore` is never copied as a template file (`rel == _GITIGNORE` skip), so a nested project gets no `.gitignore` of its own (A3).
- The header is used only when the prefix is empty, because its comments name unprefixed paths.
- A seeded file whose block reports `updated` is reported as `created`, so it matches the dry run.
- The git root is looked up from the nearest existing ancestor, because the dry run's target may not exist yet.
- The ignore blocks are applied unconditionally, at the git root or at the project directory outside a repository. Before, they were applied only when an ignore file already existed, so a nested project without a git-root `.gitignore` would have lost its rules.

### Mocks
- none

### Tests (`tests/test_init_project_reports.py`)
- `test_dry_run_lists_what_the_real_run_writes[False|True]`: A1. The dry-run list equals the real list, its count equals the number of lines, it names the four managed paths, and it matches the files actually created or changed, on an empty repo and on one with an existing `.gitignore`.
- `test_dry_run_matches_outside_a_repository`: the same match when the directory is not in a git repository.
- `test_existing_gitignore_reported_as_updated_with_the_runtime_rules`: A2. An existing `.gitignore` is reported as `updated`, not skipped, its own lines are kept, and its block holds the four rules.
- `test_fresh_gitignore_keeps_the_template_header_and_one_copy_of_each_rule`: a new `.gitignore` starts with the template header and holds each rule once.
- `test_nested_layout_writes_no_project_gitignore`: A3. A nested project gets no `sr/.gitignore`, the git-root block holds the rules with the `sr/` prefix, and the dry run equals the real run.
