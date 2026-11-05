# Implementation summary: M15.7

File-limits baseline writing, failure hint, and upgrade failure counts.

## Acceptance

- **A1:** Baseline append preserves YAML bytes outside the edit; empty/null/`{}` override_limits; document `...`; leading-space paths; post-write scan must pass or the file is restored.
- **A2:** Failing scan prints `failure_hint()`; passing runs do not.
- **A3:** Upgrade prints single `failures: N`; non-zero count notes measurement change; exit code unchanged.

## Design

- **YAML:** `compose` → mark-based splice (`_splice_baseline_block`) → reload + parsed invariant (`_verify_appended_text`) → return or raise. No bracket scanning; flow close at `end_mark.index - 1`.
- **Write:** `append_baseline_yaml_text` (validate) → write file → `run_file_limits_scan`; **one restore path** on scan failure only. No post-append “non-dict YAML” branch (unreachable after append verify).
- **Overlays:** `file_globs` matched without stripping patterns; paths quoted with `json.dumps`.

## Probes

- **Class: unreachable post-append non-dict restore (grok f5c8452f)** — removed from `write_baseline`; append verify is the only pre-write gate — ruff + review trace.
- **Class: post-append scan still failing (R1)** — single restore in `write_baseline`; `test_write_baseline_leading_space_filename_resolves_and_is_idempotent` — pass.
- **Class: YAML with `...` terminator, no key (R2)** — composer `end_mark` insert — `test_write_baseline_inserts_override_limits_before_document_end` — pass.
- **Class: empty override_limits value (R3)** — value-span block replace — `test_write_baseline_populates_empty_override_limits_value` — pass.
- **Class: redundant duplicate loader in write_baseline (R4)** — removed; verify stays in yaml module only.
- Flow/block/special-char globs — `test_file_limits_baseline_shapes.py` — pass.
- Refactor complexity — `ruff check` C901 clean on `file_limits_baseline_yaml.py` / `write_baseline`.
- Public test helpers — `tests/file_limits_baseline_helpers.py` (no cross-import of `_` names).
- Toolkit — `specy-road file-limits` OK.

## Touch zones

`specy_road/file_limits_baseline_yaml.py`, `specy_road/file_limits_engine.py` (overlay glob matching).

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_file_limits_baseline.py tests/test_file_limits_baseline_shapes.py tests/test_validate_file_limits.py` — 38 passed.
- `ruff check specy_road tests scripts` — clean.
- `specy-road file-limits` — OK.

## Added

- Unified splice + verify pipeline in `file_limits_baseline_yaml.py`.
- Post-write scan with single restore in `write_baseline`.
- Shape regressions in `tests/test_file_limits_baseline_shapes.py`; helpers in `tests/file_limits_baseline_helpers.py`.
