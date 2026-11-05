# Implementation summary: M15.7

File-limits baseline writing, failure hint, and upgrade failure counts.

## Acceptance

- **A1:** Baseline write handles empty and populated flow-style `override_limits`, block lists with column-zero comments, YAML-quoted paths, literal-path globs, validated splice, idempotent rerun.
- **A2:** Failing scan prints `failure_hint()`; passing runs do not.
- **A3:** Upgrade prints single `failures: N` after refresh; non-zero count notes measurement change; exit code unchanged.

## Fix rounds

- **grok-4.7-low:** Splice before later top-level keys; refuse unparseable YAML.
- **gpt-6.1-sol-low (1):** Flow `[]`, quoting, literal globs, single upgrade count, `optional_positive_int` shared.
- **gpt-6.1-sol-low (2):** `_normalize_override_limits_block` expands flow empty (preserve ` # comment` spacing) and populated flow sequences; `_ends_override_limits_section` ignores column-zero comments so baselines append after the full existing sequence; `_serialize_override_entry` uses `_yaml_quoted_scalar` for names.

## Probes

- `override_limits: [] # existing comment` → write 0, comment preserved, scan passes — `test_write_baseline_empty_flow_list_preserves_inline_comment`.
- Block list with column-zero comment and later restrictive row → baseline after restrictive, scan passes — `test_write_baseline_inserts_after_in_sequence_comments_and_later_rows`.
- Populated flow `override_limits: [{...}]` → block form + baseline, scan passes — `test_write_baseline_appends_to_populated_flow_override_list`.
- Empty flow without comment, bracket/quote paths, roadmap splice, dry-run, upgrade single count — prior tests still passing.
- `_serialize_override_entry` name scalars — fixed `yaml.dump` document-end artifact; verified via populated-flow test.
- Toolkit repo — `specy-road file-limits` OK.

## Touch zones

Confirmed accurate.

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_file_limits_baseline.py tests/test_validate_file_limits.py` — 20 passed.
- `ruff check specy_road tests scripts` — clean.
- `specy-road file-limits` — OK.

## Added

- `literal_path_glob`, `_yaml_quoted_scalar`, `_normalize_override_limits_block`, `_ends_override_limits_section`, `_serialize_override_entry`, `_split_trailing_hash_comment`, insertion/validation helpers, baseline/upgrade/hint API in `file_limits_baseline.py`.
- `optional_positive_int` in `file_limits_engine.py`.
- Upgrade single-count reporting in `upgrade.py`; docs in `docs/file-limits.md`.
- `tests/test_file_limits_baseline.py` regressions for flow/block YAML shapes (F1–F3).
