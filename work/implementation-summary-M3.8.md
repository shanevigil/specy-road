# Implementation summary for M3.8

## Summary

`upgrade` and `validate` now separate a deliberate upgrade from an accidental one, and no longer send adopters to files they do not have:

- **A1:** `validate` prints one warning when the running version differs from the repo's declared pin. The pin is `"pin"` in `.specyrd/manifest.json`; without one, it is the first `specy-road==` line in a `requirements*.txt` at the checkout root (files read in sorted order; extras and spaces are accepted).
- **A2:** The stale-`AGENTS.md` warning now reads "has a specy-road section that differs from what specy-road <version> writes".
- **A3:** `upgrade` has a new "shipped docs" step after `refresh-profiles`. It copies the `docs/` files named in this version's load order (today `docs/supply-chain-security.md`) when they are missing, and never overwrites. `validate` warns once, naming every load-order path in the project's `AGENTS.md` block that does not exist. The `planning/<id>_…` placeholder is skipped because it names no file. Generated files (`roadmap-context.md`) are also exempt, as the amended A3 states: `digest --check` (which `upgrade` runs) already reports a missing digest, and `init project` does not write one, so without the exemption a fresh scaffold would fail `validate --strict`.
- **A4:** `refresh-stubs --dry-run` (and so `upgrade --dry-run`) prints `migration: N command stubs (*/commands/) become M skills under .agents/skills/` when pre-0.3.0 command stubs are among the orphans.
- **A5:** When a list field (`acceptance`, `risks`, `touch_zones`, `dependencies`) is given a value that parses as a JSON list, `edit-node` prints a `[note]` through the existing `notify` callback. The value is still stored as text, as before.
- **A6:** `warn_stale_parent_status` fires only when exactly one of the stored status and the rollup is `Complete`. An In Progress parent with a Not Started rollup is quiet.
- **A7:** `specy-road version` is an alias of `--version` and is listed in `--help`. Unknown commands already exit 2 (covered by `tests/test_cli_query_commands.py`), so that half needed no change.

## Changes

Final touch zones, as widened on the integration branch (`a595e6f`):

- `specy_road/bundled_scripts/refresh_stubs.py`: the migration line in `_report`
- `specy_road/agents_md_block.py`: warning wording, `load_order_paths`, `warn_missing_load_order_paths`
- `specy_road/bundled_scripts/upgrade.py`: `copy_missing_docs` and the "shipped docs" step
- `specy_road/bundled_scripts/validate_roadmap.py`: `pinned_version`, `warn_if_pin_differs`, and the call to the load-order warning; `--no-phase-status-warn` help text. The pin reader lives here rather than next to `stubs_are_stale` in `refresh_stubs.py`, because there it took `refresh_stubs.py` to 406 lines, over the 400-line file limit
- `specy_road/bundled_scripts/validate_roadmap_checks.py`: Complete-only disagreement in `warn_stale_parent_status`
- `specy_road/bundled_scripts/roadmap_edit_fields.py`: JSON-list note in `apply_set`
- `specy_road/cli.py`, `specy_road/cli_usage.py`: `version` alias
- `docs/install-and-usage.md`: pin warning, the docs-copy step, the dry-run migration line, and the load-order warning. The file was already exactly at the 400-line cap, so the merged RC/pin paragraph is one unwrapped line, as "Shape the roadmap before authoring it" already is in the same file; it is back at 400 lines
- `tests/`: see Added

Nothing outside these zones was needed.

## Verification

- `python -m pytest -q`: 2214 passed, 2 skipped (exit 0), after the review fix
- `specy-road file-limits`: OK (exit 0)
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK (exit 0). Its one `agents:` warning (the fixture has no AGENTS.md section) was already there on the base commit
- `specy-road export --check` / `digest --check` on the fixture: OK (exit 0)
- Implementation commit: `aa799e6`; review fix (non-UTF-8 requirements test): `f61547d`

## Added

### Helpers
- `validate_roadmap.pinned_version`: reads the declared pin (manifest `pin`, else `requirements*.txt`); A1.
- `validate_roadmap.warn_if_pin_differs`: the single A1 warning, called from `validate_at`.
- `validate_roadmap._REQUIREMENT_PIN`: matches `specy-road==`, `specy_road[extra] == x`, case-insensitive; A1.
- `agents_md_block.load_order_paths`: the concrete paths a block's `### Load order` names. Shared by the validate warning and the upgrade copy, so the two cannot disagree; A3.
- `agents_md_block.warn_missing_load_order_paths`: the single A3 validate warning.
- `upgrade.copy_missing_docs`: the A3 copy step, next to `refresh-profiles`.
- `roadmap_edit_fields._looks_like_json_list`: the A5 shape check (a `json.loads` result that is a list).

### Branches and guards
- `load_order_paths`: leaves out the digest (`roadmap-context.md`). Reason: see A3 above (coordinator decision after the second review; A3 amended on the integration branch). No new test: removing the exemption makes the existing `tests/test_validate_strict.py::test_strict_passes_a_fresh_scaffold`, `tests/test_upgrade.py::test_one_run_clears_every_upgrade_warning` and the fresh-scaffold half of `tests/test_agents_md_block.py::test_validate_names_load_order_files_the_project_lacks` fail. The first two were confirmed by running them with the exemption removed.
- `pinned_version`: skips a `requirements*.txt` that cannot be read (`OSError`/`UnicodeDecodeError`) and keeps looking. Trigger: a requirements file that is not UTF-8, e.g. `pip freeze > requirements.txt` in Windows PowerShell writes UTF-16 (test: `test_validate_reads_past_a_requirements_file_that_is_not_utf8`, added after review; it fails when the `except` stops catching `UnicodeDecodeError`).
- `warn_missing_load_order_paths`: returns quietly when `AGENTS.md` is unreadable (the missing-file case is covered by the dogfood validate tests). With no block it is also quiet, because `warn_if_agents_md_block_stale` already reports that.
- `copy_missing_docs`: skips a destination that already exists or is a link (test: `test_a_doc_the_project_has_is_kept`). Refuses a destination under a symlink that leads outside the repo (test: `test_a_docs_link_out_of_the_repo_is_not_followed`). Copies only `docs/` paths, because the constitution, constraints and shared files are the project's to author.
- `_report`: prints the migration line only on a dry run with old `*/commands/` orphans (A4).
- `apply_set`: notes only for `LIST_KEYS` and only when a `notify` is given (the CLI passes one; the GUI API passes none).

### Mocks
- none

### Tests
- `tests/test_refresh_stubs.py::test_a_dry_run_summarises_the_migration_in_one_line`: A4 through `refresh-stubs --dry-run` (`main`).
- `tests/test_validate_roadmap.py::test_the_declared_pin_comes_from_the_manifest_then_requirements` (3 cases): A1 sources and precedence; a `>=` range is not a pin.
- `tests/test_validate_roadmap.py::test_validate_warns_once_when_the_running_version_is_not_the_pin`: A1, one line with two pinning files, quiet when the pin matches.
- `tests/test_validate_roadmap.py::test_validate_reads_past_a_requirements_file_that_is_not_utf8`: A1 through `validate_at`. A UTF-16 `requirements-dev.txt` sorted before a readable pin: validation passes and emits the one mismatch warning (review finding on `b6652f2`).
- `tests/test_agents_md_block.py::test_validate_warning_states`: A2. The assertion changed from "from another version" to the new wording; the acceptance item changes this behaviour.
- `tests/test_agents_md_block.py::test_validate_names_load_order_files_the_project_lacks`: A3 validate side, quiet on a fresh scaffold, one line naming both missing files.
- `tests/test_upgrade.py`: `_old_repo` now lacks `docs/supply-chain-security.md`. `test_one_run_clears_every_upgrade_warning` asserts the doc is copied, and its existing "no `agents: warning`" check now also covers the load-order warning. `test_dry_run_writes_nothing_and_skips_validate` asserts the would-write line, the A4 migration line, and that nothing was written.
- `tests/test_upgrade.py::test_a_doc_the_project_has_is_kept`, `::test_a_docs_link_out_of_the_repo_is_not_followed`: the two A3 copy guards.
- `tests/test_roadmap_edit_fields.py::test_a_json_looking_list_value_is_noted_and_stored_as_text` (2 cases): A5.
- `tests/test_validate_roadmap.py::test_warn_stale_parent_status_only_on_a_complete_disagreement` (5 cases): A6. It replaces and extends `test_warn_stale_parent_status_quiet_when_aligned` (its Complete/Complete case is the first parameter).
- `tests/test_cli_version.py::test_specy_road_version_flag`: A7, adds `version` to the flags.
