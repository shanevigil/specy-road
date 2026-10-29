# Implementation summary: M3.7 (`promote-node-quality`)

## Goal

Promoted brainstorm nodes land with a `goal`, a short collision-safe `codename`, stable sibling order, one validate pass per promote batch, and a single stderr list of nodes still needing acceptance or touch zones.

## Touch zones (confirmed)

Registered zones were accurate for the core promote and codename work. Acceptance also required:

- `specy_road/bundled_scripts/brainstorm_session.py` — persist `codename` on ideas
- `specy_road/bundled_scripts/brainstorm_fields.py` — YAML load/save for idea `codename`
- `specy_road/bundled_scripts/brainstorm_cli.py` — apply `revise --codename`

## Behaviour

- **A1:** `_write_promoted_node(..., validate=False)` per node; `run_validate_raise` once after the batch.
- **A2:** `title_to_codename(..., max_words=4)` for derivation; `revise --codename` on the idea wins; collision suffix unchanged via `derive_codename_with_collision_suffix`.
- **A3:** `goal` from `idea.hypothesis`; pending ideas sorted by `decision.decided_at` / `decided_date`; `sibling_order` 1..N in that order.
- **A4:** `_report_promoted_missing_fields` prints one stderr line listing node ids missing `acceptance` or `touch_zones`.

## Verification

```bash
pytest tests/test_brainstorm_promote.py tests/test_brainstorm_promote_m37.py tests/test_roadmap_edit_fields.py
```

## Added

- `_accept_order_key` — sort pending ideas by triage decision time, then id.
- `_title_for_promote_codename` — cap title words before slug derivation for promote.
- `_promote_codename` — honor idea `codename` or derive with word cap and collision suffix.
- `_write_promoted_node` — chunk write matching add-node routing without per-node validate.
- `_report_promoted_missing_fields` — one stderr list after a successful batch promote.
- `title_to_codename(..., max_words=)` — optional word cap in shared slug helper.
- `Idea.codename` + fields parse — store PM-chosen slug on the session idea.
- `revise --codename` argparse + CLI apply — PM override before promote.
- `tests/test_brainstorm_promote_m37.py` — acceptance coverage for A1–A4.
- `test_title_to_codename_honors_max_words` — word-cap unit test on `title_to_codename`.
- none — mocks (tests use real dogfood fixture and public promote API).
