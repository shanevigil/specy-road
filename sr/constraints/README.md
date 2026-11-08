# Constraints (specy-road toolkit)

This directory applies to **this repository** — the `specy-road` Python package and docs — not to consumer projects created with `specy-road init project`.

Test-fixture roadmap validation uses the consumer-shaped sample tree under [`tests/fixtures/specy_road_dogfood/`](../../tests/fixtures/specy_road_dogfood/). That tree is not the toolkit's own product roadmap.

| Rule | Where | Check |
| ---- | ----- | ----- |
| Max file length (any matched glob) | [`file-limits.yaml`](file-limits.yaml) | `specy-road file-limits` |
| Max function length (**Python** `.py` via stdlib `ast`; **TS/JS** `.ts` `.tsx` `.js` `.jsx` `.mjs` via a bracket scanner) | same | same |
| Optional: `exclude_path_globs`, `override_limits`, `hard_alerts` | same | same (`--strict-hard-alerts` fails on warnings) |
| Roadmap manifest / JSON chunk line caps | same (`roadmap_*_max_lines` keys) | `specy-road validate` (via roadmap loader) |
| Dogfood test-fixture roadmap graph | `tests/fixtures/specy_road_dogfood/roadmap/` | `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` |
| Coverage floor (line and branch TOTAL, CLI subprocesses included) | [`pyproject.toml`](../../pyproject.toml) `[tool.coverage.*]` | CI: `coverage run -m pytest -n auto`, `coverage combine`, `coverage report` |
| Lean-core baseline metrics (measurements, never a gate) | [`lean-baseline.json`](../../constraints/lean-baseline.json) | `python scripts/lean_metrics.py --check` |

Per-function / `hard_alerts.max_lines_per_function` apply to **`.py`** and **`.ts` `.tsx` `.js` `.jsx` `.mjs`** sources. TS/JS coverage is `function` declarations, arrow functions bound by `const`/`let`/`var`, and class methods ([`specy_road/file_limits_js.py`](../../specy_road/file_limits_js.py)); unnamed callbacks are not measured. **Other files** matched by `applies_to_globs` are checked for **line count per file** only; use your stack’s analyzers in CI for other languages.

**Skipped before `applies_to_globs` is applied:** git-ignored files (opt out with `--no-respect-gitignore`), the toolkit's own `work/` session artifacts, and archived roadmap material under `roadmap/archive/` (a scaffold's `**/*.md` glob would otherwise keep flagging planning sheets for milestones that shipped years ago). See [`specy_road/file_limits_engine.py`](../../specy_road/file_limits_engine.py) (`SESSION_ARTIFACT_GLOBS`).

## Coverage floor and baseline metrics

`[tool.coverage.run]` in [`pyproject.toml`](../../pyproject.toml) measures `specy_road` with branch arcs and, through `patch = subprocess`, every Python child the suite starts (pytest-xdist workers and `specy-road` CLI runs). `[tool.coverage.report] fail_under` is that configuration's TOTAL at the baseline commit, rounded down to a whole percent. CI runs the same configuration and fails below it; the branch percentage it prints is informational. Run it locally with `coverage run -m pytest -n 4`, then `coverage combine` and `coverage report`.

[`lean-baseline.json`](../../constraints/lean-baseline.json) records the M16 starting point at one commit: package and test lines and files per subsystem, docs lines and files, test functions and collected items, ruff C901 findings and `noqa: C901` waivers, lines over 100 characters, the canonical command and alias counts, config and policy keys, the modules `specy-road validate` imports, and wall times, with the machine and settings. [`scripts/lean_metrics.py`](../../scripts/lean_metrics.py) writes it; only M16.8.1 and maintainers rewrite it. A leaf reports `python scripts/lean_metrics.py --check` deltas in READY. None of those numbers is a gate: the coverage floor is the only one that fails CI. `--contexts` (opt-in, never in CI) writes each test's covered arcs to `work/lean/contexts.json` for the test-lane leaves.

## M16 rules (lean core)

Every M16 leaf follows these rules; review checks them.

- **Behaviour is preserved.** The parity harness ([`tests/parity/`](../../tests/parity/README.md)), the review-gate decision table and the leaf's own parity tables stay green. Two named exceptions add behaviour: zone-scoped `checks:` gates (M16.4.6) and the complexity gate (M16.5.14).
- **Line estimates are informational.** Each leaf carries an estimated line change as its last acceptance line; it is never a gate.
- **No new knob without a removal.** No new config key, policy key or command without retiring one.
- **Adopter feedback is parked** until M16 ends.
- **Review-finding test rule.** A fix adds a test only when all five hold:
  1. it fails before the fix and passes after;
  2. it checks something no existing test checks, and a new input to tested behaviour is a new row in that behaviour's table rather than a new test;
  3. it is written at the cheapest level that reproduces the bug;
  4. it lives in the module's test file and is named for the behaviour, not the round;
  5. it asserts structured results, not message text.
- **Round limits.** After a second block of the same class, the planner rescopes or splits the leaf. A leaf past four review rounds is split or rescoped.
- **What reviewers check.** The acceptance lines and the leaf's parity tables. A new input class goes to the intake.

## M16 quality rules

Maintainer, 2026-11-05, revision 3: the goal is quality, not lines.

- **Behaviour is preserved:** the parity harness, the decision table and the leaf's own tables.
- **Code a leaf touches moves toward best practice:**
  - small single-purpose functions;
  - clear module boundaries and no new import cycle (M16.2.6);
  - explicit dependencies: module globals, and functions that call the clock or git themselves, are given those as parameters where a test needs a seam, with no dependency-injection framework;
  - one statement of each rule rather than copies.
- **No touched function rises in complexity** (the M16.5.14 rule).
- **Docstrings and comments that explain intent are kept or improved,** never stripped to save lines.
- **Names say what the code does.**
- **No code squashing:** no joined statements, removed blank lines, shortened names or deleted explanations to meet a number.
- **The quality metrics never regress in a leaf:** M16.1.8's ruff family baseline, line width, and M16.2.6's layering gate.
- **Line-count estimates are informational:** never by themselves a review finding or a gate.
