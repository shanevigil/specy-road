# Implementation summary: M11.78 — Review lessons

## What changed

- **A1:** `init project` now writes `constraints/review-lessons.md` (new template `specy_road/templates/project/constraints/review-lessons.md`): a short header plus an empty `## Lessons` section. Each top-level bullet under `## Lessons` is one entry: a one-line rule, with optional `Example:` and `From:` sub-bullets. `role_prompt.reviewer_lines` appends `review_lessons.reviewer_lesson_lines(root)`, so every reviewer prompt (`specy-road prompt --role reviewer`, and `review delegate` / worker paths that call `build_prompt`) has a `## Project review lessons` section listing every entry. With no file or no entries the section is left out. An unreadable file is named in the prompt instead. `tests/test_review_lessons.py::test_reviewer_prompt_carries_every_lesson` pins the inclusion and failed with the hook removed (red-green below).
- **A2:** `specy-road lessons add --rule <text> [--example <text>] [--from <NODE_ID>]` appends an entry at the end of `## Lessons`. A missing file is created from the bundled header first; line breaks in the rule or example are folded into one line. `--from` records the leaf the entry came from (it must match `[A-Za-z0-9._-]+`). `specy-road lessons list` prints entries in file order. With a missing file it says the file does not exist and exits 0. Tests cover add, list, a missing file, a section that another section follows, and a bad `--from`.
- The design mirrors the decisions ledger: library `specy_road/review_lessons.py`, CLI `specy_road/bundled_scripts/lessons_cli.py`, wired through `_FORWARDED` in `specy_road/cli.py`.
- Docs: new `## Project review lessons` section in `docs/orchestration-review.md`; a row in the template `constraints/README.md` table.

## Touch zones (final)

The listed zones were accurate; nothing was added. Changed: `specy_road/review_lessons.py` (new), `specy_road/bundled_scripts/lessons_cli.py` (new), `specy_road/cli.py`, `specy_road/bundled_scripts/role_prompt.py`, `specy_road/templates/project/constraints/{review-lessons.md (new), README.md}`, `docs/orchestration-review.md`, `tests/test_review_lessons.py` (new). The prompt section's text lives in `review_lessons.py` because `role_prompt.py` was at 399 of its 400-line cap. The hook adds one import line (400 lines now).

## Verification

- `python -m pytest -q tests/test_review_lessons.py` → 6 passed.
- Related tests (decisions, lean rules, models/prompt, role-prompt file limits, init project, review delegate, stale commands, ready, rca, review files) → 158 passed.
- `ruff check` on the changed Python files → clean.
- Full `pytest -n auto` → 3536 passed, 2 skipped, 1 failed: `tests/test_validate_file_limits.py::test_file_limits_passes_on_repo`. Both that test and `specy-road file-limits` (exit 1) fail on `specy_road/bundled_scripts/worker_cli.py: 401 lines (max 400 per file)`. That file is outside this leaf's zones, unchanged here, and already 401 lines at base `d8eccac8`, so this is pre-existing. None of the files this leaf changed is over a cap.
- Not done: `suggested_prompts/` was not updated, because none of them describe the `constraints/` layout this adds to.

## Added

- `specy_road/review_lessons.py` — the lessons file's path, parsing, appending and the reviewer prompt section, kept out of `role_prompt.py` because of its line cap.
- `review_lessons.parse_lessons` / `read_lessons` — read entries under `## Lessons` only, so the header's prose is never an entry. A missing file reads as no entries; a non-UTF-8 file raises `OSError`.
- `review_lessons._insert_entry` — puts a new entry at the end of `## Lessons` (or adds that heading), so a hand-added section after it does not capture the entry.
- `review_lessons._one_line` guard — refuses an empty rule or example and folds line breaks, because each entry must be one line.
- `--from` node-id guard (`_NODE_ID`) — refuses whitespace and other non-id text so `From:` stays parseable.
- `review_lessons.reviewer_lesson_lines` unreadable-file branch — names the file in the prompt rather than silently dropping the lessons.
- `bundled_scripts/lessons_cli.py` — `lessons add|list` argparse, mirroring `decisions_cli.py`.
- `specy_road/cli.py` `_FORWARDED["lessons"]` — registers the command.
- Template `constraints/review-lessons.md` — the header `init project` writes and `lessons add` starts a missing file from.
- `tests/test_review_lessons.py` — six tests: init header, add + list, missing file, insertion before a following section, bad `--from`, reviewer prompt inclusion. No mocks.
