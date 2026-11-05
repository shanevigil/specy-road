# Implementation summary: M15.7

File-limits baseline writing, failure hint, and upgrade failure counts.

## Acceptance

- **A1:** Baseline write appends `override_limits` entries without re-serialising existing YAML; block and flow sequences; inline and column-zero comments; extra entry fields; YAML-quoted paths; literal-path globs; validated output; idempotent rerun.
- **A2:** Failing scan prints `failure_hint()`; passing runs do not.
- **A3:** Upgrade prints single `failures: N`; non-zero count notes measurement change; exit code unchanged.

## Design (review fix rounds)

**Never re-emit** existing `constraints/file-limits.yaml` text (append-only baseline rows).

**Mark-only offsets:** every insertion point comes from PyYAML `compose` node marks — block sequences use `SequenceNode.end_mark.index`; flow sequences insert before the closing `]` at `end_mark.index - 1`; empty vs populated flow lists use `seq.value`, not scanning the source for brackets. No `index`/`find`/`rfind` or bracket-depth walks on YAML text. Line/regex logic is only for adding a new top-level `override_limits:` when the key is absent; if the key exists but does not compose to a sequence, refuse with a block-style message instead of guessing.

**After write:** parsed preservation check plus `yaml.safe_load` sanity check; on failure raise (never write a broken file).

## Probes

- **Class: flow list with `]` inside a quoted glob** — `test_write_baseline_appends_with_special_chars_in_quoted_globs` flow/`a].py` (grok de83485f); prefix/suffix bytes unchanged, scan passes.
- **Class: quoted globs with `[`, `"`, `#`, `:`** — same test, flow and block parametrized — all pass byte invariant.
- Flow `[]`, `[] # existing comment`, populated flow — `test_write_baseline_preserves_existing_yaml_bytes` (F1/F3 gpt).
- Flow `[ # head` + `note: extra` — same parametrized test.
- Block column-zero comment + later restrictive row — `test_write_baseline_inserts_after_in_sequence_comments_and_later_rows` (F2 gpt).
- Block before `roadmap_*` keys — `test_write_baseline_inserts_inside_override_limits_before_roadmap_keys`.
- No `override_limits` key — `test_append_keeps_existing_comments`.
- Non-composable `override_limits` value — `append_baseline_yaml_text` raises naming `constraints/file-limits.yaml` (no silent line splice).
- Flow/block append paths — audited: no bracket/quote search remains in flow/block branches; only composer marks + `seq.flow_style`.
- Parsed preservation — `_verify_append_preserves_parsed` on every successful append.
- Toolkit line cap — `file_limits_baseline.py` ≤400; `specy-road file-limits` OK.

## Touch zones

`specy_road/file_limits_baseline_yaml.py` listed in M15.7 touch zones.

## Verification

- `python -m pytest -q -p no:cacheprovider tests/test_file_limits_baseline.py tests/test_validate_file_limits.py` — 30 passed.
- `ruff check specy_road tests scripts` — clean.
- `specy-road file-limits` — OK.

## Added

- `specy_road/file_limits_baseline_yaml.py`: mark-only append paths, flow close at `end_mark.index - 1`, composable-sequence guard.
- `specy_road/file_limits_baseline.py`: scan/bucket/format/write orchestration.
- `tests/test_file_limits_baseline.py`: byte-preservation and special-char glob parametrization.
