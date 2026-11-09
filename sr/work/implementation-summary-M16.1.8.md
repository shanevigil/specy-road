# Implementation summary: M16.1.8 (`ruff-quality-baseline`)

Branch `feature/rm-ruff-quality-baseline`, base `361a5c73`. Implementation commit `3131d8d4`.

## What changed, by acceptance line

- **A1:** `specy_road/templates/project/constraints/file-limits.yaml` now has `max_lines_per_file: 1000` and an
  active `hard_alerts` block with `max_lines_per_file: 750` and the toolkit's rationale. The function cap (50)
  and the rest of the template are unchanged. The commented `max_lines_per_function: 80` alert stays commented.
- **A2:** `scripts/line_width_baseline.py` writes `scripts/line_width_baseline.json`. It records the command,
  the ruff version, the pickup commit (`361a5c73`) and, per file under `specy_road`, `scripts` and `tests`, the
  count from `ruff check --no-cache --select E501 --line-length 100 --output-format json`. Files with no long
  line have no entry. At pickup: 9,466 lines in 580 files (specy_road 4,730, tests 4,611, scripts 125).
  `--transfer OLD NEW` moves OLD's count onto NEW, adding it to NEW's own count after a fold.
  `python scripts/lean_metrics.py --check` prints the width report after its deltas. It names each file whose
  count rose and each file outside the baseline, then the total against the baseline. It always exits 0. No
  test or CI step reads a width count. No code was reformatted.
- **A3:** `upgrade` prints one notice under `== file-limits default` when the project's `max_lines_per_file`
  or `hard_alerts.max_lines_per_file` differs from the bundled template's. The notice names the project's
  values and the new default. The file is never written. It is printed after `refresh-stubs` on real runs and
  dry runs (from `_refresh`, which runs once per upgrade). No notice is printed when the file is absent or
  unreadable. The rc3 dry-run golden differs only by that section: a blank line, the header and the notice.
  `docs/file-limits.md` (new section "Template default") and `docs/upgrading.md` (new section "Your
  file-limits values stay") say the same. The toolkit's own `constraints/file-limits.yaml` keeps 1,000 lines
  with a 750 warning; only its comment about the width rule changed. `tests/test_upgrade_file_limits_notice.py`
  pins the notice text.
- **A4:** `CHANGELOG.md` `[Unreleased]` / `### Changed` records the new consumer default and that upgrade
  leaves existing files alone. No version heading.
- **A6:** `constraints/README.md` gains a row for the width report and corrects the quality-rules bullet:
  the ruff family baselines are M16.1.11's and the width baseline is M16.1.8's. `constraints/file-limits.yaml`'s
  comment says width is reported against the baseline, not gated. The same changes are in
  `sr/constraints/README.md` (links one level deeper) and `sr/constraints/file-limits.yaml`, in the same commit.
- **A5 (informational):** package +33 net (`upgrade.py`, the notice and the shared YAML read; the brief
  estimated 0). Config and docs +19. Scripts and tests about +225 (script 108, tests 101, `lean_metrics.py`
  +14), plus the generated 587-line width baseline.

## Zone change

`tests/test_archived_summary_file_limits.py` was added to the zones by the coordinator. With the template at
1,000 lines its 450-line `work/done/notes.md` no longer crossed the cap. Both files it writes are now 1,050
lines, so it still checks that archived summaries are exempt and other `work/done/` Markdown is capped. Its
docstring names the 1000-line cap.

## Final touch zones

The brief's list plus `tests/test_archived_summary_file_limits.py`. `pyproject.toml` was not changed: the
command names its own `--line-length 100`, and the existing `[tool.ruff]` gate selects only C901.

## Checks run

- `ruff check specy_road tests scripts`: clean. `specy-road file-limits`: OK (five existing warnings).
- `scripts/check_test_private_imports.py`, `check_machine_paths.py`, `check_clones.py`: pass.
- Dogfood `validate`, `export --check`, `digest --check`: OK.
- `pytest -n 4`: 6,995 passed, 15 skipped. The run's fixture-cleanliness check flagged
  `tests/fixtures/specy_road_dogfood/.specyrd/cache/`. My dogfood `validate`, run at the same time, had
  created it; I removed it. READY reruns the suite on its own.
- Width report after this leaf: total 9,466 -> 9,465 (-1). No file rose; no new file has a long line.
  `upgrade.py`'s one-line `_refresh` return was wrapped.

## Added

### Helpers

- `scripts/line_width_baseline.py` `counts(root)`: per-file E501 counts at 100 characters; `root` is the seam
  the test uses.
- `scripts/line_width_baseline.py` `transfer(files, old, new)`: the `--transfer` rule for a recorded move or
  fold.
- `scripts/line_width_baseline.py` `report(baseline, current)`: the lines `lean_metrics --check` prints.
- `scripts/line_width_baseline.py` `load()` / `write()` / `main()`: read and write the baseline and the CLI
  (generate, `--transfer`).
- `scripts/lean_metrics.py` `print_width_report()`: A2's report in `--check`. It imports `line_width_baseline`
  inside the function because the scripts directory is not on `sys.path` under `-p scripts.lean_metrics`.
- `upgrade.py` `_file_limits_config(root)`: the YAML read `_capped_lines` already did, shared with the notice;
  `_capped_lines` now calls it.
- `upgrade.py` `_file_cap(cfg)`: the two values compared against the template.
- `upgrade.py` `_report_file_limits_default(project)`: A3's notice.

### Branches or guards

- `_report_file_limits_default` returns without output when the project has no readable
  `constraints/file-limits.yaml`. Trigger: a project without the file (the `absent` test row).
- `_file_cap`: `hard_alerts` missing or not a mapping gives no warning value. Trigger: the rc3 file, which
  has no `hard_alerts` (the `rc3` row and the golden).
- `transfer`: OLD with no entry leaves the baseline unchanged. Trigger: moving a file with no long line (the
  third `--transfer` test row).

### Mocks

- `monkeypatch.setattr(width, "BASELINE", ...)` in the `--transfer` test points the CLI at a temporary
  baseline instead of the committed one.

### Tests

- `tests/test_line_width_baseline.py::test_counts_lines_over_100_per_file_under_the_areas`: the count is
  per file, under the three areas only, and a `noqa: E501` line is not counted. Skipped when ruff is not
  installed, because CI's test job does not install ruff.
- `tests/test_line_width_baseline.py::test_transfer_moves_old_count_onto_new` (three rows: move, fold, OLD
  absent): the `--transfer` rule, through the CLI.
- `tests/test_line_width_baseline.py::test_report_names_rises_and_new_files_and_the_total`: the report lists a
  rise and a file outside the baseline, not a fall or an unchanged file, then the total.
- `tests/test_upgrade_file_limits_notice.py::test_upgrade_names_the_new_default_and_leaves_the_file` (rows:
  rc3 file, template file, absent): the notice appears exactly once only when the values differ, and the file's
  bytes are unchanged (or it stays absent).
- `tests/parity/golden/upgrade/rc3-dry-run.txt`: regenerated; the only added lines are the notice section.
