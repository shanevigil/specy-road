# Implementation summary: M9.7 `suppression-and-ratchet-findings`

## What changed

- `specy_road/integrity.py`: `compare_integrity` now also reads the lines
  `base..ref` adds (one `git diff --unified=0` over git objects, paths
  git-root-relative via `--no-relative`) and reports two new finding kinds:
  - `new-suppression: <path>:<line>` (A1) — each added line, in any file, that
    contains `noqa`, `type: ignore`, `pragma: no cover`, `pylint: disable`,
    `eslint-disable`, `@ts-ignore`, `@ts-expect-error` or `nolint`. Matching is
    case-insensitive and allows any spacing after a colon (`# NOQA`,
    `# type:ignore`). `<line>` is the line number at REF.
  - `baseline-widened: <path> +<added lines>` (A2) — for each path in
    `policy.ratchet_paths`, read from the integration branch through
    `review_policy_ref.policy_source` + `orchestration_config.effective_config`
    (the same ref the M9.6 gate reads policy from). A removal-only diff adds no
    lines, so it prints nothing. When the integration branch or its
    orchestration file cannot be read, no ratchet paths apply.
  The review packet's **Test integrity** section and the M9.6 integrity gate
  call `compare_integrity`, so they pick up both kinds with no change there.
- `specy_road/templates/project/schemas/orchestration.schema.json` and its
  copy `sr/schemas/orchestration.schema.json`: new optional
  `policy.ratchet_paths` (unique non-empty strings).
- `sr/roadmap/orchestration.yaml` (A3): lists
  `constraints/clone-baseline.json`, `constraints/test-private-imports-baseline.txt`,
  `constraints/mutation-baseline.json` and `constraints/file-limits.yaml` under
  `policy.ratchet_paths`.
- `docs/orchestration-review.md`, `CHANGELOG.md`: describe the two findings and
  the key.
- `tests/test_integrity_ratchet.py` (A4): fixture git repositories through the
  `specy-road integrity` CLI, asserting the exact output and exit code.

## Touch zones (final)

Used: `specy_road/integrity.py`, `specy_road/templates/project/schemas/orchestration.schema.json`,
`sr/schemas/`, `sr/roadmap/orchestration.yaml`, `docs/orchestration-review.md`,
`CHANGELOG.md`, `tests/`. Not needed: `schemas/` and `roadmap/orchestration.yaml`
at the git root (neither exists there).

Not edited because they are outside the zones (cosmetic, no behaviour depends on
them): the `argparse` description in
`specy_road/bundled_scripts/integrity_cli.py` still lists only the M9.5
findings, and `test_integrity_section`'s `_none_` wording in
`review_packet.py` still says "agree on tests".

## Notes for reviewers

- This leaf's own diff gets `new-suppression` findings: the marker words appear
  in the regex in `integrity.py`, in the test parameters, and in the docs and
  CHANGELOG text. `integrity_gate` is off in `sr/roadmap/orchestration.yaml`, so
  they are informational only.
- A diff git cannot decode as UTF-8 makes `git_stdout` return `None`, and then
  neither new finding kind reports for that comparison (the M9.5 findings are
  unaffected).
- Renames are detected (`--find-renames`), so moving a file that already holds
  a suppression does not report it; edits inside the moved file still do.

## Verification

- `pytest` (full suite, run in three batches to fit the foreground limit): all passed (see READY).
- `ruff check specy_road tests scripts`: clean.
- `python scripts/check_clones.py --pylint <pylint 4.1.3 via uvx>`: 0 new (pylint is not installed in the env).
- `python scripts/check_test_private_imports.py`: 0 new.
- `specy-road validate` (sr) and `validate` / `export --check` / `digest --check` on the dogfood fixture: OK.
- `specy-road file-limits`: only `docs/brainstorming.md: 406 lines`, which is already 406 lines at the base commit (not touched here).

## Added

### Helpers
- `integrity.integration_ratchet_paths` — reads `policy.ratchet_paths` from the integration branch so a leaf cannot drop its own baselines from the list (A2).
- `integrity._added_lines` — parses `git diff -U0` into added lines with their REF line numbers; both new findings need them (A1, A2).
- `integrity._suppression_findings` — one `new-suppression` per added line matching a marker (A1).
- `integrity._ratchet_findings` — one `baseline-widened` per ratchet path with added lines (A2).
- `_SUPPRESSION`, `_HUNK` regexes — the marker list (A1) and the hunk header's new-side start line.

### Branches / guards
- `Finding.line` gains the `new-suppression` and `baseline-widened` forms (A1, A2).
- `_added_lines` reads `+++` only in a file header (`in_header`), so an added content line starting with `++` is not mistaken for a file name; a C-quoted name is unquoted; `/dev/null` (deletion) has no added lines.
- `integration_ratchet_paths` returns `[]` when the policy ref or file is unreadable, and drops non-string entries.

### Mocks
- none

### Tests (`tests/test_integrity_ratchet.py`)
- `test_new_suppression_prints_path_and_line_and_exits_one` (×8, one per marker) — A1/A4 exact line + exit 1.
- `test_existing_suppression_moved_by_an_insert_is_not_new` — only added lines count, not shifted ones.
- `test_baseline_widened_prints_added_line_count_and_exits_one` — A2/A4 exact line + exit 1.
- `test_baseline_removal_only_exits_zero` — A2/A4 removal-only gives exit 0.
- `test_ratchet_paths_listed_only_on_the_leaf_branch_are_ignored` — the list comes from the integration branch, not the leaf.
- `test_nested_project_ratchet_path_outside_the_project` — git-root-relative path outside a nested project root (the regression-2 shape).
