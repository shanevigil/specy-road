---
node_id: M11.43
model: cursor-grok-4.6-high
date: '2026-11-03'
verdict: approve
commit: 8d16db3dcea5a75bff7c3f14f9dd75a8e999ddae
acceptance:
  A1: pass
  A2: pass
  A3: pass
findings:
  correctness: []
  regression: []
  boundary: []
  test_integrity: []
commands_rerun:
- pytest -q tests/test_init_project_reports.py tests/test_init_project_gitignore.py
  tests/test_agent_ignores.py tests/test_agents_md_block.py tests/test_project_layouts.py
  tests/test_init_profiles_subset.py tests/test_package_data_dotfiles.py
- specy-road file-limits
required_changes: []
fresh_session: true
authored_fix: false
is_coordinator: false
notes_sha256: 039252da12a55247ce86a61656e80b7fe23a074fb0c45eddba033bb4581958f4
launch_mode: full
family: xai
independence: distinct-family
---

# Review notes: M11.43

Commit under review: `8d16db3dcea5a75bff7c3f14f9dd75a8e999ddae` on `feature/rm-init-project-reports-writes`. Base `36c36470c19a6259d468a08ad96575d42d92d98e`. This tip restores the template `.gitignore` comments (R1) and refreshes the implementation summary; implementation is `aee5b371`.

## Acceptance

- **A1 pass.** `run_init_project` (the CLI `init project` entry) builds one `written` list and prints the same entries in both modes (`would write` / `wrote`): template copies, `AGENTS.md (<outcome>)`, both ignore blocks via `apply_and_report`, and `.specyrd/manifest.json (<outcome>)`. The dry-run count is `len(written)` and matches the listed write lines. `_apply_agents_md` remaps a missing file from the block's `updated` (H1 written first) to `created`, matching dry-run. Manifest outcome compares disk bytes to `json.dumps(..., indent=2) + "\n"`, the same serialisation `_save_manifest` writes. Git root is taken from the nearest existing ancestor of `dst`, so `--dry-run` into a not-yet-created `sr/` still sees the repo. `test_dry_run_lists_what_the_real_run_writes` parametrizes empty vs existing `.gitignore`, asserts dry == real, count == listed lines, names the four managed paths, and names == files created or changed.
- **A2 pass.** The four run-time rules live in `SESSION_WORK_FILES` / `GITIGNORE_LINES`. An existing `.gitignore` is never copied and never `skipped (exists)`; the managed block is applied and reported `updated`. `test_existing_gitignore_reported_as_updated_with_the_runtime_rules` covers that, keeps `node_modules/`, and checks the four rules inside the block.
- **A3 pass.** `_copy_templates` skips `.gitignore`. Nested prefix is non-empty, so the template header is not seeded; rules land in the git-root block with the `sr/` prefix. `test_nested_layout_writes_no_project_gitignore` asserts no `sr/.gitignore`, dry == real, prefixed session rules, and the file starts with the managed-block marker.

No `human:` items.

## Findings

- **Correctness.** Dry-run vs real outcomes for AGENTS.md and a seeded `.gitignore` are remapped so both modes print `created` (traced: missing file + dry-run → `apply_managed_block` CREATED; real run seeds/writes H1 then block UPDATED → remapped CREATED). Nested dry-run against a missing `sr/` is covered by the A3 test (no mkdir before `_dry_then_real`). Outside a repository, blocks go on the project directory with no prefix and no manifest (`test_dry_run_matches_outside_a_repository`). Packet “uncommitted references” are the four gitignore globs named in prose, not missing files.
- **Regression.** Existing `test_init_project_gitignore.py` (ships rules, `--force` keeps consumer lines), `test_agent_ignores.py`, `test_project_layouts.py` (init ↔ specyrd init order), `test_init_profiles_subset.py`, and `test_package_data_dotfiles.py` still pass in the re-run (95 passed). Blocks are now applied even when the git-root ignore files were missing, which is the nested-layout fix, not a silent behaviour drop. A prior block on this leaf (gpt-6.1-sol R1: restored `docs/orchestration.md` and Reviewed-by trailer notes) is in the tree at this commit.
- **Boundary.** Diff is `specy_road/init_project.py`, `specy_road/agent_ignores.py`, `specy_road/templates/project/.gitignore`, `tests/test_init_project_reports.py`, `docs/pm-workflow.md`, plus the leaf summary. All inside the listed zones (summary lives under `sr/work/`).
- **Test integrity.** No tests deleted or weakened. New tests go through `run_init_project` stdout and files on disk. Packet `new-suppression` on the summary line that mentions the removed `# noqa: C901` is prose, not a code suppression.

Executor-asserted pytest/file-limits were not taken on their own; both were re-run here.

## Excess

Summary has `## Added`. Checked against the diff.

- **Test pins internals.** Not proven. Tests import public `SESSION_WORK_FILES` and `run_init_project`. No `_`-prefixed production names, no mock call counts.
- **Unreachable defence.** Not proven. `_seed`’s `except OSError` is write I/O. `if not text` is the nested / non-init callers (empty `gitignore_seed`). File/symlink guards are path-boundary. The `CREATED if seeded and gitignore == UPDATED` arm is the real run after seeding; dry-run takes `CREATED` from the missing file.
- **Duplicated logic.** Not proven. `_copy_templates` / `_profile_selection` are splits of `run_init_project`. Manifest `json.dumps(..., indent=2) + "\n"` matches `_save_manifest` so dry-run can compare without writing; it is not a second writer. AGENTS.md `created` remapping is the same idea as gitignore seeding, different file.
- **Overlapping test.** Not proven. `test_init_project_ships_a_gitignore` already names the four rules; `test_fresh_gitignore_keeps_the_template_header_and_one_copy_of_each_rule` adds header + uniqueness after the rules moved out of the template. A2’s test adds reporting (`updated` vs skipped) on an existing file. Nested A3 is init-project end-to-end, not `apply_agent_ignores` prefixing.

## Comments / docs

Template `.gitignore` comments were rewritten in-zone as part of moving the rules into the managed block. Compared with base `36c36470`, every original explanatory note is present, including the review hand-off `docs/orchestration.md` pointer and the Reviewed-by trailer sentence on `mark-implementation-reviewed`. Each comment now names the path it explains; only the rule lines moved into the managed block. `_GITIGNORE_NOTE` gained the pickup/finish files. No unrelated docstring squeeze to restore. `docs/pm-workflow.md` adds the nested `.gitignore` and dry-run listing sentence.

## Verify

```
pytest -q tests/test_init_project_reports.py tests/test_init_project_gitignore.py tests/test_agent_ignores.py tests/test_agents_md_block.py tests/test_project_layouts.py tests/test_init_profiles_subset.py tests/test_package_data_dotfiles.py
```

95 passed (exit 0), run on this commit in the leaf worktree.

```
specy-road file-limits
```

OK (exit 0).