# Implementation summary — M11.66 (`version-shows-checkout-sha`)

## What changed

- Added `specy_road/toolkit_version.py` with `running_toolkit_version()`: semver from `__version__`, plus `+<12-char HEAD>` when the installed package directory is inside a git worktree, and a `.dirty` suffix when that worktree is not clean; plain semver for non-checkout installs.
- `specy-road --version` (and `-V` / `version`) prints `specy-road {running_toolkit_version()}` via `specy_road/cli.py`.
- `version_skew.py` re-exports `running_toolkit_version` for callers that already import from there; version-skew warnings still compare recorded project pins to plain `__version__`.
- Worker YAML records store `toolkit_version` at delegation time (`worker_state.create_record`).
- `render_front_matter` in `review_files.py` stamps `toolkit_version` on every READY/REVIEW write (including `specy-road ready` and `review record` without touching those CLIs).
- JSON schemas (`handoff`, `review-record`, `worker-record`) allow optional `toolkit_version`.

## Touch zones (confirmed)

| Path | Role |
|------|------|
| `specy_road/cli.py` | `--version` output |
| `specy_road/version_skew.py` | Re-export |
| `specy_road/toolkit_version.py` | **Added** — core helper (file-limits split) |
| `specy_road/worker_state.py` | Worker record field + set on create |
| `specy_road/review_files.py` | Stamp on render |
| `specy_road/schemas/*.json` | **Also edited** — required for valid records |
| `tests/` | Coverage for checkout / dirty / wheel-like tree, CLI, worker, review render |

`specy_road/worker_runner.py` was not modified; the worker record is stamped when the coordinator delegates.

## Verification

- `pytest tests/test_running_toolkit_version.py tests/test_cli_version.py tests/test_review_files.py tests/test_worker_state.py`
- `specy-road file-limits`

## Added

- `specy_road/toolkit_version.running_toolkit_version` — single source for CLI and audit strings.
- `version_skew.__all__` — documents the re-exported helper.
- `WorkerRecord.toolkit_version` + set in `create_record` — worker records name the build that delegated.
- `render_front_matter` stamp — review and READY files name the filing build.
- Schema `toolkit_version` property on handoff, review-record, worker-record — validation for stamped files.
- `tests/test_running_toolkit_version.py` — checkout, dirty checkout, non-checkout install, worker record, review stamp, CLI parity.
- Adjusted `tests/test_cli_version.py` and `tests/test_review_files.py::test_render_front_matter_round_trips` — align with stamped version output.
