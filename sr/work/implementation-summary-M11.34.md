# Implementation summary: M11.34 — decision-ledger

## What changed

- **`roadmap/decisions.yaml`** is the tracked ledger for open human decisions, validated against `schemas/decisions.schema.json` (bundled under `specy_road/templates/project/schemas/` and copied on `init project` / `refresh-schemas`).
- **`specy-road decisions add|list|close`** implements A1: self-contained fields on add, list ordered by `needed_by` (no deadline last), close only after the same answer appears on the node planning sheet as `{id}: {answer}`.
- **Coordinator discipline (A2):** `specyrd-orchestrate.md`, `coordinator_decision_lines()` in `decisions.py` (included from `role_prompt.py` for coordinator prompts), and a new **Human decisions ledger** section in `docs/orchestration.md`.
- **Tests (A3):** `tests/test_decisions.py` covers add, list ordering, close vs sheet, schema rejection, and coordinator prompt text.

## Touch zones (confirmed)

Final list matches the brief: `specy_road/decisions.py`, `specy_road/bundled_scripts/decisions_cli.py`, `specy_road/cli.py`, `specy_road/templates/project/schemas/`, `specy_road/templates/specyrd/commands/specyrd-orchestrate.md`, `specy_road/bundled_scripts/role_prompt.py`, `docs/orchestration.md`, `tests/`. No additions or removals.

## Verification

- `pytest tests/test_decisions.py -q`
- `specy-road file-limits`

## Added

- `specy_road/decisions.py` — ledger read/write, schema validation, sort/list formatting, add/close, `coordinator_decision_lines()` — core behaviour and coordinator prompt block.
- `specy_road/bundled_scripts/decisions_cli.py` — `add|list|close` argparse entrypoints — CLI surface for A1.
- `specy_road/templates/project/schemas/decisions.schema.json` — JSON Schema for ledger documents — A1/A3 validation contract.
- `tests/test_decisions.py` — five behavioural tests through CLI and `build_prompt` — A3 coverage.
- `specy_road/cli.py` — `_FORWARDED["decisions"]` — wires subcommand to bundled script.
- `specy_road/bundled_scripts/role_prompt.py` — append `coordinator_decision_lines()` after coordinator preamble — A2 coordinator prompt.
- `specy_road/templates/specyrd/commands/specyrd-orchestrate.md` — turn-start `decisions list` and question discipline — A2 orchestrate skill.
- `docs/orchestration.md` — ledger field table and turn discipline — A3 documentation.
- none — helpers/branches/guards/mocks beyond the above.
