# Implementation summary: M9.10 (red-green-evidence)

## What changed

- **`specy_road/red_green.py`** (new). `tests_under_check(root, base, head)` lists git-root-relative
  pytest node ids for every test function (`test_*` at module or class scope, scoped as
  `integrity._test_functions` scopes them) in a changed `test_*.py` / `*_test.py` whose source
  (decorators included) differs between base and head, or that exists only at head (A1).
  `run_red_green` builds a detached temporary worktree of the merge base, overlays the head's blobs
  of just the test files that hold tests under check, then a detached temporary worktree of head;
  in each it runs `python -m pytest -q -p no:cacheprovider --junitxml=<tmp> <node id>` once per
  test from the worktree's git root and classifies the JUnit XML (`junit_outcome`): any `<error>` →
  `error`, else any `<failure>` → `fail`, else `pass` when a case ran unskipped, else `error`
  (not found, all skipped). Both worktrees are removed in `finally` (A2, A5).
  `cmd_red_green` writes `work/reviews/<ID>/RED-GREEN.md` (`commit`, `base`, `tests: [{test, base,
  head}]`), prints each row and the problems, exits 1 on any problem.
  `outcome_problems` applies A3: a `preserve: <path>::<name>` test must pass at base and head
  (`not-green` otherwise); any other must pass at head (`not-green`) and fail at base (`not-red`);
  one problem per test. `red_green_problems` is the gate side: `red-green: missing` (absent or
  unreadable), `red-green: stale (<sha12>)` (commit is not the commit under review, via
  `same_commit`), else `outcome_problems` over tests recomputed from git, so a row left out of the
  record is a problem (A4).
- **`specy_road/integrity_gate.py`**: `integrity_gate_problems` now also runs the red-green check
  when `policy.red_green` is on (policy and `planned_test_changes` from the integration branch, as
  for M9.6). The merge base is computed once; with only red-green on, a missing base is reported as
  `red-green: no merge base …` (fails closed). Integrity-gate output is unchanged.
- **`specy_road/bundled_scripts/review_cli.py`**: registers `review red-green <ID> [--ref]`
  (file is now exactly at the 400-line cap).
- **Schemas**: `policy.red_green` (boolean, default false) in
  `specy_road/templates/project/schemas/orchestration.schema.json` and `sr/schemas/orchestration.schema.json`.
- **Docs**: `## Red-green evidence` in `docs/orchestration-review.md`; CHANGELOG `[Unreleased]` entry.

## Decisions

- Python/pytest is run with `sys.executable` (the interpreter running specy-road) from the
  worktree's git root, so the worktree's own packages win over an editable install.
- One pytest process per test, so a collection error or unknown node id in one test cannot
  hide the others.
- A missing or stale record yields only that one problem, not per-test problems as well.
- With the policy on and no tests under check, the record is still required (A4 literal); the
  command writes an empty `tests: []` record without creating worktrees.
- A test that errors at base (e.g. it imports a function only the leaf adds) is `not-red`, per A3.

## Touch zones

Final list used: `specy_road/red_green.py`, `specy_road/integrity_gate.py`,
`specy_road/bundled_scripts/review_cli.py`, `specy_road/templates/project/schemas/orchestration.schema.json`,
`sr/schemas/`, `docs/orchestration-review.md`, `CHANGELOG.md`, `tests/`. `schemas/` (git root) does
not exist and was not needed.

Follow-ups outside the zones (not edited): `suggested_prompts/bootstrap-roadmap.md` (lists policy
keys and `planned_test_changes`), `docs/roadmap-authoring.md` and
`specy_road/templates/project/schemas/roadmap.schema.json` (the `planned_test_changes`
description mentions only integrity finding lines, not `preserve: <id>`).

## Verification

- `pytest tests/test_red_green.py tests/test_integrity_gate.py tests/test_review_pre_existing.py` — 28 passed.
- `specy-road file-limits` — OK. `ruff check specy_road tests scripts` — all passed.
- `scripts/check_clones.py` (pylint 4.1.3 via uvx) — 0 new. `scripts/check_test_private_imports.py` — 0 new.
- Full suite, all `tests/test_*.py` in 4 parallel shards of `python -m pytest -q -p no:cacheprovider` — 2829 passed, 2 skipped, every shard exit 0.

## Added

### Helpers
- `red_green.tests_under_check` — A1 selection of tests under check from git objects.
- `red_green._test_sources` — per-test source text (with decorators) for the "source differs" comparison.
- `red_green.junit_outcome` — maps one pytest JUnit XML to pass / fail / error (A2).
- `red_green._outcomes_at` — one detached temporary worktree, optional overlay, one pytest per node id, always removed (A2, A5).
- `red_green.run_red_green` — base-with-overlay then head runs, `{test, base, head}` rows.
- `red_green.outcome_problems` — A3 rule, one `not-red`/`not-green` per offending test.
- `red_green.red_green_problems` — A4 gate side: missing / stale / per-test problems.
- `red_green.cmd_red_green` — the `review red-green` command; writes `RED-GREEN.md`.

### Branches and guards
- `integrity_gate_problems`: red-green branch when `policy.red_green`; shared merge-base fail-closed with a `red-green:` prefix when only red-green is on.
- `red_green_problems`: rows whose outcomes are not in {pass, fail, error} are dropped (no evidence), so a malformed record cannot raise.
- `cmd_red_green`: lazy import of `integrity_gate.planned_test_changes` (that module imports `red_green`).
- `_outcomes_at`: worktree creation failure returns an error and removes the temp dir.

### Mocks
- none

### Tests (`tests/test_red_green.py`)
- `test_tests_under_check_are_the_added_and_changed_test_functions` — A1: changed, new-in-file and new-file tests; unchanged one excluded.
- `test_record_has_one_outcome_per_test_at_base_and_head` — A2 record shape and outcomes (fail→pass, pass, error at base, preserve), A5 worktree list unchanged.
- `test_gate_flags_tests_that_pass_or_error_at_base` — A3/A4: already-passing and erroring-at-base tests are `not-red`; red-green and preserve tests clean.
- `test_gate_flags_a_missing_record_and_ignores_evidence_with_the_policy_off` — A4 `red-green: missing`; policy off leaves the gate unchanged.
- `test_gate_flags_a_stale_record` — A4 `red-green: stale (<sha>)`.
- `test_preserve_must_pass_on_both_and_others_must_go_red_to_green` — A3 preserve failing at head, regular failing at head, test without a row.
- `test_no_integration_ref_fails_closed` — gate fails closed with only red-green on.
- `test_schema_accepts_the_policy` — schema accepts boolean `red_green`, rejects a string.
