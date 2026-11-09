# Implementation summary: M16.1.11 (`ruff-quality-family-baseline`)

Branch `feature/rm-ruff-quality-family-baseline`, base `542aa46c`.

## What changed, by acceptance line

- **A1:** `scripts/ruff_quality_baseline.py` writes `scripts/ruff_quality_baseline.json`. It records the command
  for each family, the ruff version (`ruff 0.17.3`), the pickup commit (`542aa46c`) and, per file under
  `specy_road`, `scripts` and `tests`, the count from `ruff check --no-cache --select <family> --output-format json`.
  C901 also passes `--ignore-noqa`, so a waiver is still counted; PL, B, SIM, RET, N and D102/D103 honour noqa.
  D102 and D103 are one family (`--select D102,D103`). Files with no finding in any family have no entry.
  `--no-cache` matches the width baseline so a warm cache cannot hide an edit; it does not change which rules run.
  At pickup, counted from that commit's tree: 5,638 findings in 741 files. C901 18, PL 1,548, B 38, SIM 42,
  RET 4, N 14, D102/D103 3,974.
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
- **A5 (informational):** package 0. `scripts/ruff_quality_baseline.py` 225 lines, `tests/test_ruff_quality_baseline.py`
  255, `scripts/lean_metrics.py` +16/−1, `docs/release-runbook.md` +14. Scripts and tests are above the +80
  estimate because each family, `--shrink`, `--transfer` and the commit-tree rewrite are spelled out. The
  generated baseline is 2,666 lines.
  `docs/release-runbook.md` is 912 lines, under the 1,000-line cap (the 750 warning was already in effect at 898).

## Fix round (review block on `6a613c7a`)

**Class:** a count stored under the pickup commit that was taken from the worktree, so a post-pickup increase
is already in the baseline and the report prints `+0`. The named instance is a path that does not exist at
that commit. The same class also reaches an existing file whose blob at the commit is not the blob that was
counted. One rule covers both: a full rewrite counts `git archive` of the commit it records, not the worktree.
The docstring and `--help` state that rule. `--shrink` still reads the worktree, and it can only lower.

The regenerated baseline drops `tests/test_ruff_quality_baseline.py` and stores `scripts/lean_metrics.py` at
the commit's PL 3, not the worktree's PL 4. Against the worktree the report now names
`scripts/lean_metrics.py PL: 3 -> 4 (+1)` and
`tests/test_ruff_quality_baseline.py: D102/D103 6 (not in the baseline)`. Family totals are not `+0`:
D102/D103 3,974 -> 3,949 (−25) and PL 1,548 -> 1,540 (−8), because files deleted on the integration branch
since pickup outweigh this leaf's additions. Those deletions are not this class; they stay in the pickup
baseline. The new PL finding is the inline import in `print_quality_report`, left in place so the report
shows it.

## Fix round (review block on `6ef98d46`)

**Class:** a git command in a test that requires a historical commit object and treats a missing object as
failure (`check=True`). A depth-1 checkout, which is what `actions/checkout@v7` does when `fetch-depth` is
unset, does not have `542aa46c`, so `git ls-tree` exits 128.

The same class does not reach the other git calls in this leaf. `test_rewrite_counts_the_commit_tree_not_the_worktree`
creates the commit it archives. `counts_at` archives the commit `main` passes, which is `HEAD` of the
repository being rewritten; CI does not run that rewrite, and a depth-1 checkout does contain `HEAD`.
`.github/workflows/validate.yml` is outside the zones and was not changed.

One rule: the tree check runs only when `git cat-file -e <commit>^{commit}` succeeds. The recorded hash is
always compared to the pickup commit, which does not need the object.

## Probes

- Every pre-fix baseline path against `git ls-tree` of `542aa46c`: only `tests/test_ruff_quality_baseline.py`
  was absent, with D102/D103 4.
- `scripts/ruff_quality_baseline.py` is new and was not a baseline key (no findings in the seven families).
- `scripts/lean_metrics.py` is in the commit, but the blob differs. Stored PL was 4; the commit blob is PL 3
  and D102/D103 23; the worktree is PL 4 and D102/D103 23. Same class as the missing path.
- `docs/release-runbook.md` differs from the commit and is outside `specy_road`, `scripts` and `tests`, so it
  cannot enter this baseline.
- Scripts deleted by the merge with `origin/WIP/improvements-0-3-1` (`scripts/census/`, `scripts/review_effort_study.py`)
  exist at `542aa46c` and stay in the baseline. Not this class.
- `.github/workflows/validate.yml` uses `actions/checkout@v7` with no `fetch-depth`, so CI's checkout is depth 1.
  The workflow was not edited.
- Other git calls in `tests/test_ruff_quality_baseline.py` (`init`, `add`, `commit`, `rev-parse`) run in a
  repository the test just created, so their commits are local. `counts_at` is not called on `542aa46c` by any test.
- `git cat-file -e 542aa46c^{commit}` in this checkout exits 0, so the tree check still runs here (13 passed).
- A `--depth 1` clone of this branch, with the updated test copied in: `git cat-file -e 542aa46c^{commit}`
  exits 128, and that test is skipped (pytest exit 0). The clone was removed afterwards.

## Final touch zones

The brief's list, unchanged: `scripts/ruff_quality_baseline.py`, `scripts/ruff_quality_baseline.json`,
`tests/test_ruff_quality_baseline.py`, `scripts/lean_metrics.py`, `docs/release-runbook.md`. The only caller is
`print_quality_report` in `scripts/lean_metrics.py`, which is in the zone. `pyproject.toml` stays out.

## Checks run

- `pytest -n 4 tests/test_ruff_quality_baseline.py`: 13 passed. In a depth-1 clone the pickup-commit test is skipped
  and the run still exits 0.
- `ruff check specy_road tests scripts`: clean.
- `specy-road file-limits`: OK (three warnings; `docs/release-runbook.md` at 912 lines is one, under the 1,000 cap).
- `python scripts/ruff_quality_baseline.py --shrink` on the first baseline: `no entry lowered`. Not run again
  after the regeneration, because shrink would replace the pickup counts with the post-merge tree.

## Added

### Helpers

- `scripts/ruff_quality_baseline.py` `ruff_command`: the ruff argv for one family, shared by the count and the
  command recorded in the baseline.
- `scripts/ruff_quality_baseline.py` `counts(root)`: per-file, per-family findings. `root` is the seam the area
  test uses. One ruff invocation per family, because only C901 passes `--ignore-noqa`.
- `scripts/ruff_quality_baseline.py` `counts_at(commit, root)`: the rewrite rule. It counts `git archive` of
  `commit`, so the worktree cannot be stored under that commit. `main` passes `REPO` at call time so a test
  can point the rewrite at another repository.
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
- `tests/test_ruff_quality_baseline.py::test_baseline_records_the_pickup_commit_and_only_its_files`: the
  committed baseline's commit is `542aa46c`. When that commit object is local, every path exists in its
  tree. When `git cat-file -e <commit>^{commit}` fails, the tree check is skipped, so a depth-1 checkout
  does not fail. Uses git, not ruff.
- `tests/test_ruff_quality_baseline.py::test_rewrite_counts_the_commit_tree_not_the_worktree`: a full rewrite
  keeps the committed file's count and leaves out a worktree edit and an untracked file. Skipped when ruff
  is not installed.
