# Implementation summary: M11.34 — decision-ledger

## What changed

- **`roadmap/decisions.yaml`** is the tracked ledger for open human decisions, validated against `schemas/decisions.schema.json` (bundled under `specy_road/templates/project/schemas/` and copied on `init project` / `refresh-schemas`).
- **`specy-road decisions add|list|close`** implements A1: self-contained fields on add, list ordered by `needed_by` (no deadline last), close only after the same answer appears in the node's planning-sheet **decision block**.
- **Coordinator discipline (A2):** `specyrd-orchestrate.md`, `coordinator_decision_lines()` in `decisions.py` (included from `role_prompt.py` for coordinator prompts), and a **Human decisions ledger** section in `docs/orchestration.md`.
- **Tests (A3):** `tests/test_decisions.py` covers add, list ordering, close vs decision-block, date/schema rejection, coordinator/skill text, and the documented `search --kind planning` command. Tests drive the public CLI (`decisions_cli.main` / `search_cli.main`), not patched internals.

Merged `origin/WIP/improvements-0-3-1` into this branch before the review fixes (`23b4ce39`). Roadmap JSON was not edited for RCA-3.

## RCA-3 (round 3 R1, in_scope_must_fix)

| Item | Change | Commit | Test |
|---|---|---|---|
| **R1** | Strip CommonMark fences from the **whole** planning sheet, then select the first level-2 section whose heading normalises to `decisions and notes` or `decisions`. A heading that exists only inside a fence is not the decision block. | `0109ad49` | `test_close_requires_decision_block_record` (extended: ` ```markdown ` fence whose body is `## Decisions and notes` plus `D1: blue` — close fails, entry stays open) |

## Review required changes (gpt-6.1-sol, second block)

| Item | Change | Commit | Test |
|---|---|---|---|
| **R1** | Close skips every CommonMark fenced example (backtick and tilde, matching fence lengths) by reusing `_fence_marker` / `_fence_closes` / `_opening_is_code_span` from `validate_stale_commands`. | `a9314c04` | `test_close_requires_decision_block_record` (extended: `~~~text` fence and a 4-backtick fence that a 3-backtick line does not close) |
| **R2** | Ledger schema validation uses `Draft202012Validator.FORMAT_CHECKER` so `format: date` rejects calendar-impossible values, not only regex/add parsing. | `a9314c04` | `test_list_rejects_malformed_asked_in_ledger` (extended: quoted `"2026-02-30"`) |

## Review required changes (gpt-6.1-sol, first block)

| Item | Change | Commit | Test |
|---|---|---|---|
| **R1** | Close verifies `id: answer` only inside `## Decisions and notes` (or `## Decisions`), skipping other sections and fenced examples. Reuses `find_section`. | `0ceeeeec` | `test_close_requires_decision_block_record` (Intent-only and fenced answers must fail; a decision-block line closes) |
| **R2** | `asked` / `needed_by` are ISO `YYYY-MM-DD` in the schema (`format` + `pattern`) and at add (`require_iso_date`) before write. CLI prints the error. | `0ceeeeec` | `test_add_rejects_malformed_dates` (CLI `--asked not-a-date`, `--needed-by tomorrow-ish`); `test_list_rejects_malformed_asked_in_ledger` (schema via `decisions list`) |
| **R3** | Both instruction surfaces use `specy-road search "<topic>" --kind planning`. | `0ceeeeec` | `test_coordinator_prompt_and_skill_name_kind_and_shape`; `test_documented_search_kind_planning` (public search CLI, exit 0) |
| **R4** | Orchestrate skill enumerates the self-contained fields: summary, why now and blockers, options and effects, recommendation and reason, default if unanswered, optional needed-by deadline. | `0ceeeeec` | `test_coordinator_prompt_and_skill_name_kind_and_shape` |

## Touch zones (confirmed)

Final list matches the brief: `specy_road/decisions.py`, `specy_road/bundled_scripts/decisions_cli.py`, `specy_road/cli.py`, `specy_road/templates/project/schemas/`, `specy_road/templates/specyrd/commands/specyrd-orchestrate.md`, `specy_road/bundled_scripts/role_prompt.py`, `docs/orchestration.md`, `tests/`. No additions. This fix did not need a further `cli.py` / `role_prompt.py` edit (`role_prompt.py` still appends `coordinator_decision_lines()`).

## Verification

- `pytest tests/test_decisions.py -q` (10 passed)
- `specy-road file-limits`

## Added

- `recorded_on_sheet` strips fences on the whole sheet before `find_section` — a fenced `## Decisions and notes` is not the decision block (RCA-3 R1).
- `Draft202012Validator.FORMAT_CHECKER` on the ledger validator — calendar-valid `format: date` at schema time (second R2).
- `_unfenced_lines` now reuses `_fence_marker` / `_fence_closes` / `_opening_is_code_span` — CommonMark backtick and tilde fences (second R1).
- `require_iso_date` — boundary check so malformed `asked`/`needed_by` never write (first R2).
- `cmd_add` `ValueError` guard — CLI prints date/schema errors instead of traceback (first R2).
- `_DECISION_HEADINGS` — match `## Decisions and notes` / `## Decisions` (first R1).
- `test_close_requires_decision_block_record` — public CLI close vs Intent / backtick / tilde / unmatched-length fence / block (R1).
- `test_add_rejects_malformed_dates` — public CLI add with invalid dates (first R2).
- `test_list_rejects_malformed_asked_in_ledger` — public CLI list schema-rejects `not-a-date` and quoted `"2026-02-30"` (R2).
- `test_coordinator_prompt_and_skill_name_kind_and_shape` — both instruction surfaces (R3, R4).
- `test_documented_search_kind_planning` — documented `--kind planning` command (R3).
- none — mocks.
