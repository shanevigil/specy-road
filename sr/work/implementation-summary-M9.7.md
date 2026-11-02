# Implementation summary: M9.7 `suppression-and-ratchet-findings`

## What changed

- `specy_road/integrity.py`: `compare_integrity` now also reads the lines
  `base..ref` adds and reports two new finding kinds. It lists the changed
  files with `git diff --name-status -z --find-renames` (exact git-root paths,
  rename pairs kept) and runs one `git diff --unified=0` per file, limited by a
  `:(top,literal)` pathspec, reading only the hunks:
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
- Review round 1 (gpt-6.1-sol, R1/R2) fixed: a single whole-branch diff let one
  non-UTF-8 file blank both findings, and patch-header parsing kept git's tab
  after a name with spaces. Now a file whose diff git output cannot decode as
  UTF-8 loses only its own lines, and paths come from `--name-status -z`, never
  from a `+++` header. Origin `WIP/improvements-0-3-1` was merged in (1ae66df),
  which brings the `docs/brainstorming.md` file-limits fix (9b82c16).
- Review round 2 (gpt-6.1-sol) fixed: that file still lost all its own added
  lines, so a non-UTF-8 line in a configured baseline hid its widening and its
  suppressions. The per-file diff is now read as bytes and decoded with
  `errors="replace"`, so line counts and ASCII markers survive. `integrity.py`
  spawns this one git call itself (`_patch`) because `git_subprocess.run`
  decodes strictly. The `git_subprocess` module docstring, which lists the
  callers that spawn git themselves, is outside this leaf's touch zones and
  does not mention this one yet.
- Review round 3 (gpt-6.1-sol) fixed: the leaf's own `.gitattributes` could mark
  a file `-diff` (or `binary`), and git then printed "Binary files differ" with
  no hunks. Every content diff now passes `--text`, plus `--no-textconv`,
  `--no-ext-diff` and `--no-relative` (the shared `_DIFF` flags). Audit of other
  ways to hide additions:
  - textconv drivers and `diff.external` / `diff=<driver>` commands are
    disabled by flags; tests cover both.
  - `diff.relative` in repo config: `--no-relative` on both git calls.
  - the leaf's `.gitattributes`: with these flags only `xfuncname` still has an
    effect, and it changes the hunk-header text after the line number, which is
    not parsed.
  - `git show <blob>`, used to read the policy from the integration branch,
    applies no textconv or binary classification (checked by hand).
  - **renames (found in this audit):** with rename detection, `git mv` of an
    existing file onto a ratchet path that does not exist yet
    (`constraints/mutation-baseline.json` does not) showed zero added lines.
    `_ratchet_findings` now diffs each ratchet path on its own with
    `--no-renames`, so every line of the moved file counts. Suppression
    findings still follow renames, so a moved file's existing markers are not
    reported as new.
  - not handled: submodule gitlinks have no file lines, and repo-local config
    or environment set by whoever runs the command is out of scope (the
    leaf's commit cannot carry either).
- Escalation fix (RCA-4, round 5): `_changed_files` read `--name-status -z`
  through the strict `git_stdout`, so one non-UTF-8 file name dropped every
  path and an ordinary `# noqa` went unreported. It now reads bytes
  (`_git_bytes`, shared with `_patch`), splits on NUL and decodes each name.
  A name that is not UTF-8 is skipped. A rename whose source name is not UTF-8
  keeps its destination alone, so all of that file's lines count. Observed and
  left alone, as instructed (no other encoding class opened): the M9.5 code
  paths (`_tree_paths` via `ls-tree`, and `diff_paths` for config changes) still
  read names through the strict `git_stdout`.
- Round 6 (gpt-6.1-sol R1): a type change (symlink to regular file) is two
  patch sections. `_hunk_additions` stayed in hunk mode after the first
  section's `@@`, so it counted the second section's `+++ b/<path>` header as
  an added line. That inflated baseline counts, and a marker in the file name
  gave a false `:0` suppression. A `diff --git` line now ends hunk mode, so
  only lines inside each section's hunks count.
- Renames are detected (`--find-renames`), so moving a file that already holds
  a suppression does not report it; edits inside the moved file still do.

## Verification

- Round 6: `pytest tests/test_integrity_ratchet.py tests/test_integrity.py tests/test_integrity_python.py tests/test_integrity_gate.py tests/test_review_packet.py tests/test_validate_file_limits.py`: 90 passed. Round 1 ran the full suite in three batches; only the file-limits test failed, on the then-unfixed `docs/brainstorming.md`.
- `ruff check specy_road tests scripts`: clean.
- `python scripts/check_clones.py --pylint <pylint 4.1.3 via uvx>`: 0 new (pylint is not installed in the env).
- `python scripts/check_test_private_imports.py`: 0 new.
- `specy-road validate` (sr) and `validate` / `export --check` / `digest --check` on the dogfood fixture: OK.
- `specy-road file-limits`: OK after the merge.

## Added

### Helpers
- `integrity.integration_ratchet_paths` — reads `policy.ratchet_paths` from the integration branch so a leaf cannot drop its own baselines from the list (A2).
- `integrity._added_lines` — added lines with their REF line numbers, one diff per changed file (A1, A2; R1).
- `integrity._patch` — runs that per-file diff and decodes the bytes leniently, so a non-UTF-8 line keeps its file's count and markers (round 2).
- `integrity._git_bytes` — raw git stdout, never raises, empty on failure or timeout; used by `_patch` and `_changed_files` (round 5).
- `integrity._utf8` — strict decode of one file name, `None` when it is not UTF-8 (round 5).
- `integrity._changed_files` — changed paths and rename pairs from `--name-status -z` read as bytes, so paths with spaces or quotes are exact (R2) and a non-UTF-8 name drops only itself (round 5).
- `integrity._hunk_additions` — the `+` lines inside the hunks of one file's `-U0` patch, every section of it.
- `integrity._suppression_findings` — one `new-suppression` per added line matching a marker (A1).
- `integrity._ratchet_findings` — one `baseline-widened` per ratchet path with added lines, each diffed with `--no-renames` (A2; round 3).
- `integrity._file_additions` — one file's (or rename pair's) added lines; shared by both findings.
- `_DIFF` flags — `--text --no-textconv --no-ext-diff --no-relative`, so attributes and drivers cannot hide added lines (round 3).
- `_SUPPRESSION`, `_HUNK` regexes — the marker list (A1) and the hunk header's new-side start line.

### Branches / guards
- `Finding.line` gains the `new-suppression` and `baseline-widened` forms (A1, A2).
- `_hunk_additions` ignores each section's header (from `diff --git` to its first `@@`), so header lines are never content even in a two-section type change (round 6); a deleted or binary file has no hunks and adds nothing.
- `_git_bytes` returns `b""` when git fails, times out or cannot start, so that file adds nothing.
- `_changed_files` skips a record whose destination name is not UTF-8 and drops an undecodable rename source (round 5).
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
- `test_non_utf8_file_in_the_diff_hides_no_other_finding` — R1 and round 2: an unrelated non-UTF-8 file, and non-UTF-8 text plus a suppression in the configured baseline itself; `baseline-widened ... +2`, the baseline's `new-suppression` and the other file's, exit 1.
- `test_paths_with_spaces_are_reported_and_matched_exactly` — R2: exact suppression line and baseline match for paths with spaces, exit 1.
- `test_attributes_and_diff_drivers_do_not_hide_additions` (×4: `-diff`, `binary`, textconv driver, external diff command) — round 3: a configured baseline the leaf hides from diff still gives `baseline-widened ... +1` and its `new-suppression`, exit 1.
- `test_file_renamed_onto_a_new_ratchet_path_widens_it` — round 3 audit: `git mv` onto a not-yet-existing ratchet path gives `+<all lines>`, exit 1.
- `test_non_utf8_file_name_hides_no_other_finding` — round 5: a committed name with a 0xff byte beside `src/mod.py`'s added `# noqa`; prints `new-suppression: src/mod.py:1`, exit 1.
- `test_symlink_to_regular_file_counts_only_hunk_lines` — round 6: a ratchet baseline named `noqa-baseline.txt` goes from symlink to a two-line file; prints only `baseline-widened: ... +2`, exit 1 (was `+3` plus a false `:0` suppression).
