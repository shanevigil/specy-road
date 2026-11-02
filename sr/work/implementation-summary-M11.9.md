# Implementation summary: M11.9 — human acceptance items

## What changed

- **Marker (A1):** an acceptance criterion whose text starts with `human:` is one only a person can satisfy. No schema shape change: the `acceptance` item stays a string; the description in `specy_road/templates/project/schemas/roadmap.schema.json` and the identical `sr/schemas/roadmap.schema.json` documents the prefix. A `schemas/` directory does not exist at the git root (touch zone listed it; nothing to change).
- **Reviewer handling (A1):** `reviewer_preamble` in `specy_road/bundled_scripts/role_prompt_rca.py` tells reviewers to mark a `human:` item `n/a`, write `human` as its reason in their notes, and never fail or block on it. The review gate already treats `n/a` as not-a-fail (`review_semantic_errors` fails an approve only on `fail`), so no gate change was needed; `tests/test_review_files.py` already covers it.
- **Finish refusal (A2):** new `specy_road/finish_task_gates.py` (the touch-zone module name; no module of that name existed). `human_acceptance_or_exit` runs in `finish_task._resolve_main_context` right after the scaffold-sheet check and before the review gate. It refuses with exit 1 while any `human:` item has no recorded decision on the planning sheet, naming the ids, the sheet, and the exact line form to add: `- A#: <decision, who and when>` in any section, committed on the branch. A decision is any sheet line matching `A#: <text>` with an optional list marker or checkbox in front. A missing sheet leaves every human item undecided (validate owns the missing-sheet finding).
- **Docs (A3):** `docs/roadmap-authoring.md` acceptance row documents the marker, the reviewer `n/a`, and how to record the decision.

## Touch zones (final)

As listed, minus `schemas/` (absent at the git root). All edits inside the zones.

## Verification

- `specy-road file-limits` = 0
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood` = 0
- `python -m pytest -q -x -p no:cacheprovider` = 0 (3001 passed, 2 skipped)

## Added

### Helpers
- `finish_task_gates.is_human_item` — the `human:` prefix test, case-insensitive after strip.
- `finish_task_gates.human_acceptance_ids` — A# ids of a node's human items, numbered like `brief_acceptance.acceptance_ids`.
- `finish_task_gates.recorded_decisions` — parses `A#: <text>` lines from a sheet.
- `finish_task_gates.undecided_human_items` — human ids with no decision line on the sheet.
- `finish_task_gates.human_acceptance_or_exit` — the finish refusal with the recording instructions.

### Branches or guards
- `finish_task._resolve_main_context` calls `human_acceptance_or_exit` after the scaffold check (A2).
- `undecided_human_items` treats an unreadable or unresolvable sheet as empty text (OSError/ValueError), same classes `planning_scaffold_check.scaffold_sheet` catches.
- `reviewer_preamble` sentence on `human:` items (A1).

### Mocks
- none

### Tests (`tests/test_human_acceptance.py`)
- `test_marker_and_decision_lines` — id extraction and decision-line parsing including checkbox and bare forms.
- `test_reviewer_is_told_to_skip_a_human_item` — preamble wording (A1, reviewer skip). The approve-plus-`n/a` semantics are already covered by `tests/test_review_files.py::test_valid_ready_and_review_parse`, so the earlier duplicate assertion was removed on Sol's review.
- `test_finish_refuses_until_the_sheet_records_the_decision` — finish exits 1 with the recording instructions and no commit; after the decision line is committed it proceeds to the next gate (A2, A3).
