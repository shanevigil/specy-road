# Implementation summary: M15.15

## Summary

`specy-road upgrade` now ships missing `work/*.template.md` files that prompt builders and specyrd command stubs reference, after the mirrored refresh plan is applied (the plan mirror skips `work/`, so templates copy in a post-`apply_plan` step). The `.specyrd/README.md` upgrade paragraph lists the same six steps as `upgrade --help`.

## Changes

- **`specy_road/upgrade_templates.py`** (new): discovers bundled and prompt-referenced templates, compares README step labels to `UPGRADE_STEP_LABELS`, and copies missing templates without overwriting.
- **`specy_road/bundled_scripts/upgrade.py`**: docstring step 3 renamed to “shipped docs and templates”; shipped-docs section lists missing work templates; `_apply` / dry-run temp copy call `copy_missing_work_templates` after `apply_plan`.
- **`specy_road/templates/specyrd/dot-specyrd/README.md`**: “Updating after pip install” lists all upgrade steps including shipped docs and templates, validate, and digest `--check`.
- **`tests/test_upgrade_work_templates.py`**: A1–A3 coverage (reference set, upgrade copy, no overwrite, dry-run output, README/help parity).

## Touch zones (confirmed)

- `specy_road/bundled_scripts/upgrade.py`
- `specy_road/upgrade_templates.py`
- `specy_road/templates/specyrd/dot-specyrd/README.md`
- `tests/`

## Verification

```bash
pytest tests/test_upgrade_work_templates.py tests/test_upgrade.py tests/test_upgrade_parity.py tests/test_upgrade_plan_parity.py tests/test_upgrade_preview.py -n 4 -q
```

## Added

- `specy_road/upgrade_templates.py` — module for template discovery, README/help step labels, and copy-when-missing.
- `UPGRADE_STEP_LABELS` — canonical ordered step names shared by tests, README parser, and help docstring.
- `bundled_work_template_names()` — lists shipped `work/*.template.md` basenames.
- `referenced_work_template_names()` — greps `do_next_prompt.py`, `role_prompt*.py`, and `templates/specyrd/commands/*.md`.
- `upgrade_help_step_labels()` / `readme_upgrade_step_labels()` — parity check inputs for A2.
- `missing_work_template_rels()` — paths to add without writing (mirror-safe listing during refresh).
- `copy_missing_work_templates()` — post-plan copy with optional `existence_root` for dry-run sandbox.
- `existence_project` closure in `_plan()` — lists missing templates against the real checkout while refresh runs on the mirror.
- Post-`apply_plan` template copy in `_apply` and `_dry_run` — avoids upgrade-plan conflicts on skipped `work/`.
- `tests/test_upgrade_work_templates.py` — five tests for A1–A3 and README/help alignment; no new mocks.
