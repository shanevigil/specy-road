# Implementation summary: M11.29 (`doctor-version-skew`)

## Goal

Warn when the running `specy-road` is **older** than the version recorded in the consumer repo (`.specyrd/manifest.json` and/or the `AGENTS.md` managed block), name both versions and the usual PATH shadowing cause, state the minimum in generated stubs, and document a supported isolated CLI install.

## Acceptance

- **A1:** `specy-road doctor` prints one stderr warning before other output when running `< recorded; message names running and recorded versions, where recorded, PATH cause, and reinstall hints (`pipx` / `uv tool`).
- **A2:** The generated `AGENTS.md` block states the minimum on the existing “Written by specy-road” line (`(minimum <version>)`); `specy_road/cli.py` warns once per invocation for every registered command except `doctor` (which warns in its subprocess); `doctor.py` calls the shared helper at the start of `cmd_doctor`.
- **A3:** `README.md` and `docs/install-and-usage.md` document `pipx` / `uv tool install` plus `which specy-road` / `specy-road --version`. Tests cover older, equal, and newer recorded versions.

## Touch zones (confirmed)

`specy_road/bundled_scripts/doctor.py`, `specy_road/cli.py`, `specy_road/templates/`, `README.md`, `docs/install-and-usage.md`, `tests/` — accurate; version comparison lives in `cli.py` (within zone) and is invoked from `doctor.py`.

## Verification

- `pytest tests/test_enforced_rules_pointers.py::test_the_meter_reports_a_shorter_section_than_before tests/test_doctor_version_skew.py tests/test_agents_md_block.py tests/test_doctor.py`
- `specy-road file-limits`

## Review required_changes (Codex Sol)

Round 1, `6a99f7a1`:

- **R1:** `_MINIMUM_LINE` captures the version before the sentence period. Test: `test_warns_when_the_minimum_is_newer_than_written_by_and_the_manifest`.
- **R2:** `_repo_root_from_argv` accepts `--repo-root=PATH`.
- **R3:** Entry-point tests run `python -m specy_road.cli`; no private patches. Test: `test_doctor_emits_the_skew_warning`.
- **R4:** `test_silent_when_running_is_newer_than_every_recorded_source`; docs no longer claim `--version` warns.

Post-approval meter (WIP trial merge), `a4e9ed49`:

- Folded the minimum into the Written-by line (`(minimum <version>)`) so the managed block stays 51 lines / under 7679 bytes. Test: `test_the_meter_reports_a_shorter_section_than_before`.

Round 2, `999cfddb`:

- **R1:** Manifest read in `recorded_toolkit_version` treats missing, empty, invalid JSON, and non-UTF-8 as skip-and-continue to AGENTS.md (same decode/parse failures on AGENTS.md skip to the manifest). Tests: `test_unreadable_manifest_still_warns_from_agents_md` (public CLI `validate --help`), `test_unreadable_agents_md_still_warns_from_the_manifest`.
- **R2:** Removed `test_cli_warns_for_both_repo_root_spellings`; space and equals `--repo-root` live on `test_warns_when_the_running_version_is_older_than_the_manifest` (`99.0.0` space, `0.3.1rc99` equals).

## Added

- `_version_sort_key` / `recorded_toolkit_version` / `warn_if_running_version_older` in `specy_road/cli.py` — PEP-440-ish compare and read manifest + AGENTS.md block for the recorded minimum.
- `_repo_root_from_argv` / `_maybe_warn_running_version_older` in `specy_road/cli.py` — one warning per CLI invocation (skip `doctor`; doctor subprocess warns separately).
- `cmd_doctor` call to `warn_if_running_version_older` — A1 via `specy-road doctor`.
- `(minimum {{SPECYRD_VERSION}})` on the existing Written-by line in `agents-md-block.md` — A2 stub text without adding a line.
- Maintainer install / PATH prose in `README.md` and `docs/install-and-usage.md` — A3.
- `_read_text` in `specy_road/cli.py` — nonfatal UTF-8/OSError read of manifest and AGENTS.md for the advisory check.
- `tests/test_doctor_version_skew.py` — public CLI coverage of older, equal and newer recorded versions, both `--repo-root` spellings, a newer AGENTS.md minimum, and unreadable manifest/AGENTS.md files.
- Assertion for `(minimum <version>)` in `tests/test_agents_md_block.py::test_fresh_init_project_writes_agents_md_with_the_block` — template ships the minimum on the Written-by line.
