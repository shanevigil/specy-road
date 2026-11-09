# Implementation summary: M16.1.11 (`ruff-quality-family-baseline`)

Branch `feature/rm-ruff-quality-family-baseline`, base `542aa46c`.

## What changed, by acceptance line

- **A1:** `scripts/ruff_quality_baseline.py` writes `scripts/ruff_quality_baseline.json`. It records the command
  for each family, the ruff version (`ruff 0.17.3`), the pickup commit (`542aa46c`) and, per file under
  `specy_road`, `scripts` and `tests`, the count from `ruff check --no-cache --select <family> --output-format json`.
  C901 also passes `--ignore-noqa`, so a waiver is still counted; PL, B, SIM, RET, N and D102/D103 honour noqa.
  D102 and D103 are one family (`--select D102,D103`). Files with no finding in any family have no entry.
  `--no-cache` matches the width baseline so a warm cache cannot hide an edit; it does not change which rules run.
  At pickup: 5,643 findings in 742 files. C901 18, PL 1,549, B 38, SIM 42, RET 4, N 14, D102/D103 3,978.
  `python scripts/ruff_quality_baseline.py --shrink` rewrites a stored count only when the current count is lower.
  A higher count stays. A file or family that is not already stored is not added. A missing current count is zero
  and a zero entry is removed. When nothing is lower the file is left byte for byte, so the command does not dirty
  the tree. It always exits 0. No test or CI step fails on a family count. No finding was removed from existing code.
- **A2:** `--transfer OLD NEW` moves OLD's per-family counts onto NEW, adding them to NEW's own counts. OLD with no
  entry leaves the baseline unchanged. The pickup commit on the file is kept. No code was fixed.
- **A3:** The families are selected only in `scripts/ruff_quality_baseline.py`. `pyproject.toml` still selects only
  C901. `ruff check specy_road tests scripts` is clean. No other tool was added.
- **A4:** `python scripts/lean_metrics.py --check` prints the quality report after the width report. The header
  names the baseline commit. Each file whose count in a family rose, and each file outside the baseline, is named;
  then each family's total and its delta. The report always returns 0. `docs/release-runbook.md` §8.1 is the
  per-release checklist: each family total and its delta, the line-width total, and M16.2.6's import-cycle count.
  A rise is recorded and does not fail the checklist. M16.2.6 records the import-cycle value; this leaf only names it.
- **A5 (informational):** package 0. `scripts/ruff_quality_baseline.py` 205 lines, `tests/test_ruff_quality_baseline.py`
  193, `scripts/lean_metrics.py` +16/−1, `docs/release-runbook.md` +14. Scripts and tests are about +413, above the
  +80 estimate because each family, `--shrink` and `--transfer` is spelled out. The generated baseline is 2,670 lines.
  `docs/release-runbook.md` is 912 lines, under the 1,000-line cap (the 750 warning was already in effect at 898).

A fresh count after the baseline was written lowered nothing (`--shrink` printed `no entry lowered`), so the
quality report's family deltas against this file are 0. `lean_metrics.py --check` also prints M16.1.7's other
deltas; those are in this leaf's READY record, because that command times the suite.

## Final touch zones

The brief's list, unchanged: `scripts/ruff_quality_baseline.py`, `scripts/ruff_quality_baseline.json`,
`tests/test_ruff_quality_baseline.py`, `scripts/lean_metrics.py`, `docs/release-runbook.md`. The only caller is
`print_quality_report` in `scripts/lean_metrics.py`, which is in the zone. `pyproject.toml` stays out.

## Checks run

- `pytest -n 4 tests/test_ruff_quality_baseline.py`: 11 passed.
- `ruff check specy_road tests scripts`: clean.
- `specy-road file-limits`: OK (five existing warnings; the runbook warning is one of them).
- `python scripts/ruff_quality_baseline.py --shrink`: `no entry lowered`, and the baseline file was not rewritten.

## Added

### Helpers

- `scripts/ruff_quality_baseline.py` `ruff_command`: the ruff argv for one family, shared by the count and the
  command recorded in the baseline.
- `scripts/ruff_quality_baseline.py` `counts(root)`: per-file, per-family findings. `root` is the seam the area
  test uses. One ruff invocation per family, because only C901 passes `--ignore-noqa`.
- `scripts/ruff_quality_baseline.py` `_in_family_order`: stored family keys stay in the report's family order.
- `scripts/ruff_quality_baseline.py` `transfer`: the `--transfer` rule, summed per family.
- `scripts/ruff_quality_baseline.py` `shrink`: the `--shrink` rule.
- `scripts/ruff_quality_baseline.py` `totals`: each family's sum, including a family with no findings.
- `scripts/ruff_quality_baseline.py` `report`: the lines `lean_metrics --check` prints.
- `scripts/ruff_quality_baseline.py` `load` / `write` / `main`: read and write the baseline and the CLI
  (generate, `--shrink`, `--transfer`).
- `scripts/lean_metrics.py` `print_quality_report`: A4's report in `--check`. It imports `ruff_quality_baseline`
  inside the function because the scripts directory is not on `sys.path` under `-p scripts.lean_metrics`.

### Branches or guards

- `shrink`: a higher current count stays at the stored number. Trigger: the row where current C901 is 4 and the
  stored count stays 1.
- `shrink`: a family missing from the current count is zero and dropped, and a file that is gone is removed.
  Trigger: the vanished-file row and the row that drops C901 when only PL remains.
- `shrink`: a file or family that is not in the baseline is not added. Trigger: the new-file row and the new-family row.
- `shrink`: when nothing is lower, the file is not rewritten. Trigger: those no-op rows, and `--shrink` after the
  pickup count, so the command does not dirty the zone.
- `transfer`: OLD with no entry leaves the files unchanged. Trigger: the third `--transfer` row.
- `counts`: ruff's exit is not checked. Trigger: ruff exits 1 whenever it finds any, which is the normal count.

### Mocks

- `monkeypatch.setattr(quality, "BASELINE", ...)` in the `--transfer` and `--shrink` tests points the CLI at a
  temporary baseline instead of the committed one.
- `monkeypatch.setattr(quality, "counts", ...)` in the `--shrink` test substitutes the current counts so the CLI
  does not scan the repository. The test asserts the written file, not that `counts` was called.

### Tests

- `tests/test_ruff_quality_baseline.py::test_counts_findings_per_file_and_family_under_the_areas`: the count is
  per file and per family, under the three areas only; a `noqa: C901` function is still counted and a
  `noqa: B006` function is not. Skipped when ruff is not installed, because CI's test job does not install ruff.
- `tests/test_ruff_quality_baseline.py::test_transfer_sums_old_families_onto_new` (three rows: move, fold, OLD
  absent): the `--transfer` rule, through the CLI. The pickup commit on the file is kept.
- `tests/test_ruff_quality_baseline.py::test_shrink_lowers_entries_and_never_raises` (six rows: lower one family,
  refuse a rise, refuse a new file, refuse a new family, drop a vanished file, drop a family that fell to zero):
  the `--shrink` rule, through the CLI. Rows that change nothing also assert the file's bytes are unchanged.
- `tests/test_ruff_quality_baseline.py::test_report_names_rises_new_files_and_family_totals`: the report lists a
  rise, a new family on a known file and a file outside the baseline, not a fall, then every family's total and delta.
