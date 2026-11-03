# Implementation summary: M11.29 (`doctor-version-skew`)

## Goal

Warn when the running `specy-road` is **older** than the version recorded in the consumer repo (`.specyrd/manifest.json` and/or the `AGENTS.md` managed block), name both versions and the usual PATH shadowing cause, state the minimum in generated stubs, and document a supported isolated CLI install.

## Acceptance

- **A1:** `specy-road doctor` prints one stderr warning before other output when running `< recorded; message names running and recorded versions, where recorded, PATH cause, and reinstall hints (`pipx` / `uv tool`).
- **A2:** `agents-md-block.md` adds **Minimum specy-road version**; `specy_road/cli.py` warns once per invocation for every registered command except `doctor` (which warns in its subprocess); `doctor.py` calls the shared helper at the start of `cmd_doctor`.
- **A3:** `README.md` and `docs/install-and-usage.md` document `pipx` / `uv tool install` plus `which specy-road` / `specy-road --version`. Tests cover older, equal, and newer recorded versions.

## Touch zones (confirmed)

`specy_road/bundled_scripts/doctor.py`, `specy_road/cli.py`, `specy_road/templates/`, `README.md`, `docs/install-and-usage.md`, `tests/` — accurate; version comparison lives in `cli.py` (within zone) and is invoked from `doctor.py`.

## Verification

- `pytest tests/test_doctor_version_skew.py tests/test_agents_md_block.py tests/test_doctor.py`
- `specy-road file-limits`

## Review required_changes (Codex Sol)

Addressed in `6a99f7a1`:

- **R1:** `_MINIMUM_LINE` captures the version before the sentence period. Test: `test_warns_when_the_minimum_is_newer_than_written_by_and_the_manifest` (public CLI `validate --help`; Written-by = running, minimum `99.0.0`, manifest `0.0.1`).
- **R2:** `_repo_root_from_argv` accepts `--repo-root=PATH`. Test: `test_cli_warns_for_both_repo_root_spellings` (space and equals forms).
- **R3:** Entry-point tests run `python -m specy_road.cli` against temporary projects; no patches of `_context` or `_run`. Tests: `test_doctor_emits_the_skew_warning`, `test_cli_warns_for_both_repo_root_spellings`.
- **R4:** `test_silent_when_running_is_newer_than_every_recorded_source` records only an older manifest (no AGENTS.md). Docs no longer claim `specy-road --version` itself warns.

## Added

- `_version_sort_key` / `recorded_toolkit_version` / `warn_if_running_version_older` in `specy_road/cli.py` — PEP-440-ish compare and read manifest + AGENTS.md block for the recorded minimum.
- `_repo_root_from_argv` / `_maybe_warn_running_version_older` in `specy_road/cli.py` — one warning per CLI invocation (skip `doctor`; doctor subprocess warns separately).
- `cmd_doctor` call to `warn_if_running_version_older` — A1 via `specy-road doctor`.
- **Minimum specy-road version** line (+ provenance comment) in `specy_road/templates/specyrd/agents-md-block.md` — A2 stub text.
- Maintainer install / PATH prose in `README.md` and `docs/install-and-usage.md` — A3.
- `tests/test_doctor_version_skew.py` — public CLI coverage of older, equal and newer recorded versions, both `--repo-root` spellings, and a newer AGENTS.md minimum.
- Assertion for minimum-version line in `tests/test_agents_md_block.py::test_fresh_init_project_writes_agents_md_with_the_block` — template ships minimum line on init.
