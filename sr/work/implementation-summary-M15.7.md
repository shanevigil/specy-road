# Implementation summary: M15.7

File-limits baseline writing, failure hint, and upgrade failure counts.

## Acceptance

- **A1:** `specy-road file-limits --write-baseline` (and `--dry-run`) buckets failures, splices rows into `override_limits` (including after `override_limits: []`), serializes path scalars with YAML quoting, uses literal-path globs so bracket names cannot widen exemptions, validates loadable YAML before write, and is idempotent when nothing fails.
- **A2:** A failing scan prints `failure_hint()` on stderr after violations; passing runs do not (`scan_with_optional_hint`).
- **A3:** `run_upgrade` prints a single `failures: N` after the refresh (no before/after pair while only the running engine is available), notes measurement changes when N is non-zero, and does not change upgrade's exit code.

## Fix round (grok-4.7-low)

Line-oriented insertion before later top-level keys; refuse write when composed YAML does not load.

## Fix round (gpt-6.1-sol-low)

Flow-empty `override_limits: []` expanded to a block list before insert; paths emitted via `yaml.dump` quoting and `literal_path_glob` for engine matching; upgrade uses single-count reporting; `optional_positive_int` shared from `file_limits_engine`.

## Probes

- `override_limits: []` then failing file: `write_baseline` exit 0, YAML loads, scan passes — `test_write_baseline_with_override_limits_empty_flow_list`.
- Filename with `"`: write succeeds, YAML loads, scan passes — `test_write_baseline_with_double_quote_in_filename`.
- `a[1].py` baselined, rerun idempotent, new `a1.py` still fails default cap — `test_write_baseline_literal_glob_does_not_widen_to_similar_names`.
- `literal_path_glob` on paths with `*`, `?`, `[`, `]` — spot-checked via bracket regression and Python `Path.glob` during development.
- `override_limits` block before `roadmap_*` keys — `test_write_baseline_inserts_inside_override_limits_before_roadmap_keys`.
- Dry-run and idempotent rerun — existing tests unchanged and passing.
- Upgrade output: `failures:` present, before/after lines absent — `test_upgrade_reports_file_limits_counts_without_failing`.
- `file_limits_failure_count` hard-alert caps — uses `optional_positive_int` from engine (same as scanner).
- Toolkit `constraints/file-limits.yaml` after changes — `specy-road file-limits` OK.

## Touch zones

Confirmed accurate. `optional_positive_int` is public in `file_limits_engine.py`.

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_file_limits_baseline.py tests/test_validate_file_limits.py` — 17 passed.
- `ruff check specy_road tests scripts` — clean.
- `specy-road file-limits` — OK.

## Added

- `specy_road/file_limits_baseline.py`: baseline module (A1–A3 helpers).
- `literal_path_glob` / `_yaml_quoted_scalar` / `_expand_flow_empty_override_limits`: safe globs and YAML scalars (gpt fix round).
- `_insert_index_for_new_override_rows` / `_loads_file_limits_mapping`: splice point and post-compose validation (grok fix round).
- `round_up_to_step`, `FailingFileMetrics`, `collect_failing_file_metrics`, `file_limits_failure_count`, `bucket_failing_files`, `format_baseline_entries`, `plan_baseline_append`, `append_baseline_yaml_text`, `write_baseline`, `failure_hint`, `scan_with_optional_hint`.
- `optional_positive_int` in `file_limits_engine.py` (F5; was private duplicate in baseline).
- `_report_file_limits_after_upgrade` single-count form in `upgrade.py` (F4).
- `--write-baseline` / `--dry-run` in `validate_file_limits.py`; docs in `docs/file-limits.md`.
- `tests/test_file_limits_baseline.py`: behavioural coverage including F1–F4 regressions.
