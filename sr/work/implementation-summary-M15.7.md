# Implementation summary: M15.7

File-limits baseline writing, failure hint, and upgrade failure counts.

## Acceptance

- **A1:** Baseline write appends `override_limits` without re-serialising existing YAML; empty/null/`{}` values; document `...` terminator; leading-space paths; post-write scan must pass or file is restored.
- **A2:** Failing scan prints `failure_hint()`; passing runs do not.
- **A3:** Upgrade prints single `failures: N`; non-zero count notes measurement change; exit code unchanged.

## Design

- **Never re-emit** existing YAML bytes outside the insertion/replacement span.
- **Mark-only** flow/block offsets from PyYAML `compose` (flow close at `end_mark.index - 1`).
- **New key:** insert at first-document `end_mark` (before `...`) or before trailing policy keys — composer line starts, not line scans of scalars.
- **Empty override_limits value** (null, bare key, `{}`, empty block seq): replace only the value span with a block sequence; preserve trailing comments on the key line.
- **Post-write gate:** run `run_file_limits_scan` after append; on failure restore original file and exit non-zero.
- **Overlay globs:** `build_overlay_match_sets` matches `file_globs` without stripping the pattern (exclude globs still strip).
- **Quoting:** `yaml_quoted_scalar` uses `json.dumps` for YAML-safe double-quoted paths.

## Probes

- **Class: leading/trailing space in repo-relative paths (R1)** — overlay `strip_pattern=False`; `test_write_baseline_leading_space_filename_resolves_and_is_idempotent` — scan passes, rerun idempotent.
- **Class: YAML ending with explicit `...` and no override_limits (R2)** — `root.end_mark` insert; `test_write_baseline_inserts_override_limits_before_document_end` — prefix bytes preserved, `...` after new rows.
- **Class: empty override_limits value null / `{}` / bare key (R3)** — value-span replace via marks; `test_write_baseline_populates_empty_override_limits_value` — comment on key line kept, scan passes.
- **Class: post-append scan still failing** — `write_baseline` restores raw file; exercised by engine+quoting fix (would fail without overlay match).
- **Class: quoted globs with `]`, `[`, `"`, `#`, `:` and space padding** — `test_write_baseline_appends_with_special_chars_in_quoted_globs` (flow + block).
- Flow/block byte preservation — `test_write_baseline_preserves_existing_yaml_bytes` in `test_file_limits_baseline_shapes.py`.
- Block comment + restrictive row, roadmap keys, CLI hint, upgrade count — `test_file_limits_baseline.py`.
- **R4:** redundant `_loads_file_limits_mapping` + unreachable branch removed from `write_baseline`; validation stays in `append_baseline_yaml_text`.
- Toolkit line caps — `tests/test_file_limits_baseline.py` ≤400; `specy-road file-limits` OK.

## Touch zones

Includes `specy_road/file_limits_baseline_yaml.py`, `specy_road/file_limits_engine.py` (overlay glob matching only).

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_file_limits_baseline.py tests/test_file_limits_baseline_shapes.py tests/test_validate_file_limits.py` — 38 passed.
- `ruff check specy_road tests scripts` — clean.
- `specy-road file-limits` — OK.

## Added

- Post-write scan + restore in `write_baseline`.
- Composer-based new-key and empty-value paths in `file_limits_baseline_yaml.py`.
- `tests/test_file_limits_baseline_shapes.py` for YAML shape regressions.
