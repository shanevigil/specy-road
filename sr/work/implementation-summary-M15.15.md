# Implementation summary: M15.15

## Summary

`specy-road upgrade` ships missing `work/*.template.md` files that prompt builders and specyrd command stubs reference, after the mirrored refresh plan is applied (the plan mirror skips `work/`, so templates copy in a post-`apply_plan` step). The `.specyrd/README.md` upgrade paragraph lists the same six steps as `upgrade --help`.

**Fix round (R1):** `work_template_ship_plan()` decides copy vs out-of-repo refusal (via `resolves_outside`) before any `would write` / `wrote` line or copy. `_report_shipped_docs` and `copy_missing_work_templates` both use that plan so preview, real upgrade, and dry-run agree.

## Changes

- **`specy_road/upgrade_templates.py`**: `work_template_ship_plan()`, shared skip message, `copy_missing_work_templates` copies only the plan’s copy list.
- **`specy_road/bundled_scripts/upgrade.py`**: shipped-docs reporting uses the plan; helpers split for ruff C901.
- **`specy_road/templates/specyrd/dot-specyrd/README.md`**: upgrade step list matches `--help`.
- **`tests/test_upgrade_work_templates.py`**: A1–A3, README parity, external-`work/` symlink regression via `run_upgrade`.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/upgrade.py`
- `specy_road/upgrade_templates.py`
- `specy_road/templates/specyrd/dot-specyrd/README.md`
- `tests/`

## Verification

```bash
pytest tests/test_upgrade_work_templates.py tests/test_upgrade.py tests/test_upgrade_parity.py tests/test_upgrade_plan_parity.py tests/test_upgrade_preview.py -n 4 -q
ruff check specy_road tests scripts
specy-road file-limits
```

## Probes

- **Class: missing template path blocked by `resolves_outside` but still advertised as a write** — checked `_report_shipped_docs`, `copy_missing_work_templates`, and dry-run post-`apply_plan` copy; all routed through `work_template_ship_plan()` so refused paths never get write claims (fixed).
- **Class: external `work/` directory symlink (target outside git root)** — checked `work_template_ship_plan` and `run_upgrade` dry + real; only skip lines, external dir stays empty (test `test_external_work_symlink_reports_skipped_not_write`).
- **Class: per-file dangling `work/*.template.md` symlink** — checked `work_template_ship_plan` treats existing symlink as present, so not in copy or refuse lists; `copy_missing_work_templates` still skips overwrite (unchanged, matches reviewer probe).
- **Class: shipped `docs/` symlink outside repo** — checked `copy_missing_docs` still skips before append to `declined_docs` and does not append to copied list (unchanged; same message shape via `work_template_skip_message`).
- **Class: upgrade mirror skips `work/`** — checked post-`apply_plan` copy still uses real `existence_root` for the plan and sandbox only for bytes (unchanged design; no plan stale conflicts).

## Added

- `work_template_ship_plan()` — single copy vs refuse decision before claims or writes (R1).
- `work_template_skip_message()` — shared skip wording with shipped docs.
- `test_external_work_symlink_reports_skipped_not_write` — `run_upgrade` regression for external `work/` symlink (parametrized dry + real).
- (Prior leaf) `UPGRADE_STEP_LABELS`, discovery helpers, README/help parsers, post-`apply_plan` copy, `_report_*` refresh helpers, five other tests in `test_upgrade_work_templates.py`.
