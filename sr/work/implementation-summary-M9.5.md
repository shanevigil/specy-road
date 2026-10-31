# Implementation summary: M9.5 — integrity-report

## What shipped

- **`specy_road/integrity.py`** — Pure comparison of two commit SHAs: lists test files at each tip via `git ls-tree`, loads Python test modules with `git show` + AST, and diffs changed paths for pytest config files. Emits sorted `Finding` rows (text line + JSON dict).
- **`specy-road integrity <NODE_ID>`** — Resolves base and reviewed commit through `review_target` (same as `review-packet`), prints one finding per line (exit 1) or silent exit 0; `--json` prints findings only when non-empty.
- **`review-packet`** — Inserts **Test integrity** after **Changed paths** using the same `compare_integrity` call; deterministic for fixed base/head SHAs.
- **Docs / CLI usage / CHANGELOG** — User-facing mention of the command and packet section.

## Touch zones (confirmed)

`specy_road/integrity.py`, `specy_road/bundled_scripts/integrity_cli.py`, `specy_road/cli.py`, `specy_road/cli_usage.py`, `specy_road/bundled_scripts/review_packet.py`, `docs/orchestration-review.md`, `CHANGELOG.md`, `tests/`

## Review round 1 fix (claude-fable-5-1)

The Grok review of `00261f8` blocked on A3: a bare `@pytest.mark.xfail` (the no-argument form) was not
reported as `new-skip`, because `_decorator_skips` only recognised pytest marks when the decorator node was a
`Call`. Commit `92ffc0a` adds the `Attribute` branch for `pytest.mark.xfail` / `pytest.mark.skipif` using the
existing `_is_pytest_mark` check, and a fixture-repo test asserting the exact `new-skip` line. No other
behaviour changed.

## Review round 2 fix (claude-fable-5-1)

The gpt-6.1-sol review of `eb34aa1` blocked on four items, fixed in commit `a3d2b3f`:

- **A3** — `_decorator_skips` now matches only `pytest.mark.skip` / `skipif` / `xfail` and `unittest.skip` /
  `skipIf` / `skipUnless` (attribute on `unittest`, or the bare imported name), bare or called. An unrelated
  `@custom.skip` is no longer a finding. `expectedFailure`, which the acceptance text does not name, is no
  longer matched.
- **A4** — `_assert_count` counts `pytest.raises` as a `Call` node, so the context-manager and callable forms
  each count exactly once; the `With` branch is gone.
- **A5** — `_pytest_table_text` strips each line before matching a `[tool.pytest*]` or following table header,
  so indented TOML headers are seen.
- **A6** — a parametrized CLI test runs every finding form (removed-test, removed-test-file, new-skip,
  assert-loss, config-change) and asserts the complete stdout and exit 1; a text-mode unchanged ref asserts
  exit 0 and empty output. A deleted Python test file prints both its `removed-test-file` line and one
  `removed-test` line per function, as the round-1 review noted.

## Review round 3 fix (claude-opus-5.5)

The gpt-6.1-sol review of `799ef95` blocked on two defects and one excess, fixed in commit `44dba2a`:

- **R1 (A1-A4, A7)** — `_tree_paths` runs `git ls-tree --full-tree`, so a nested project root (`sr/` under the
  git root) lists every test with git-root-relative paths, matching what `git show <sha>:<path>` and
  `diff_paths` already use. It reads raw stdout (`git_stdout`) so the NUL-split names are never stripped.
  `test_nested_project_root_reports_git_root_paths` puts the roadmap under `sr/`, weakens a test inside it and
  deletes one outside it, and asserts the exact CLI output, exit 1 and the same lines in the packet's
  `test_integrity_section`. It fails on `799ef95`.
- **R2 (A5)** — the line-based `[tool.pytest` header scan is replaced by `_pytest_tables`, which parses
  `pyproject.toml` with `tomllib` and compares the `tool` keys starting with `pytest`, so quoted
  (`["tool"."pytest"."ini_options"]`), dotted and indented spellings are all one table. A `pyproject.toml` that
  does not parse is compared as raw text, so any edit to it still reports. `test_config_change_quoted_pyproject_pytest_table`
  fails on `799ef95`; the indented and non-pytest-table tests still pass.
- **E1** — `test_cli_text_line_and_exit_one` is deleted; its input class is covered, with exact stdout and exit 1,
  by `test_cli_prints_exact_line_and_exits_one_for_each_form[removed-test-file]`.

## Verification

- `pytest tests/test_integrity.py tests/test_review_packet.py` — 37 passed (round 3); full `pytest` — 2547 passed, 2 skipped
- `specy-road file-limits` — OK
- `python scripts/check_test_private_imports.py` — 0 new; one stale baseline entry predates this leaf
  (`review_packet._changed`, also absent on the integration branch) and `constraints/` is outside the zones
- `python scripts/check_clones.py` — not run (`pylint` missing in this shell)
- `specy-road integrity M9.5 --repo-root sr` on this branch — exit 0, no output

## Added

- `Finding` dataclass and `line()` / `as_json()` — stable text and JSON shapes for A2–A6.
- `compare_integrity()` — orchestrates file-tree, AST, and config diff findings.
- `_pytest_table_text()` — limited `config-change` on `pyproject.toml` to `[tool.pytest*]` tables; replaced in round 3 by `_pytest_tables()`.
- `_test_functions()` / skip and assert helpers — AST extraction for Python test modules.
- `findings_to_json()` — JSON envelope for `--json`.
- `test_integrity_section()` in `review_packet.py` — packet section after changed paths.
- `tests/test_integrity.py` — fixture repos per finding kind plus CLI exit/json tests.
- `test_new_skip_bare_xfail_decorator` — pins the A3 no-argument `@pytest.mark.xfail` form the review found missing.
- `Attribute` branch in `_decorator_skips` for `pytest.mark.xfail` / `skipif` — the fix itself; one guard, no new helper.
- `test_packet_test_integrity_section_is_stable_and_lists_findings` — byte-stable section and assert-loss in packet.
- `_UNITTEST_SKIPS` constant — the three unittest decorator names shared by the bare-name and `unittest.` branches.
- `test_unrelated_decorator_named_skip_is_not_a_skip` — A3 false-positive regression (`@custom.skip`).
- `test_assert_loss_counts_callable_pytest_raises` — A4 callable-form regression.
- `test_config_change_indented_pyproject_pytest_table` — A5 indented-header regression.
- `_TEST_SRC` / `_CLI_FORMS` table and `test_cli_prints_exact_line_and_exits_one_for_each_form` — A6 per-form CLI
  coverage with exact output and exit 1.
- `test_cli_text_mode_unchanged_ref_exits_zero_silently` — A6 unchanged-ref text-mode case.
- `--full-tree` on `_tree_paths` (and `git_stdout` in place of `git_text`) — R1: git-root-relative paths from a nested project root.
- `_pytest_tables()` (replaces `_pytest_table_text()`) — R2: tomllib reads every TOML spelling of `tool.pytest*`.
- raw-text fallback in `_pytest_tables()` on `TOMLDecodeError` — an unparseable `pyproject.toml` in a commit still reports an edit.
- `isinstance(tool, dict)` guard in `_pytest_tables()` — `tool = 1` is valid TOML and has no pytest tables.
- `project` parameter on the `_roadmap` / `_repo` test fixtures — builds the roadmap under a nested project directory.
- `test_nested_project_root_reports_git_root_paths` — R1 regression through the CLI and the packet section.
- `test_config_change_quoted_pyproject_pytest_table` — R2 regression.
- removed: `test_cli_text_line_and_exit_one` — E1, covered by the parametrized `removed-test-file` form.
- none — no new mocks; tests use real git repos under `tmp_path`.
