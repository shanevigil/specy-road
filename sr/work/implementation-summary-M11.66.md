# Implementation summary — M11.66 (`version-shows-checkout-sha`)

## What changed

- Added `specy_road/toolkit_version.py` with `running_toolkit_version()`: semver from `__version__`, plus `+<12-char HEAD>` when the installed package directory is inside a git worktree, and a `.dirty` suffix when that worktree is not clean; plain semver for non-checkout installs.
- `specy-road --version` (and `-V` / `version`) prints `specy-road {running_toolkit_version()}` via `specy_road/cli.py`.
- `version_skew.py` re-exports `running_toolkit_version` for callers that already import from there; version-skew warnings still compare recorded project pins to plain `__version__`.
- Worker YAML records store `toolkit_version` at delegation time (`worker_state.create_record`).
- `render_front_matter` in `review_files.py` calls `stamp_review_toolkit_version` (in `toolkit_version.py`): REVIEW records get `toolkit_version` once; re-render (e.g. independence relabel) does not overwrite a filed value. READY hand-offs are unchanged.
- `review record` and interactive human approve stamp before `sign()`, so signed bytes match the written file.
- JSON schemas: `review-record` and `worker-record` allow optional `toolkit_version`. The READY/handoff schema is unchanged.

## Touch zones (confirmed)

| Path | Role |
|------|------|
| `specy_road/cli.py` | `--version` output |
| `specy_road/version_skew.py` | Re-export |
| `specy_road/toolkit_version.py` | **Added** — core helper (file-limits split) |
| `specy_road/worker_state.py` | Worker record field + set on create |
| `specy_road/review_gate_ready.py`, `specy_road/bundled_scripts/review_cli.py` | Stamp before sign |
| `specy_road/review_files.py` | REVIEW render uses stamp helper |
| `specy_road/schemas/review-record.schema.json`, `worker-record.schema.json` | Optional `toolkit_version` field |
| `tests/` | Coverage for checkout / dirty / wheel-like tree, CLI, worker, review render, signing |

`specy_road/worker_runner.py` was not modified; the worker record is stamped when the coordinator delegates.

## Verification

- `pytest tests/test_running_toolkit_version.py tests/test_cli_version.py tests/test_review_files.py tests/test_worker_state.py tests/test_review_signing.py tests/test_review_cli.py`
- `specy-road file-limits`

## Added

- `specy_road/toolkit_version.running_toolkit_version` — single source for CLI and audit strings.
- `version_skew.__all__` — documents the re-exported helper.
- `WorkerRecord.toolkit_version` + set in `create_record` — worker records name the build that delegated.
- `toolkit_version.stamp_review_toolkit_version` — one-shot REVIEW stamp; preserved on re-render.
- `review_cli` / `write_human_approval` — stamp before `sign()`.
- Schema `toolkit_version` on review-record and worker-record — validation for stamped files. Handoff schema left as-is.
- `tests/test_running_toolkit_version.py` — checkout, dirty checkout, non-checkout install, worker record, REVIEW stamp, READY unstamped, CLI parity.
- Adjusted `tests/test_cli_version.py` and `tests/test_review_files.py::test_render_front_matter_round_trips` — align with stamped version output.
