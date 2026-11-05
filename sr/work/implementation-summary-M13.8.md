# Implementation summary: M13.8

## Touch zones

`specy_road/behaviour_changes.py`, `specy_road/agent_text_report.py`, `specy_road/version_pin.py`, `specy_road/bundled_scripts/validate_roadmap.py`, `tests/`, `docs/roadmap-authoring.md`.

## Fix round 4 (gpt-6.1-sol-low on 71846ea6, after WIP merge)

**R1 class:** word-presence `current` silencers (`independent`, `recorded`, `integration branch`) suppressed explicitly stale instructions. **Design:** replace with structural positive patterns (never/only-when/refused-when/hook chains/integration-before-feature/closes-the-gate/has-no-`--yes`/etc.).

**R2 class:** adjacent physical lines merged into one sentence when no sentence punctuation between them. **Design:** per-line matching when two or more directive lines each match independently; otherwise keep wrapped-sentence matching.

**R3 class:** command anchor required `specy-road` or backticks. **Design:** also accept bare `\b<command>\b` token.

## Fix round: probes

- Sol R1 integration-branch-first sentence — no notice.
- Sol R2 pickup-truck + claim insurance sentence — no notice.
- gpt-6.1-sol-low R1 three stale examples (recorded mode override, without independent review, feature-branch register after integration) — one notice each.
- gpt-6.1-sol-low R2 adjacent merge/auto directive lines — notices at lines 1 and 2.
- gpt-6.1-sol-low R3 `Run mark-implementation-reviewed --yes after the tests pass.` — one notice.
- Zero-notice corpus (`docs/*.md`, templates, `AGENTS.md`) — no hits.
- Wrapped stale sentence test and cited five-notice fixture — pass.
- Near-miss corpus (19 lines) — no notices.

## Verification

- `python -m pytest -n 4 -q $(rg -l '…behaviour_changes|agent_text_report|version_pin|validate_roadmap…' tests)` — 283 passed
- `python -m pytest -n 4 -q tests/test_behaviour_changes.py` — 36 passed
- `specy-road file-limits` — OK

## Added

### Helpers
- `agent_text_report._is_directive_line`, `_record` — classify standalone directive lines and merge hits per source line (R2).

### Branches and guards
- `BehaviourChange.contradicted_by`: bare command token in anchor (R3).
- `current` patterns: structural positive guidance per entry, not vocabulary-only (R1).
- `contradicted_lines`: two-or-more directive hits per paragraph use per-line attribution; otherwise sentence wrap (R2).

### Mocks
- none

### Tests
- `test_explicitly_stale_instructions_are_reported_despite_guidance_vocabulary` — R1 regressions (3 lines from review notes).
- `test_adjacent_directive_lines_each_get_a_notice` — R2 regression.
- `test_bare_command_name_in_prose_is_anchored` — R3 regression.
