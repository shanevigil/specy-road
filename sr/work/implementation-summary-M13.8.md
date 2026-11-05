# Implementation summary: M13.8

## Touch zones

`specy_road/behaviour_changes.py`, `specy_road/agent_text_report.py`, `specy_road/version_pin.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `tests/`, `docs/roadmap-authoring.md`.

## Fix round: mandate cue (planner A2 clarification)

A line is reported only when it **instructs** stale behaviour: each catalogue `contradicts` pattern includes shared `_MANDATE_CUE` (must/always/approve/when tests pass/never pass|run|delete/push/non-TTY/unattended/prescriptive first-commit steps) plus command anchor (except `--base` optional anchor). Bare command examples without mandating words are valid usage and stay silent.

## Fix round: probes

- CITED five-sentence fixture — five notices, unchanged.
- `BARE_VALID_USAGE` (planner bare merge/yes lines plus prior minimum pairings) — no notices.
- `test_explicitly_stale_instructions_are_reported_despite_guidance_vocabulary` — three notices (Always/Approve/after branching).
- Zero-notice corpus — no hits.
- Near-miss corpus — no notices.
- Sol integration-branch-first near-miss — no notice.

## Verification

- `python -m pytest -n 4 -q $(rg -l '…behaviour_changes|agent_text_report|version_pin|validate_roadmap…' tests)` — 286 passed
- `python -m pytest -n 4 -q tests/test_behaviour_changes.py` — 39 passed
- `specy-road file-limits` — OK

## Added

### Helpers
- `behaviour_changes._MANDATE_CUE` — shared instructive-language regex combined into every entry's `contradicts` via `_all_of`.

### Branches and guards
- All five catalogue entries: stale match requires mandate cue in the same sentence (mandate round).

### Mocks
- none

### Tests
- `test_bare_valid_command_examples_print_no_notice` — parametrized bare valid usage (mandate round).
- `test_mandated_stale_instruction_with_bare_command_name_prints_a_notice` — bare command token still reports when `must` mandates (R3 + mandate).
