# Implementation summary — M4.14

## Goal

Promoted brainstorm nodes inherit the anchor’s `execution_milestone` unless the PM overrides it with `brainstorm promote --set execution_milestone=…`.

## Touch zones (confirmed)

Roadmap touch zones name `specy_road/brainstorm_promote.py` and `specy_road/brainstorm_cli.py`; in this repo those modules live under `specy_road/bundled_scripts/`. Effective edits:

- `specy_road/bundled_scripts/brainstorm_promote.py`
- `specy_road/bundled_scripts/brainstorm_cli.py`
- `specy_road/bundled_scripts/brainstorm_cli_args.py` (promote argparse; required for `--set`)
- `docs/brainstorming.md`
- `tests/test_brainstorm_promote.py`
- `sr/planning/M4.14_brainstorm-promote-inherits-execution-milestone-from-the-anchor_9ea6aab2-3241-428e-81a7-fc329d4ae8ba.md` (Approach filled after review)

## Behaviour

- `promote_session` resolves `execution_milestone` from the already-validated anchor parent (`--under` or session anchor) when not overridden. Missing parents stay `_assert_parent`'s error; lookup has no missing-anchor fallback.
- `INHERIT_EXECUTION_MILESTONE` sentinel keeps the default “inherit” distinct from an explicit override (including clearing via `--set execution_milestone=`).
- CLI `promote --set KEY=VALUE` accepts only `execution_milestone`; values must match `EXEC_MILESTONES`.

## Verification

```bash
pytest tests/test_brainstorm_promote.py -q
```

Exit 0; 19 passed.

## Added

- `_anchor_execution_milestone` — reads the already-validated anchor’s advisory execution type; root returns None, unset/non-enum field is omitted (`next` lookup, no missing-anchor fallback — E1).
- `INHERIT_EXECUTION_MILESTONE` — sentinel default for `promote_session` so `None` can mean an explicit clear override.
- `execution_milestone_from_promote_sets` — parses `promote --set` pairs for CLI and GUI callers.
- Promote `--set` argparse on `brainstorm promote` — exposes `execution_milestone` override at the CLI.
- `test_promoted_nodes_inherit_the_anchor_execution_milestone` — Agentic-led anchor (M1) copied without `--set`.
- `test_promoted_nodes_inherit_human_led_from_the_anchor` — Human-led anchor (M0) copied without `--set`.
- `test_promoted_nodes_accept_execution_milestone_override` — `--set`/kwarg override to Human-led under an agentic anchor.
- `test_promoted_nodes_omit_execution_milestone_when_the_anchor_has_none` — M0.3 has no execution_milestone; the leaf omits the field (E1 optional-field handling).
- Extended `test_promoting_to_the_root_makes_a_top_level_node` — root promotion also omits execution_milestone (E1 root handling).
