# Implementation summary: M15.7

File-limits baseline writing, failure hint, and upgrade failure counts.

## Acceptance

- **A1:** `specy-road file-limits --write-baseline` (and `--dry-run`) live in `validate_file_limits.py`; bucketing, YAML append, and idempotency are implemented in `specy_road/file_limits_baseline.py`. Tests in `tests/test_file_limits_baseline.py` pin rounding, buckets, comment preservation, dry-run, and rerun adding nothing.
- **A2:** A failing scan prints `failure_hint()` on stderr after violations; passing runs do not (`scan_with_optional_hint`).
- **A3:** `run_upgrade` records failure counts before `_apply` and after the refresh/`validate`/`digest` steps, prints them under `== file-limits`, mentions measurement changes when the after count is non-zero, and does not change upgrade's exit code.

## Touch zones

Confirmed accurate; `specy_road/file_limits_engine.py` unchanged (logic stays in `file_limits_baseline.py` at 249 lines). `upgrade.py` is 351 lines. `specy-road file-limits` passes on the toolkit repo.

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_file_limits_baseline.py tests/test_validate_file_limits.py` — 13 passed.
- `python -m pytest -q -p no:cacheprovider -n 4 tests/test_upgrade.py tests/test_upgrade_preview.py tests/test_upgrade_parity.py` — 19 passed.
- `specy-road file-limits` — OK.

## Added

- `specy_road/file_limits_baseline.py`: baseline module (A1–A3 helpers).
- `round_up_to_step`: bucket caps (50 / 20 steps) for A1.
- `FailingFileMetrics` / `collect_failing_file_metrics`: failing paths and worst sizes for bucketing.
- `file_limits_failure_count`: violation-line count for upgrade reporting (A3).
- `bucket_failing_files` / `format_baseline_entries` / `plan_baseline_append` / `append_baseline_yaml_text`: build and append YAML without re-dumping (A1).
- `write_baseline`: CLI backend for `--write-baseline` and `--dry-run` (A1).
- `failure_hint` / `scan_with_optional_hint`: stderr pointer on failure only (A2).
- `_file_limits_cfg` / `_file_limits_failure_count` / `_report_file_limits_after_upgrade` in `upgrade.py`: end-of-upgrade counts and hint (A3); `_capped_lines` reuses `_file_limits_cfg`.
- `--write-baseline` and `--dry-run` argparse flags in `validate_file_limits.py`.
- Docs paragraph in `docs/file-limits.md` for baseline and upgrade behaviour.
- `tests/test_file_limits_baseline.py`: behavioural tests for A1–A3 (no mocks).
