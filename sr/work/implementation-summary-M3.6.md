## Summary

Leaf `M3.6` closes the rc1 triage gaps: batch `accept`/`reject`/`park` run `set_status` on every id before printing or writing (missing *and* already-promoted ids print nothing); `realize` records `promoted_node_key` for hand-built nodes; `revise --append-why` extends `verdict_why`; `list --summary` prints status and recommendation counts; `--reason` help and argparse rules match across accept (optional), reject, and park (required).

Review round 2: A1 failed because `validate_idea_ids` only called `by_id`, so a promoted id in a batch printed `[ok]` for earlier ids. `_triage` and `cmd_park` now collect `set_status` first; that helper already refuses a promoted idea. `validate_idea_ids` was then unused and removed.

## Touch zones (confirmed)

- `specy_road/bundled_scripts/brainstorm_cli.py` — `_triage` all-or-nothing via `set_status`; `list --summary`; `revise --append-why`
- `specy_road/bundled_scripts/brainstorm_cli_args.py` — `--summary`, separate accept/reject/realize/revise flags and help
- `specy_road/bundled_scripts/brainstorm_cli_v2.py` — `print_idea_summary`, `cmd_realize`, park all-or-nothing via `set_status`
- `specy_road/bundled_scripts/brainstorm_cli_args_v2.py` — park `--reason` help
- `specy_road/bundled_scripts/brainstorm_session.py` — unchanged (no net edit after refactors)
- `docs/brainstorming.md` — triage section
- `tests/test_brainstorm_triage_m36.py`, `tests/test_brainstorm_cli.py`, `tests/test_brainstorm_v2.py`

Outside original touch zones, at the coordinator's request: `sr/planning/M3.6_brainstorm-triage-cli_acbadda9-3756-4e55-aad3-e7153ad5be97.md` (`## Approach` filled to match the A1 `set_status` pre-check).

## Acceptance

| Criterion | How verified |
|-----------|----------------|
| A1 | `test_triage_checks_every_id_before_printing_or_saving`; `test_triage_prints_nothing_when_a_batch_holds_a_promoted_idea` |
| A2 | `test_realize_records_a_hand_built_node` |
| A3 | `test_revise_append_why_adds_to_verdict_why`; `--why` help names `verdict_why` |
| A4 | `test_list_summary_prints_status_and_recommendation_counts` |
| A5 | argparse: reject/park `--reason` required; accept optional; help strings in `brainstorm_cli_args*.py` |

## Verification

```bash
pytest tests/test_brainstorm_triage_m36.py tests/test_brainstorm_cli.py tests/test_brainstorm_v2.py -q
specy-road file-limits
```

`file-limits` still fails on `specy_road/bundled_scripts/role_prompt.py` (407 lines). That file is outside this leaf and was over the cap at base `7a8507c`.

## Added

- `_triage` `set_status` list-comprehension first — refuse missing and promoted ids before any `[ok]` (A1 review round 2)
- `cmd_park` same pre-check — A1 for park
- `print_idea_summary` in `brainstorm_cli_v2.py` — `list --summary` output (A4)
- `cmd_realize` in `brainstorm_cli_v2.py` — link idea to merged-graph node by display id (A2)
- `--append-why` branch in `cmd_revise` — append to `verdict_why` (A3)
- `tests/test_brainstorm_triage_m36.py` — M3.6 acceptance tests through the CLI entry
- `test_triage_checks_every_id_before_printing_or_saving` — A1 stdout/session unchanged on missing id
- `test_triage_prints_nothing_when_a_batch_holds_a_promoted_idea` — A1 stdout/session unchanged when a later id is already realized
- `test_realize_records_a_hand_built_node` — A2 promoted_node_key + duplicate guard
- `test_revise_append_why_adds_to_verdict_why` — A3 newline join
- `test_list_summary_prints_status_and_recommendation_counts` — A4 counts

### Removed

- `validate_idea_ids` — existence-only pre-check; `set_status` already raises on missing and promoted ids
