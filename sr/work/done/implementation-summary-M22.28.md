# Implementation summary: M22.28 — upgrade does not warn about itself, and export's drift line says how to fix it

Branch `feature/rm-upgrade-no-self-warning-export-drift-hint`, implementation `15e7d11d34972a8e2af40b1113ce47c682d73611`, base `77837855ed8cb23bbfe0c0c3f8dc7fdae8d3963e`.

## What changed

- `specy_road/cli.py` `_maybe_warn_running_version_older` returns before the version-skew check when the command is `upgrade`, the same early return `doctor` already takes. `validate` and every other known command call `warn_if_running_version_older`.
- `export --check` prints `drift: <path> no longer matches the roadmap. Run: specy-road export` when `roadmap.md` differs from the graph, then the same gitignore hint, then exit 1. The `missing <path>` line is unchanged.

## Acceptance

- **A1:** met. An older `AGENTS.md` block produces no `run \`specy-road upgrade\`` warning on `upgrade`; `validate` on the same tree prints it. A stale `roadmap.md` makes `export --check` name the path and `Run: specy-road export` and exit 1. Both cases are in the test files named in the acceptance. `[Unreleased]` `Fixed` has one line per finding.
- **A2:** not binding. `M16.1.1` and `M16.1.2` are `Not Started`, so this leaf captured before either of them. No file under `tests/parity/` changed.
- **A3:** informational. Package about +5 lines, tests about +48.

## Touch zones (final)

- `specy_road/cli.py`
- `specy_road/bundled_scripts/export_roadmap_md.py`
- `tests/test_doctor_version_skew.py`
- `tests/test_export_roadmap_md.py`
- `CHANGELOG.md`

Confirmed against the call sites at HEAD. Outside-zone importers of `export_roadmap_md` write or re-export; they do not format the `--check` drift line. Outside-zone importers of `cli` do not decide which command skips the skew warning. No zone added or removed.

## Verification

- `pytest tests/test_doctor_version_skew.py tests/test_export_roadmap_md.py -q -p no:cacheprovider`: 19 passed.

## Added

### Helpers

- none

### Branches or guards

- `cmd in ("doctor", "upgrade")` in `_maybe_warn_running_version_older` — `upgrade` must not tell the person to run `specy-road upgrade`; the command's own report already states the versions it moves between.

### Mocks

- none

### Tests

- `test_upgrade_does_not_warn_to_run_itself_when_the_agents_block_is_older` — an `AGENTS.md` block written by `0.0.1` leaves that warning off `upgrade` stderr and on `validate` stderr.
- `test_export_check_names_how_to_fix_drift` — a stale dogfood `roadmap.md` makes `export --check` print the digest-shaped drift line and exit 1.
