# Implementation summary: M3.7 (`promote-node-quality`)

## Goal

Promoted brainstorm nodes land with a `goal`, a short collision-safe `codename`, stable sibling order, one validate pass per promote batch, and a single stderr list of nodes still needing acceptance or touch zones.

## Touch zones (confirmed)

Registered zones covered promote, argparse, `title_to_codename`, docs, and tests. The skip-validate flag had to live on the existing add-node write, so this leaf also touched:

- `specy_road/bundled_scripts/roadmap_crud_ops.py` — `append_node_to_chunk(..., validate=False)`
- `specy_road/bundled_scripts/roadmap_chunk_router.py` — `write_with_routing(..., validate=False)`
- `specy_road/bundled_scripts/roadmap_crud_prepare.py` — `max_words` through collision-suffix derivation
- `specy_road/bundled_scripts/brainstorm_session.py` — persist `codename` on ideas
- `specy_road/bundled_scripts/brainstorm_fields.py` — YAML load/save for idea `codename`
- `specy_road/bundled_scripts/brainstorm_cli.py` — apply `revise --codename`
- `sr/planning/M3.7_promote-node-quality_f3e2008b-1cb2-4f0f-92c3-05864482d958.md` — Approach filled after review

## Behaviour

- **A1:** each node is `append_node_to_chunk(..., validate=False)`; `run_validate_raise` once after the batch so pin/schema warnings print once.
- **A2:** `derive_codename_with_collision_suffix(..., max_words=4)` calls `title_to_codename` (punctuation-only tokens do not count toward the cap); `append_node_to_chunk(..., max_words=4)` so the add-node heal cannot uncap; `revise --codename` on the idea wins.
- **A3:** `goal` from `idea.hypothesis`; every CLI `accept` (including without `--reason`) records `decision.seq`; promote sorts by seq then timestamp; `sibling_order` from `next_sibling_order` so later batches append.
- **A4:** `_report_promoted_missing_fields` prints one stderr line listing node ids missing `acceptance` or `touch_zones`.

## Verification

```bash
pytest tests/test_brainstorm_promote.py tests/test_brainstorm_promote_m37.py tests/test_roadmap_edit_fields.py tests/test_roadmap_chunk_router.py tests/test_roadmap_crud_atomicity.py tests/test_roadmap_crud.py tests/test_brainstorm_cli.py tests/test_brainstorm_v2.py tests/test_gui_app_brainstorm.py -q
specy-road file-limits
```

`specy-road file-limits` is re-run after the WIP merge (M3.18 split `role_prompt.py`). This leaf's files stay under cap.

## Added

- `write_with_routing(..., validate=)` / `append_node_to_chunk(..., validate=)` — skip per-node validate so a batch can check once.
- `_promote_execution_milestone` — keep `promote_session` under the 80-line cap.
- `derive_codename_with_collision_suffix(..., max_words=)` — pass the promote word cap into `title_to_codename`.
- `Idea.codename` + fields parse — store PM-chosen slug on the session idea.
- `revise --codename` argparse + CLI apply — PM override before promote.
- `_next_decision_seq` — allocate a session-wide accept/reject/park sequence.
- `_accept_order_key` — sort pending ideas by that sequence, then timestamp, then id.
- `_promote_codename` — honor idea `codename` or derive with word cap and collision suffix.
- `_report_promoted_missing_fields` — one stderr list after a successful batch promote.
- `title_to_codename(..., max_words=)` — cap counts only tokens that contribute slug fragments.
- `append_node_to_chunk` / `ensure_codename_for_new_node(..., max_words=)` — keep the promote cap on the add-node heal path.
- `test_promote_caps_codename_when_the_title_starts_with_punctuation` — public write-path four-word cap after punctuation.
- `test_title_to_codename_skips_punctuation_tokens_when_capping` — helper-level skip of empty tokens.
- `test_promote_prints_pin_warnings_once_for_a_multi_node_batch` — public A1 (pin warning once, no mock count).
- `test_write_with_routing_skip_validate_still_writes` — skip-validate writes even when validate would raise.
- `test_cli_accept_without_reason_preserves_accept_order` — public CLI accept order without `--reason`.
- `test_successive_promote_appends_after_existing_siblings` — later promote calls append sibling_order.
- `tests/test_brainstorm_promote_m37.py` — A2–A4 through `promote_session`.
- `test_title_to_codename_honors_max_words` — word-cap unit test on `title_to_codename`.
- none — mocks in the A1 test (pin is a real `requirements.txt` on a nested git copy).
