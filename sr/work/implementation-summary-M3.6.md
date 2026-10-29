## Summary

Leaf `M3.6` closes the rc1 triage gaps: batch `accept`/`reject`/`park` validate every idea id before printing or writing; `realize` records `promoted_node_key` for hand-built nodes; `revise --append-why` extends `verdict_why`; `list --summary` prints status and recommendation counts; `--reason` help and argparse rules match across accept (optional), reject, and park (required).

## Touch zones (confirmed)

- `specy_road/bundled_scripts/brainstorm_cli.py` — `_triage` all-or-nothing; `list --summary`; `revise --append-why`
- `specy_road/bundled_scripts/brainstorm_cli_args.py` — `--summary`, separate accept/reject/realize/revise flags and help
- `specy_road/bundled_scripts/brainstorm_cli_v2.py` — `validate_idea_ids`, `print_idea_summary`, `cmd_realize`, park validation
- `specy_road/bundled_scripts/brainstorm_cli_args_v2.py` — park `--reason` help
- `specy_road/bundled_scripts/brainstorm_session.py` — unchanged (no net edit after refactors)
- `docs/brainstorming.md` — triage section
- `tests/test_brainstorm_triage_m36.py`, `tests/test_brainstorm_cli.py`, `tests/test_brainstorm_v2.py`

## Acceptance

| Criterion | How verified |
|-----------|----------------|
| A1 | `test_triage_checks_every_id_before_printing_or_saving` |
| A2 | `test_realize_records_a_hand_built_node` |
| A3 | `test_revise_append_why_adds_to_verdict_why`; `--why` help names `verdict_why` |
| A4 | `test_list_summary_prints_status_and_recommendation_counts` |
| A5 | argparse: reject/park `--reason` required; accept optional; help strings in `brainstorm_cli_args*.py` |

## Verification

```bash
pytest tests/test_brainstorm_triage_m36.py tests/test_brainstorm_cli.py tests/test_brainstorm_v2.py -q
specy-road file-limits
```

## Added

- `validate_idea_ids` in `brainstorm_cli_v2.py` — resolve all ids before triage mutates (A1)
- `print_idea_summary` in `brainstorm_cli_v2.py` — `list --summary` output (A4)
- `cmd_realize` in `brainstorm_cli_v2.py` — link idea to merged-graph node by display id (A2)
- `validate_idea_ids` call in `_triage` — all-or-nothing accept/reject (A1)
- `validate_idea_ids` call in `cmd_park` — all-or-nothing park (A1)
- `--append-why` branch in `cmd_revise` — append to `verdict_why` (A3)
- `tests/test_brainstorm_triage_m36.py` — M3.6 acceptance tests through the CLI entry
- `test_triage_checks_every_id_before_printing_or_saving` — A1 stdout/session unchanged on bad id
- `test_realize_records_a_hand_built_node` — A2 promoted_node_key + duplicate guard
- `test_revise_append_why_adds_to_verdict_why` — A3 newline join
- `test_list_summary_prints_status_and_recommendation_counts` — A4 counts
