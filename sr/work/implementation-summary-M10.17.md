# Implementation summary: `M10.17` (packet-byte-budget)

## What changed

- `specy_road/bundled_scripts/review_packet.py`
  - **A1:** `--max-diff-bytes N` (default `MAX_DIFF_BYTES = 200_000`, `0` = no byte cap) works alongside
    `--max-diff-lines`. The packet switches to the capped form when the diff passes either budget. Files are
    inlined whole, in diff order, until one would pass either budget. That file and every later one are listed
    as ``- `path` (+a -r) — not inlined (N bytes of diff)``. The full diff still goes to `DIFF.patch`. The cap
    line reads `**Diff capped at L lines** and **B bytes** (… lines, … bytes in all)`. The M10.7
    `**Diff capped at L lines**` prefix is kept, so existing readers and tests still match.
  - **A2:** generated files are never inlined, whatever the budgets. A file is generated when its git-root
    path is under `GENERATED_PATHS` (`specy_road/pm_gantt_static/`) or when `git check-attr
    --source=<commit> linguist-generated` says `set`/`true`. Attributes are read at the commit under review.
    If git lacks `--source`, the working tree's attributes are used instead. These files are listed with
    `, generated` and their counts and size. The packet adds `GENERATED_NOTE`, and the diff is in
    `DIFF.patch`. A diff with a generated file always takes the capped form, even with both budgets at `0`
    (the header is then `**Diff not inlined in full**`).
  - `_numstat` now uses `--numstat -z`, so each row carries a rename's new path (needed for the generated
    check) and not git's `{a => b}` display form. If numstat and the diff disagree on file count, the
    fallback now names each file by its `b/` path, not the raw `a/X b/X` header.
  - Module docstring and `--max-diff-lines` help updated: `0` now means "no line cap". `DIFF.patch` is still
    written when a generated file or the byte budget forces the capped form.
  - 398 lines (cap 400). No helper module was needed, so the touch zones are unchanged.
- `docs/orchestration-review.md`: new **The diff in the review packet** section documents both budgets and
  the generated-file rule.
- `tests/test_review_packet.py`: five tests (below).

Behaviour preserved: a diff within both budgets with no generated file is inlined byte-for-byte as before.
`test_a_packet_under_the_cap_is_byte_identical_to_an_uncapped_one` still passes. All M10.7 tests are
unchanged and pass.

## Touch zones

Confirmed accurate: `specy_road/bundled_scripts/review_packet.py`, `docs/orchestration-review.md`, `tests/`.
Nothing outside them was edited.

## Verification

- `pytest tests/test_review_packet.py`: 22 passed
- `pytest` (full suite): 2861 passed, 2 skipped (exit 0)
- `specy-road file-limits`: OK
- `ruff check specy_road tests scripts`: all checks passed
- `scripts/check_clones.py` (pylint 4.1.3): 0 new. `scripts/check_test_private_imports.py`: 0 new. Each
  also prints one stale-baseline line that was already there before this branch.

## Added

### Helpers / constants
- `MAX_DIFF_BYTES`: the default byte budget (A1).
- `GENERATED_PATHS`: default generated-artefact prefixes, git-root relative: the packaged PM GUI bundle (A2).
- `GENERATED_NOTE`: the packet line saying generated files are never inlined (A2).
- `_generated(root, commit, paths)`: the generated set from the prefixes plus `linguist-generated` at the
  reviewed commit (A2).
- `_budget(cap, max_bytes)`: renders the cap headline for whichever budgets are on, keeping M10.7's wording.

### Branches / guards
- `_diff`: takes the capped path when there is a generated file or the byte budget is passed, as well as
  the old line check (A1, A2).
- `_capped_diff`: a `full` flag lists every file after the first one past either budget (M10.7's prefix
  semantics), and generated files are skipped without stopping the prefix (A1, A2).
- `_numstat`: a rename/copy record (empty path field under `-z`) reads the new path from the next fields.
- `_capped_diff` fallback: names files from their `b/` header path when numstat and diff disagree on count.
- `_generated`: falls back to working-tree attributes when `check-attr --source` fails (git < 2.40).

### CLI
- `--max-diff-bytes N`, passed through `build_packet(max_diff_bytes=…)` (A1).

### Mocks
- none

### Tests (`tests/test_review_packet.py`)
- `test_a_few_long_minified_lines_past_the_byte_budget_are_listed_with_their_size`: three 100 KB lines
  stay under the line cap but pass the default byte budget. The file is listed with its exact diff bytes,
  earlier files are inlined, and `DIFF.patch` holds the full line (A1, A3).
- `test_max_diff_bytes_zero_lifts_the_byte_cap`: `0` inlines a 300 KB line and writes no `DIFF.patch` (A1).
- `test_a_generated_bundle_is_listed_as_generated_and_never_inlined`: a file under `GENERATED_PATHS` is
  listed as generated even with both budgets `0`, and `DIFF.patch` holds it (A2, A3).
- `test_a_linguist_generated_path_at_the_reviewed_commit_is_never_inlined`: `.gitattributes`
  `linguist-generated` is honoured from the reviewed commit even after the working-tree copy is deleted (A2).
- `test_main_passes_max_diff_bytes_through`: CLI wiring of `--max-diff-bytes` (A1).
