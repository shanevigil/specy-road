# Implementation summary: M15.7

File-limits baseline writing, failure hint, and upgrade failure counts.

## Acceptance

- **A1:** `specy-road file-limits --write-baseline` (and `--dry-run`) live in `validate_file_limits.py`; bucketing, YAML append, and idempotency are implemented in `specy_road/file_limits_baseline.py`. New rows are spliced into the existing `override_limits` list before later top-level keys (for example `roadmap_manifest_max_lines`); `write_baseline` refuses to write when the result would not `yaml.safe_load`. Tests pin rounding, buckets, comment preservation, toolkit-shaped YAML, dry-run, and rerun adding nothing.
- **A2:** A failing scan prints `failure_hint()` on stderr after violations; passing runs do not (`scan_with_optional_hint`).
- **A3:** `run_upgrade` records failure counts before `_apply` and after the refresh/`validate`/`digest` steps, prints them under `== file-limits`, mentions measurement changes when the after count is non-zero, and does not change upgrade's exit code.

## Fix round (grok-4.7-low)

Replaced EOF append whenever `override_limits:` appeared with line-oriented insertion: scan from the `override_limits` header until the next top-level key (or EOF), insert baseline list items there; when the header is missing, open `override_limits` before known trailing policy keys. `write_baseline` validates the composed document with `yaml.safe_load` and exits 1 without writing on parse failure.

## Probes

- `append_baseline_yaml_text` on toolkit-shaped YAML (`override_limits` then `roadmap_*` keys): baseline rows land before `roadmap_manifest_max_lines` and `yaml.safe_load` succeeds — covered by `test_write_baseline_inserts_inside_override_limits_before_roadmap_keys`.
- `append_baseline_yaml_text` when `override_limits` is absent and the file has only `applies_to_globs`: adds a new `override_limits` section that loads — covered by `test_append_keeps_existing_comments`.
- `write_baseline` after a successful write on the same fixture: idempotent second run — covered by `test_write_baseline_buckets_pass_and_rerun_is_idempotent`.
- `write_baseline` dry-run path: still does not touch the file — covered by `test_write_baseline_dry_run_prints_without_writing`.
- `plan_baseline_append` / `write_baseline` when nothing fails: empty plan, exit 0 — covered by `test_plan_baseline_append_empty_when_nothing_fails`.
- `scan_with_optional_hint` and CLI subprocess: hint on failure only — covered by `test_failing_cli_prints_hint_passing_does_not`.
- `run_upgrade` file-limits section: unchanged by insertion fix — covered by `test_upgrade_reports_file_limits_counts_without_failing`.

## Touch zones

Confirmed accurate; `specy_road/file_limits_engine.py` unchanged. `specy-road file-limits` passes on the toolkit repo.

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_file_limits_baseline.py tests/test_validate_file_limits.py` — 14 passed (fix round).
- `specy-road file-limits` — OK.

## Added

- `specy_road/file_limits_baseline.py`: baseline module (A1–A3 helpers).
- `round_up_to_step`: bucket caps (50 / 20 steps) for A1.
- `FailingFileMetrics` / `collect_failing_file_metrics`: failing paths and worst sizes for bucketing.
- `file_limits_failure_count`: violation-line count for upgrade reporting (A3).
- `bucket_failing_files` / `format_baseline_entries` / `plan_baseline_append` / `append_baseline_yaml_text`: build and splice YAML without re-dumping (A1).
- `_insert_index_for_new_override_rows` / `_loads_file_limits_mapping`: insertion point scan and post-compose YAML validation (fix round).
- `write_baseline`: CLI backend for `--write-baseline` and `--dry-run` (A1).
- `failure_hint` / `scan_with_optional_hint`: stderr pointer on failure only (A2).
- `_file_limits_cfg` / `_file_limits_failure_count` / `_report_file_limits_after_upgrade` in `upgrade.py`: end-of-upgrade counts and hint (A3); `_capped_lines` reuses `_file_limits_cfg`.
- `--write-baseline` and `--dry-run` argparse flags in `validate_file_limits.py`.
- Docs paragraph in `docs/file-limits.md` for baseline and upgrade behaviour.
- `tests/test_file_limits_baseline.py`: behavioural tests for A1–A3 (no mocks); `test_write_baseline_inserts_inside_override_limits_before_roadmap_keys` for fix round.
