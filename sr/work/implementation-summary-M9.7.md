# Implementation summary: M9.7 `suppression-and-ratchet-findings`

## What changed

- `specy_road/integrity.py`: `compare_integrity` now also reads the lines
  `base..ref` adds and reports two new finding kinds. It takes the changed
  entries from `git diff --raw -z` (modes, blob ids, exact git-root path) and
  computes the added lines of each regular file or symlink from its blob pair
  (`git diff --text --no-textconv --no-ext-diff -U0 <old> <new>`). When the old
  side is not the same kind, it uses the whole new blob (`git cat-file`). No
  pathspec and no attribute is involved, so each result belongs to exactly its
  entry's path:
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
findings.

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
- Round 7 (gpt-6.1-sol R1; root cause of the path-related rounds): a literal
  pathspec also selects a directory's descendants. So when a former file became
  a directory, its descendants' lines were attributed to the old path. A
  renamed file got a child's suppression, and a deleted baseline counted as
  widened. Diffing by path is gone. `_changed_files` parses
  `git diff --raw -z --no-abbrev --no-relative` into `(path, old blob, new
  blob)`, keeping only entries whose new mode is a regular file (`100644`,
  `100755`). Deletions, submodules and symlinks are skipped, and a type change
  counts as its new regular file only (old blob `None`, so every line is new).
  `_blob_additions` diffs the blob pair with no path, or reads the whole new
  blob, because the empty blob is not an object in a repo that never stored it
  and integrity writes nothing. This also retires the earlier per-path
  mechanisms: the `:(top,literal)` pathspec, `_file_additions`, and reading
  names from `--name-status`.
  - Renames: the ratchet pass uses `--no-renames`, as specified, so a file
    moved onto a ratchet path still counts every line. The suppression pass
    keeps `--find-renames`. A rename's raw entry carries both blob ids and the
    exact destination, so no pathspec is involved, and a moved file's existing
    markers stay out of the findings. That behaviour was described since round
    1 and is now pinned by `test_moved_file_keeps_its_existing_suppressions`.
- Round 8 (A1/A2 rewritten on WIP in c55166d, merged here in 75329c5;
  gpt-6.1-sol): the new A1 counts the `+` content lines of git's default
  `-U0` diff, and that diff shows a symlink's target as one such line. Round 7
  skipped symlinks (mode `120000`), so an added `baseline-link -> target-noqa`
  at a ratchet path gave nothing. `_changed_files` now keeps regular files and
  symlinks (`_KIND`) in both passes, and still skips gitlinks and deletions.
  The old blob is used only when the old side is the same kind. A file/symlink
  type change keeps git's default semantics, a deletion plus an addition, so
  every line of the new side counts. A 100644/100755 mode change is an ordinary
  modification.
  - How this matches the new A1's wording: `--raw -z` lists the same entries
    as `--name-status -z` (with modes and blob ids added), and a `-U0`
    blob-pair diff gives the same `+` content lines as git's default diff of
    that path for a text file. `--text` also covers files the new A1 puts out
    of scope (binary by default or by attribute), so it reports more, never
    less.
  - Seen in the merge, not this leaf's change: WIP added
    `policy.stall_after_seconds` to the template orchestration schema without
    refreshing `sr/schemas/orchestration.schema.json`, so the two copies differ
    by that key on WIP itself. `ratchet_paths` is in both. Left alone as
    another leaf's drift.
  - The local `sr/work/brief-M9.7.md` is an untracked snapshot and still shows
    the old A1/A2; I worked from the rewritten text in `sr/roadmap/phases/M9.json`.

## Verification

- Round 8: `pytest tests/test_integrity_ratchet.py tests/test_integrity.py tests/test_integrity_python.py tests/test_integrity_gate.py tests/test_review_packet.py tests/test_validate_file_limits.py`: 98 passed (the merge brought more tests into these files). Round 1 ran the full suite in three batches; only the file-limits test failed, on the then-unfixed `docs/brainstorming.md`.
- `ruff check specy_road tests scripts`: clean.
- `python scripts/check_clones.py --pylint <pylint 4.1.3 via uvx>`: 0 new (pylint is not installed in the env).
- `python scripts/check_test_private_imports.py`: 0 new.
- `specy-road validate` (sr) and `validate` / `export --check` / `digest --check` on the dogfood fixture: OK.
- `specy-road file-limits`: OK after the merge.

## Added

### Helpers
- `integrity.integration_ratchet_paths` — reads `policy.ratchet_paths` from the integration branch so a leaf cannot drop its own baselines from the list (A2).
- `integrity._added_lines` — `path -> added lines` over the `--find-renames` entries (A1).
- `integrity._changed_files` — `(path, old blob or None, new blob)` per `git diff --raw -z` entry whose new side is a regular file or symlink; exact paths with no pathspec (R2, round 7), and a non-UTF-8 name drops only itself (round 5).
- `integrity._blob_additions` — added lines of one blob pair, or every line of the new blob when there is no regular old side (round 7).
- `integrity._patch` — a git diff decoded leniently, so a non-UTF-8 line keeps its count and markers (round 2).
- `integrity._git_bytes` — raw git stdout, never raises, empty on failure or timeout; `_patch`, `_changed_files` and `_blob_additions` use it (round 5).
- `integrity._utf8` — strict decode of one file name, `None` when it is not UTF-8 (round 5).
- `integrity._hunk_additions` — the `+` lines inside the hunks of a `-U0` blob-pair patch.
- `integrity._suppression_findings` — one `new-suppression` per added line matching a marker (A1).
- `integrity._ratchet_findings` — one `baseline-widened` per ratchet path with added lines, over the `--no-renames` entries (A2; round 3).
- `_BLOB_DIFF` flags — `--text --no-textconv --no-ext-diff`: a blob pair has no path, so no attribute applies, but NUL content and repo-config drivers still could hide lines (round 3).
- `_KIND` — modes whose lines count (`100644`/`100755` file, `120000` symlink); gitlinks and deletions are skipped (round 7; symlinks added in round 8).
- `_SUPPRESSION`, `_HUNK` regexes — the marker list (A1) and the hunk header's new-side start line.

### Branches / guards
- `Finding.line` gains the `new-suppression` and `baseline-widened` forms (A1, A2).
- `_hunk_additions` ignores each section's header (from `diff --git` to its first `@@`), so header lines are never content (round 6; with blob pairs each patch has one section, so this is a guard).
- `_git_bytes` returns `b""` when git fails, times out or cannot start, so that file adds nothing.
- `_changed_files` skips an entry whose new mode is not in `_KIND` (deletion, submodule) or whose path is not UTF-8. It treats an old side of a different kind as `None`, so a file/symlink type change counts every new line, as git's default diff does (round 8). It stops at a truncated record instead of raising (round 7).
- `_blob_additions` drops the empty string after a final newline, so `a\n` is one line.
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
- `test_file_renamed_and_its_path_reused_as_a_directory` — round 7, Sol's case 1: `old` renamed to `new.txt` and `old/child.txt` added with `# noqa`; prints only `new-suppression: old/child.txt:1`, exit 1.
- `test_deleted_baseline_reused_as_a_directory_is_not_widened` — round 7, Sol's case 2: the configured baseline deleted and its name reused as a directory; empty output, exit 0.
- `test_moved_file_keeps_its_existing_suppressions` — round 7: pins the rename-following kept for suppressions; a moved file with an existing `# noqa` gives exit 0.
- `test_added_symlink_counts_its_target_as_a_line` — round 8: an added symlink `baseline-link -> target-noqa` at a configured ratchet path prints `baseline-widened: baseline-link +1` and `new-suppression: baseline-link:1`, exit 1.
