# Implementation summary — M16.1.7

Baseline metrics, a coverage floor in CI, and the M16 working rules written down.

## Commits

- `ef2690ed` (**the baseline commit**): `scripts/lean_metrics.py`; coverage pinned in the `dev` extra and the lock regenerated; `[tool.coverage.run]`; CI's test step runs under coverage.
- `674dc189`: `[tool.coverage.report] fail_under = 90`; `constraints/lean-baseline.json` (measured at `ef2690ed`); the M16 rules and quality rules in `constraints/README.md` and `sr/constraints/README.md`.
- The next commit adds this summary.

## Touch zones (confirmed)

- `scripts/lean_metrics.py`: **new**, maintainer-only, not shipped.
- `constraints/lean-baseline.json`: **new**, written by the script.
- `constraints/README.md`, `sr/constraints/README.md`: the same text; the `sr/` copy's links are one level deeper, and it links to the root `constraints/lean-baseline.json` because `sr/constraints/` has none.
- `.github/workflows/validate.yml`: the `Tests` step became `Tests under coverage`.
- `pyproject.toml`: `coverage==7.17.2` in `dev`; `[tool.coverage.run]` and `[tool.coverage.report]`. `project.version` untouched.
- `requirements-ci.txt`: `pip-compile requirements-ci.in -o requirements-ci.txt` (Python 3.12) added only `coverage==7.17.2`. pip-compile wrote this checkout's absolute path on the `-e` line, so I restored the committed `-e .[dev]`.
- `requirements-ci.in`: no change needed (it is `-e .[dev]`).

No path outside the zones changed, and no zone needs adding.

## Acceptance

**A1 (baseline commit).** `constraints/lean-baseline.json` records `commit: ef2690ed…` with `clean: true`. At that commit:

- **rc4 leaves:** every rc4 leaf in M16.1.3's inventory is Complete in the archive (M14.1, M15.2, M15.3, M15.9, M15.17, M15.31, M15.33, M15.36). M15.7 (now M19.10, dropped) and M15.20 (now M18.13, post-0.3.1) are recorded in M16.1.3's round 2 table.
- **Harnesses:** `pytest tests/parity -n 4` gave 234 passed and 1 skipped. That covers the M16.1.1 harness and M16.1.2's `tests/parity/review_gate/`, which carries no `parity` marker, so `-m parity` alone would leave it out.

**A2 (`python scripts/lean_metrics.py`).** It measures every listed number from the files git tracks at HEAD:

- package and test lines and files per subsystem (a classifier ported from 01-code.md §1, because the scratchpad's `subsys.py` is not in the tree);
- docs lines and files over the listed paths, leaving out `docs/design-notes/`, the root `design-notes/` and `sr/`;
- test functions (AST, pytest's default names) and collected items (`pytest --collect-only`);
- C901 findings (`ruff --select C901 --ignore-noqa`) and `noqa: C901` comments;
- lines over 100 (`ruff --select E501 --line-length 100`, M16.1.8's command);
- canonical commands and aliases (M16.4.4's definition: `registered_agent_command_names()['specy-road']` minus `command_map.yaml` rows that retire a bare top-level name);
- config and policy keys (top-level `git-workflow.schema.json` properties plus orchestration `$defs.policy` properties);
- modules imported by `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`;
- the median of five `validate --help` runs;
- the full suite as the median of three runs at `-n 4`, with coverage variables removed.

It also records the machine (OS, CPU, cores, Python; no hostname or paths) and the settings, including which extras are installed. `--check` re-measures and prints `baseline -> current (delta)` for every number. Nothing exits non-zero on a number.

Baseline values (all extras installed, Python 3.12):

| Metric | Value |
| --- | --- |
| Package | 377 files, 77,423 lines |
| Tests | 446 files, 85,004 lines |
| Docs | 50 files, 10,253 lines |
| Test functions / collected items | 4,002 / 6,889 |
| C901 findings (waivers ignored) | 18 |
| `noqa: C901` comments | 19 |
| Lines over 100 characters | 9,292 |
| Canonical commands / aliases | 74 / 0 |
| Config + policy keys | 24 + 24 |
| `validate` imports | 138 `specy_road` modules, 497 modules in total, over 2 processes (the CLI re-launches the bundled script) |
| `validate --help` | 0.34 s |
| Suite median | 505.41 s (runs 462.45, 512.96 and 505.41, all exit 0) |

The suite times were taken while other sessions loaded this machine (load average 6 to 11).

**Validate import count (Done but wrong #3).** The baseline records what it counts: `specy_road` modules and all modules are both stored, together with the method and the command. The method is `PYTHONPROFILEIMPORTTIME=1`, distinct names over every Python process. The command runs what the `specy-road` console script runs, from the checkout root. After M16.2.9 removes the re-launch, the same count comes from one process.

**A3 (`--contexts`).** It writes a coverage rcfile under `work/lean/` from pyproject's `source` and `branch`, with `context = ${SPECY_ROAD_LEAN_CONTEXT-}`. It then runs the suite with `COVERAGE_PROCESS_START` set, so coverage's `.pth` starts measuring in every Python process, and with `-p scripts.lean_metrics`. That plugin hook switches the worker's context to the test id and exports it for CLI children. Finally it combines the data and streams `{test id: {file: [[from, to], ...]}}` to `work/lean/contexts.json`, recording the commit, the pytest command, pytest's exit code and the coverage version. It is never run in CI.

I ran it in full at `674dc189`: pytest exited 0 (6,880 passed), and the run took 13 to 22 minutes at `-n 4` depending on machine load. It wrote 6,506 test contexts and 9.4M arcs (`contexts.json` is 114 MB, plus 348 MB of raw data under `work/lean/contexts-data`). The other 374 items run no `specy_road` code. The subprocess-only tests in `tests/test_cli_version.py` carry `specy_road/cli.py` arcs under their own test ids.

An earlier full run exited 1 even though all tests passed. During it, I had run `specy-road digest --check` on the dogfood fixture, which creates the ignored `tests/fixtures/specy_road_dogfood/.specyrd/cache/`, and the suite's fixture guard (`tests/conftest.py`) fails a run when the fixtures' git status changes mid-run. Do not run dogfood commands while the suite runs.

**A4 (coverage floor).**

- **Configuration:** `[tool.coverage.run]` has `source = ["specy_road"]`, `branch = true`, `patch = ["subprocess"]` (which implies parallel data files) and `data_file = "work/.coverage"`. The data file sits under the gitignored `work/`, so child processes never leave untracked files in the checkout.
- **Floor:** `fail_under = 90`. That is the TOTAL of 90.57% (lines 92.27%, branches 85.49%) measured in a CI-equivalent venv (Python 3.12, `pip install -r requirements-ci.txt` only) on the package and tests that are byte-identical at `ef2690ed`, rounded down.
- **CI:** `coverage run -m pytest -n auto`, `coverage combine`, `coverage json --fail-under=0`, then a printed branch percentage (informational), then `coverage report`, which exits 2 below the floor.

Measured locally on that venv: 6,880 passed and 9 skipped under coverage, with 3,237 data files from workers and CLI children.

**Subprocess capture (Done but wrong #1).** `cli.py` lines 399–400 (`if __name__ == "__main__": main()`) are reachable only in a `python -m specy_road.cli` child. In a coverage run of `tests/test_cli_version.py` alone, they show as executed.

**Cost ("If this fails").** At `-n 4`, the suite under coverage took 895 s (one run, before the timings below). Without coverage, the three runs took 462–513 s, with the machine loaded by other sessions. That is roughly 1.8x. I did not measure CI's own time.

**A5 and A6.** `constraints/README.md` has two new sections:

- **M16 rules:** behaviour-preserving with the two named exceptions; informational line estimates; no knob without a removal; feedback parked; the five-condition review-finding test rule; the same-class rescope and four-round limits; what reviewers check.
- **M16 quality rules (revision 3):** every item of A6, in its order.

Two table rows (coverage floor, baseline metrics) and a short section say how the floor and the script work.

**A7 (estimate).** Package 0. Scripts +498 (`lean_metrics.py`); it is above the +200 estimate mostly because of the 70-line subsystem table, the docstrings and the `--contexts` capture. Config, CI and docs +115. The generated baseline JSON is +310.

**A8 (governance copies).** `constraints/README.md` and `sr/constraints/README.md` changed in the same commit (`674dc189`). Every relative link in both resolves. `constitution/` and `file-limits.yaml` are unchanged.

## Verification

- At `ef2690ed`: `pytest tests/parity -n 4` exited 0.
- At `674dc189`: these all exited 0:
  - `specy-road validate`, `export --check` and `digest --check` with `--repo-root tests/fixtures/specy_road_dogfood`;
  - `specy-road file-limits`;
  - `ruff check specy_road tests scripts`;
  - `python scripts/check_clones.py`;
  - `python scripts/check_test_private_imports.py` (one stale entry that was already there);
  - `python scripts/check_machine_paths.py`.
- `pip-audit -r requirements-ci.txt`: no known vulnerabilities.
- The READY record re-runs, in this order: the suite under the committed coverage configuration (CI-equivalent venv, `-n 4`); `lean_metrics --check`; file-limits; ruff; and the dogfood gates. `digest --check` goes last because the cache it creates would make the next pytest run refuse to start.

## Not done / risks

- **CI not exercised.** The workflow was not run on GitHub, because this leaf does not push. Its commands ran locally, and the YAML parses (`tests/test_release_harness.py`).
- **Small margin.** The floor's margin is 0.57 points. A CI TOTAL that differs from the local one (another runner, flaky subprocess capture) could fail it. Because CI installs the same lock on Python 3.12, I expect the same TOTAL.
- **Classifier gaps.** The subsystem classifier is a port, not the scratchpad tool, so its numbers are not comparable with the 2026-11-05 report's table. `other` still holds 4 package files and 12 test files, such as `__init__`, `conftest`, `helpers` and `verify_cmd*`.
- **No tests.** `scripts/lean_metrics.py` has no tests, because no test path is in this leaf's zones. Every number it writes was checked by hand against a direct count (ruff, `git ls-files`, pytest's own collection count of 6,880 + 9 = 6,889).

## Added

- `scripts/lean_metrics.py`, a new script (A2, A3). Its functions, each with its reason:
  - `run`, `git`, `tracked`, `read`: subprocess and git plumbing pinned to the checkout root, so the numbers are of this checkout.
  - `subsystem`, `PATH_RULES`, `STEM_RULES`: the per-subsystem split A2 asks for.
  - `lines_and_files`, `docs_group`: lines and files per group.
  - `is_test_file`, `test_functions`: test functions.
  - `collected_items`: collected items.
  - `ruff_counts`, `per_area`: C901 findings and lines over 100, by area.
  - `noqa_c901`: the waiver count.
  - `commands`: canonical command and alias counts.
  - `config_keys`: config and policy keys.
  - `validate_imports`: modules `validate` imports, with method and command recorded (Done but wrong #3).
  - `timed`, `coverage_off_env`, `validate_help_seconds`, `suite_seconds`: wall times; coverage is off for the suite.
  - `extras_installed`, `distribution_installed`, `cpu_model`, `machine`, `settings`: settings and machine recorded.
  - `measure`: assembles the record, including the `clean` flag (Done but wrong #2).
  - `numbers`, `print_deltas`: `--check`.
  - `contexts_rcfile`, `pytest_runtest_logstart` (the plugin hook), `capture_contexts`, `write_contexts`: `--contexts`.
  - `main`: the three modes.
- Branches and guards in the script:
  - the `/proc/cpuinfo` fallback in `cpu_model`: macOS has no `/proc`;
  - `PackageNotFoundError` in `distribution_installed`: an extra that is not installed is recorded as false;
  - the mutually exclusive `--check` and `--contexts`: one mode per run.
- `pyproject.toml`:
  - `coverage==7.17.2` in `dev`: the maintainer approved it on 2026-11-07, exact pin;
  - `[tool.coverage.run]` and `[tool.coverage.report]`: A4.
- `.github/workflows/validate.yml`: the coverage test step (A4) and its inline branch-percentage print (informational).
- `constraints/lean-baseline.json`: A1, A2.
- `constraints/README.md` and its `sr/` copy: two table rows, the "Coverage floor and baseline metrics" section, and the "M16 rules" and "M16 quality rules" sections (A5, A6, A8).
- Mocks: none.
- Tests: none (no test path in this leaf's zones).
