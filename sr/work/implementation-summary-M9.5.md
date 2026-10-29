# Implementation summary: M9.5 — integrity-report

## What shipped

- **`specy_road/integrity.py`** — Pure comparison of two commit SHAs: lists test files at each tip via `git ls-tree`, loads Python test modules with `git show` + AST, and diffs changed paths for pytest config files. Emits sorted `Finding` rows (text line + JSON dict).
- **`specy-road integrity <NODE_ID>`** — Resolves base and reviewed commit through `review_target` (same as `review-packet`), prints one finding per line (exit 1) or silent exit 0; `--json` prints findings only when non-empty.
- **`review-packet`** — Inserts **Test integrity** after **Changed paths** using the same `compare_integrity` call; deterministic for fixed base/head SHAs.
- **Docs / CLI usage / CHANGELOG** — User-facing mention of the command and packet section.

## Touch zones (confirmed)

`specy_road/integrity.py`, `specy_road/bundled_scripts/integrity_cli.py`, `specy_road/cli.py`, `specy_road/cli_usage.py`, `specy_road/bundled_scripts/review_packet.py`, `docs/orchestration-review.md`, `CHANGELOG.md`, `tests/`

## Verification

- `pytest tests/test_integrity.py tests/test_review_packet.py`
- `specy-road file-limits`
- `python scripts/check_clones.py` — not run here (`pylint` missing in this shell)

## Added

- `Finding` dataclass and `line()` / `as_json()` — stable text and JSON shapes for A2–A6.
- `compare_integrity()` — orchestrates file-tree, AST, and config diff findings.
- `_pytest_table_text()` — limits `config-change` on `pyproject.toml` to `[tool.pytest*]` tables.
- `_test_functions()` / skip and assert helpers — AST extraction for Python test modules.
- `findings_to_json()` — JSON envelope for `--json`.
- `test_integrity_section()` in `review_packet.py` — packet section after changed paths.
- `tests/test_integrity.py` — fixture repos per finding kind plus CLI exit/json tests.
- `test_packet_test_integrity_section_is_stable_and_lists_findings` — byte-stable section and assert-loss in packet.
- none — no new mocks; tests use real git repos under `tmp_path`.
