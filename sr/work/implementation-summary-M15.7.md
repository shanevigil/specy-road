# Implementation summary: M15.7

File-limits baseline writing, failure hint, and upgrade failure counts.

## Acceptance

- **A1:** Baseline write appends `override_limits` entries without re-serialising existing YAML; block and flow sequences; inline and column-zero comments; extra entry fields; YAML-quoted paths; literal-path globs; validated output; idempotent rerun.
- **A2:** Failing scan prints `failure_hint()`; passing runs do not.
- **A3:** Upgrade prints single `failures: N`; non-zero count notes measurement change; exit code unchanged.

## Design (review fix round)

**Rule:** never re-emit or re-serialise existing `constraints/file-limits.yaml` text.

- **Append only:** new baseline rows are inserted at the composer `end_mark` of a block sequence, before the closing `]` of a flow sequence (or inside empty `[]`), or after a new `override_limits:` header when the key is missing. Existing bytes outside the insertion stay unchanged.
- **New flow items:** only the new `{name, file_globs, …}` snippet is generated; existing flow mappings and comments are not rewritten.
- **After write:** reload YAML; assert every key except `override_limits` is unchanged and prior `override_limits` rows match exactly; else raise and exit non-zero. Final `yaml.safe_load` sanity check unchanged.
- **Removed:** `_flow_override_limits_span`, `_render_override_limits_section`, `_serialize_override_entry`, and any full-span flow replacement.

## Probes

- Flow `[]`, `[] # existing comment`, one-line and two-line populated flow — `test_write_baseline_preserves_existing_yaml_bytes` (prefix/suffix bytes unchanged, comments kept, scan passes, idempotent).
- Flow `[ # head` with `note: extra` on existing entry — same parametrized test (comment and extra field preserved in parsed config).
- Block list before `roadmap_*` keys — `test_write_baseline_inserts_inside_override_limits_before_roadmap_keys`.
- Block list with column-zero comment and later restrictive row — `test_write_baseline_inserts_after_in_sequence_comments_and_later_rows` (baseline after restrictive; scan passes).
- No `override_limits` key — `test_append_keeps_existing_comments` and parametrized cases with header insert.
- Quoted filenames and `a[1].py` literal globs — dedicated tests.
- Parsed preservation guard — `_verify_append_preserves_parsed` on every append path in `file_limits_baseline_yaml.py`.
- Toolkit repo line cap — YAML helpers split to `file_limits_baseline_yaml.py`; `file_limits_baseline.py` ≤400 lines — `test_file_limits_passes_on_repo` / `specy-road file-limits` OK.

## Touch zones

Add `specy_road/file_limits_baseline_yaml.py` (listed in M15.7 touch zones).

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_file_limits_baseline.py tests/test_validate_file_limits.py` — 22 passed.
- `ruff check specy_road tests scripts` — clean.
- `specy-road file-limits` — OK.

## Added

- `specy_road/file_limits_baseline_yaml.py`: composer-mark append paths, flow bracket insert, parsed preservation check.
- `specy_road/file_limits_baseline.py`: scan/bucket/format/write orchestration; re-exports `append_baseline_yaml_text`.
- `optional_positive_int` in `file_limits_engine.py`.
- `tests/test_file_limits_baseline.py`: parametrized byte-preservation tests; block comment/restrictive-row regression.
