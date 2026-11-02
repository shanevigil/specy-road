# Implementation summary: `M4.6` — Lenses from the frame and a ranked node list in the recommend prompt

Implementation commit: `c79dc320a290edb2770dbc287e73cbd60c50c1bf` (base `7e03d863afbbd29c0ff595914fa1f2aae10d49ea`).

## What changed

**A1 — personas and directions from `served`; `--profile personal`.**
`brainstorm_lenses` now holds the persona examples and the directions per profile as data, and builds the operators and directions with `operators_for(profile, served)` and `directions_for(profile, served)`. Once the frame records `served` (its `assumed:` marker is removed), the "Ordinary personas" operator says to generate as people "drawn from who the frame says is served — <served> —" and leave out anyone it says is not served. The `user-segments` direction becomes `segments of who is served (<served>)`. The new `personal` profile adds seven lenses for a tool with one author (friction log, future self, inversion, delete before adding, one evening, analogous tools, jobs to be done). It also has its own default personas and directions (daily use, setup and maintenance, the author's future self, technical layers, someone else's tool of the same kind), and its default idea kind is `feature`. `--profile` choices come from `PROFILES`, so the CLI accepts `personal` without an argparse change. `allocation_lines` and `shard_lines` in `brainstorm_prompt_diverge` use the frame-derived operators and directions. While `served` is not recorded yet (for example in the round-1 prompt written at `start`, before framing), the prompt says the personas are placeholders to be drawn from `served`. Shard prompts are rewritten on every `frame` call, so they carry the substituted text. With no frame, the product profile's text matches the old text exactly: the module-level `OPERATORS` and `DIRECTIONS` are kept and are equal to `operators_for("product")` and `directions_for("product")`.

**A2 — ranked node list in the recommend prompt.**
`search_index.similar_node_ids(root, queries, per_query=5, limit=40)` ranks the live node and planning chunks for each query, using the BM25 and structural fusion that `search` already uses. It fuses the per-query rankings with RRF, so a node near several ideas comes first. It returns `None`, not `[]`, when FTS5 or the index is unavailable. `_existing_roadmap_lines` in `brainstorm_prompt` now lists **Phases** and then up to 40 **Nodes closest to the ideas**, ranked on the idea titles. It ends with "This is N of M nodes" and a pointer to `specy-road search` and `list-nodes`. When the index cannot rank, the prompt falls back to the old full list, capped at 150.

**Docs.** `docs/brainstorming.md` covers `--profile personal`, personas and the segments direction drawn from `served`, and the ranked inventory with its fallback.

## Touch zones (final)

As listed, all used: `specy_road/bundled_scripts/brainstorm_lenses.py`, `specy_road/bundled_scripts/brainstorm_prompt_diverge.py`, `specy_road/bundled_scripts/brainstorm_prompt.py`, `specy_road/search_index.py`, `docs/brainstorming.md`, `tests/` (`tests/test_brainstorm_lenses.py` new; `tests/test_brainstorm_cli.py` one line).

Not edited because they are outside the touch zones; they are follow-ups, not blockers:
- `specy_road/bundled_scripts/brainstorm_cli_args_v2.py`: the `--profile` help still says "product (default) or technical". `personal` is accepted because the choices come from `PROFILES`.
- `specy_road/cli_usage.py`: the usage text names only `--profile technical`.
- `gui/pm-gantt/src/types.ts`: `profile: "product" | "technical"`. This is a type only; the panel shows the profile string unchanged at runtime.
- `suggested_prompts/brainstorm-roadmap.md`: not checked for a profile list. No acceptance item requires it.

## Test change to note

`tests/test_brainstorm_cli.py::test_the_roadmap_inventory_moves_to_the_converge_prompt`: this test added an idea titled "One" and asserted that `` `M0.1` `` appears in the recommend prompt. That held only because the prompt used to list every node, which A2 replaces. The idea is now titled "Shared contracts skeleton", so `M0.1` is listed because it is ranked close to the idea. The `` `M0.1` in text `` assertion and the other assertions are unchanged.

## Verification

- `python -m pytest -q`: 2662 passed, 2 skipped (16 min).
- `python -m pytest -q tests/test_brainstorm_lenses.py`: 10 passed.
- `specy-road validate`, `export --check` and `digest --check` with `--repo-root tests/fixtures/specy_road_dogfood`: exit 0. The `.specyrd/cache` these runs wrote into the fixture was removed afterwards.
- `specy-road file-limits`: OK. `ruff check` on the changed Python files: clean.

## Added

### Helpers
- `brainstorm_lenses.served_answer(frame)`: the `served` answer without `assumed:`, so a provisional marker does not leak into persona text.
- `brainstorm_lenses.operators_for(profile, served)`: builds the persona operator from `served`, or from the profile's default personas when `served` is missing (A1).
- `brainstorm_lenses.directions_for(profile, served)`: a direction list per profile, with `served` in place of "user segments" (A1).
- `brainstorm_lenses.PERSONAL_LENSES`, `_DEFAULT_PERSONAS`, `_DIRECTIONS`, `_PRODUCT_DIRECTIONS`, `_OTHER_OPERATORS`: per-profile data for the `personal` profile and for frame-derived text (A1; the sheet says "lens sets are data in brainstorm_lenses").
- `brainstorm_lenses.PROFILES["personal"]`, `DEFAULT_KINDS_BY_PROFILE["personal"]`: register the profile, which also adds it to the CLI choices (A1).
- `search_index.similar_node_ids(root, queries, ...)`: RRF-fused node ranking across the idea titles. It returns `None` without the index so the caller can fall back (A2).
- `brainstorm_prompt._similar_node_ids(root, session)`: calls the search helper with the idea titles. Any exception becomes `None`, the same contract as "the prompt must still render" (A2).
- `brainstorm_prompt._node_line(n)`: the node line format, shared by the ranked list and the fallback list.
- `brainstorm_prompt._MAX_SIMILAR_NODES = 40`: caps the ranked list so the prompt stays readable (A2).

### Branches / guards
- `allocation_lines`: a placeholder note when `served` is not recorded yet. The round-1 prompt is written before framing, so the agent is told to draw personas from its own `served` answer (A1).
- `directions_for`: replaces the first direction only when it is "user segments", so the `personal` profile's directions are not rewritten.
- `_existing_roadmap_lines`: `ranked is None` selects the old full list, the fallback the planning sheet asks for. Phases are excluded from the ranked list so they are not listed twice. There are "(none)" placeholders for an empty phase list and for an empty match list.
- `similar_node_ids`: keeps only live `node` and `planning` chunks with a `node_id`, and removes duplicate node ids within a query's ranking.

### Mocks
- `monkeypatch.setattr(search_index, "fts5_available", lambda: False)` in two tests: simulates an interpreter without FTS5 to exercise the fallback and the `None` contract.

### Tests (`tests/test_brainstorm_lenses.py`)
- `test_served_answer_drops_the_assumed_marker`: the marker is removed and whitespace trimmed.
- `test_without_a_frame_the_product_text_is_unchanged`: guards behaviour preservation with no frame.
- `test_round_one_says_the_personas_are_placeholders_until_served_is_recorded`: the placeholder note appears, and goes away once `served` is recorded.
- `test_recorded_served_answer_drives_personas_and_directions`: CLI `start --panel` then `frame`. The shard prompt's operators, directions and shard cell use `served`, and the procurement officer is gone (A1).
- `test_personal_profile_is_a_lens_set_for_single_author_tools`: CLI `start --profile personal` gives the personal lenses, personas, directions and kind, and none of the product ones (A1).
- `test_personal_profile_with_served_still_names_the_served_people`: with the personal profile, `served` overrides the default personas and the directions are not rewritten.
- `test_recommend_lists_phases_plus_the_nodes_closest_to_the_ideas`: phases are listed once and matching nodes are ranked in (A2).
- `test_recommend_leaves_out_nodes_no_idea_is_near`: a node unrelated to the idea is left out, and the prompt says "N of 6" (A2: "instead of every node").
- `test_recommend_falls_back_to_every_node_without_the_index`: the full-list fallback (A2).
- `test_similar_node_ids_fuses_queries_and_reports_no_index_as_none`: a node near several queries ranks first, an empty query list gives `[]`, and no FTS5 gives `None`.
