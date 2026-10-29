# Implementation summary: `M5.1` — every managed AGENTS.md rule carries its provenance

base: `d1350018ae3c41554a1cbdddbe126a04dccebcdd`

## What changed

- **Templates (A1).** Every `- ` bullet in `specy_road/templates/specyrd/agents-md-block.md` (19) and `claude-md-block.md` (12), plus the two bold rule paragraphs in the AGENTS.md block (**Precedence**, **Shared checkouts and other agents**), is followed on the next line by `<!-- prevents: ... | enforced: ... | ref: ... -->`. Each comment names the failure, where it is enforced (a module, CLI check or CI gate, or `advisory` when nothing checks it), and a doc, CHANGELOG section or test. Every cited path was checked to exist. Comments use no backticked `specy-road <cmd>` and no `SPECY_ROAD_*` names, so `tests/test_review_round6_docs.py`'s raw-template command scan sees the same set as before. The numbered load-order items are not annotated: they are reading order, not rules, and are not bullets.
- **Renderer (A2).** `strip_provenance()` and its `PROVENANCE` pattern in `specy_road/agent_guide_block.py` drop whole lines that fully match the format. `render_guide_lines` and `render_agents_lines` (`specy_road/agents_md_block.py`, which imports the helper) both call it before placeholder and doc-link substitution. I snapshotted `render_agents_lines()`, `render_guide_lines()` and `render_guide_lines("sr/")` before editing, and all three are byte-identical after the change (`cmp`). Existing managed blocks therefore stay `current`, and no consumer pays any context for the comments.
- **Test (A3).** `test_every_rule_in_a_block_template_is_followed_by_its_provenance` (parametrized over both templates) fails and names the rule when a bullet or bold rule paragraph is not followed by a well-formed provenance line. I checked it by deleting one comment from each template: it failed and named `**When nothing is pickable:**` and `**Roadmap-linked implementation.**`. I then restored both templates.

## Existing tests changed (not weakened)

- `tests/test_lean_rules.py` and `tests/test_shared_checkout_guidance.py` read the raw template, which now holds maintainer-only lines. Both now read `render_agents_lines()`, the text agents receive. This is what their docstrings say they pin ("injected into every adopter agent's context"; "the scaffold AGENTS.md carries the full rule"). Every assertion is unchanged, including the 12-line cap on the Lean section and the exact-paragraph match against the bootstrap prompt.

## Touch zones

Confirmed accurate. Final list as given: the two templates, `specy_road/agents_md_block.py`, `specy_road/agent_guide_block.py`, `tests/`. No edits were needed elsewhere. `suggested_prompts/` needs no update because the rendered text is unchanged.

## Verification

- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: OK. Its "AGENTS.md has no specy-road section" warning predates this change, because the fixture has no block.
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK
- `specy-road file-limits`: OK
- `ruff check` on the changed Python files: clean
- `pytest`: 2254 passed, 2 skipped

## Added

- helper `strip_provenance` (`specy_road/agent_guide_block.py`): the one shared stripping helper the planning sheet asks for, used by both renderers.
- constant `PROVENANCE` (`specy_road/agent_guide_block.py`): the format, defined once and shared by the stripper and the A3 test.
- branch or guard: none
- mock: none
- test `test_every_rule_in_a_block_template_is_followed_by_its_provenance` (`tests/test_agents_md_block.py`, 2 parametrized cases): A3.
- assertion `"<!--" not in text` added to the existing `test_block_text_is_the_full_rule_set`: A2 for the AGENTS.md render.
- assertion `not any("<!--" in ln ...)` added to the existing `test_the_guide_block_is_prefixed_in_a_nested_layout` (`tests/test_specyrd_init_guide_block.py`): A2 for the CLAUDE.md render.
- fixture constant `TEMPLATES` (`tests/test_agents_md_block.py`): the path the A3 test reads.
