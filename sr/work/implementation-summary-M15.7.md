# Implementation summary: M15.7

File-limits baseline writing, failure hint, and upgrade failure counts.

## Acceptance

- **A1:** Baseline write handles flow- and block-style `override_limits`, preserves in-sequence comments for block lists, YAML-quoted paths, literal-path globs, validated output, idempotent rerun.
- **A2:** Failing scan prints `failure_hint()`; passing runs do not.
- **A3:** Upgrade prints single `failures: N`; non-zero count notes measurement change; exit code unchanged.

## Fix rounds

- **grok / gpt (prior):** Splice before trailing keys; flow `[]` and one-line flow; column-zero comments; quoting and literal globs; single upgrade count.
- **grok-4.7-low (189cac81):** Flow-style `override_limits` (including multi-line sequences) is replaced via PyYAML `compose` start/end marks, re-emitted as block entries plus baselines — no header-only line splice. Block-style lists still append at the sequence end.

## Probes

- Flow shapes `[]`, `[] # comment`, one-line `[{…}]`, two-line `[{…}, {…}]` — `test_write_baseline_replaces_flow_override_limits_shapes` (exit 0, loads, scan passes, idempotent).
- Block list before `roadmap_*` keys — `test_write_baseline_inserts_inside_override_limits_before_roadmap_keys`.
- Block list with column-zero comment and later restrictive row — `test_write_baseline_inserts_after_in_sequence_comments_and_later_rows`.
- Quoted filenames and `a[1].py` literal globs — dedicated tests.
- Sol-low empty-flow comment, populated one-line flow — covered by parametrized flow test plus earlier named tests.
- Block insert path unchanged for non-flow value nodes — `_flow_override_limits_span` returns None when value is not `[…]`.
- Toolkit repo — `specy-road file-limits` OK.

## Touch zones

Confirmed accurate.

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_file_limits_baseline.py tests/test_validate_file_limits.py` — 24 passed.
- `ruff check specy_road tests scripts` — clean.
- `specy-road file-limits` — OK.

## Added

- `_flow_override_limits_span`, `_render_override_limits_section`, `_inline_header_comment`: composer-mark flow replacement (grok fix).
- `_ends_override_limits_section`, block-list insert path, `_serialize_override_entry`, literal globs, validation, baseline/upgrade/hint API.
- `optional_positive_int` in `file_limits_engine.py`.
- `tests/test_file_limits_baseline.py` including parametrized flow override shapes.
