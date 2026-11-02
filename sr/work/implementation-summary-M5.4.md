# Implementation summary: `M5.4` — enforced rules become one-line pointers

base: 4c89fdd5930c2c4ac597fc7259fb0501f400f7ae

## What changed

Candidates came from each rule's provenance line (`enforced: …`, added by M5.1). A rule was shrunk only where its `enforced:` names a refusal or behaviour the CLI already guarantees; the pointer keeps the command and the effect, so an agent still saves the wasted turn before enforcement fires.

`specy_road/templates/specyrd/agents-md-block.md`, `## Task loop`:

- **Task pickup** — "registers (rows record `owner`) … The target is always a leaf; ancestors only roll up progress" becomes "syncs the integration branch, claims a leaf, never an ancestor (the row records `owner`), pushes the claim, then creates `feature/rm-*`"; the `--local` advice stays.
- **`on_complete: pr`** — "do not re-pick: pickup refuses …" becomes "pickup will not re-pick it"; "`Complete` and its claim released only on its feature branch" and the instruction to leave the integration-branch row alone stay.
- **Pickup order** — the two bullets merge into one line: pickup decides readiness and order (`Blocked` first, then MR-rejected, then outline order, not chunk order; a phase or milestone dependency is met when every leaf under it is `Complete`, not by its own `status`; only a `type: gate` dependency holds work back, never `execution_milestone`), with `--interactive` (by number) and `--under` (a subtree).
- **Review roles** — "it refuses without a recorded review. Policy: `roadmap/orchestration.yaml`." becomes "it refuses without the reviews `roadmap/orchestration.yaml` requires". The executor/reviewer division of labour and the interactive human-approval exception stay: the gate does not check who the executor was, so those parts are guidance, not enforcement.

`specy_road/templates/specyrd/claude-md-block.md`: **Roadmap-linked implementation** names `specy-road do-next-available-task` as the thing that registers the claim on the integration branch and creates `feature/rm-<codename>`, instead of restating both steps. "Don't rename a node's title mid-flight" stays (nothing enforces it).

Provenance lines were updated for the changed and merged bullets; every rule still carries one.

### Left alone, and why

- **Shared checkouts paragraph** (and its CLAUDE.md pointer): the tool-call guard would cover the stash/reset/branch-switch part, but its hooks are opt-in (`docs/optional-ai-tooling-patterns.md`: "Hooks are not installed for you"), so in most consumer repos the prose is the only protection. Its provenance already says "the rest is advisory". It is also pinned verbatim in `suggested_prompts/bootstrap-agents-md.md` (outside the touch zones).
- **Lean changes and tests**: enforced only by reviewer judgement and the CI private-import baseline, and pinned word for word to the toolkit's root `AGENTS.md` and the bootstrap prompt (both outside the touch zones).
- Abort-after-finish (finish only warns), Running many leaves, Workers, When nothing is pickable, Finding things, Precedence: guidance or advisory per their provenance.

## Acceptance

- **A1** — each rule above whose provenance names a CLI refusal or guarantee (review gate, pickup) is one line naming the command that enforces it. Validate enforces none of the block's rules beyond the block-staleness warning (Precedence), and the tool-call guard is opt-in (see above).
- **A2** — `tests/test_enforced_rules_pointers.py::test_each_removed_sentence_is_a_pointer_to_an_enforcement_point` has one row per removed fact (18 rows); for each it asserts the old text is gone from the rendered block, the pointer phrase carrying that fact is present, and the named enforcing test (`tests/<file>::<test>`) exists. A pointer that drops a qualifier fails its own row: rendering the block without "then MR-rejected, " fails the MR-rejected row.
- **A3** — context meter (`print_injected_context` on a fresh `init project`, which is what `validate` prints):
  - before (base `4c89fdd`): `specy-road section 52 lines, 7,679 bytes`
  - after: `specy-road section 51 lines, 7,561 bytes` (−1 line, −118 bytes)
  - CLAUDE.md block rendered: 73 lines, 3,325 → 3,312 bytes.
  - `test_the_meter_reports_a_shorter_section_than_before` asserts the meter's numbers stay under the pre-M5.4 measurement.

## Touch zones (confirmed)

`specy_road/templates/specyrd/agents-md-block.md`, `specy_road/templates/specyrd/claude-md-block.md`, `tests/`. No other path was needed.

## Follow-ups (outside this leaf)

- `sr/AGENTS.md` carries the old managed block; `specy-road validate` on `sr/` will warn it is stale until someone runs `specy-road refresh-stubs` there.
- `suggested_prompts/bootstrap-agents-md.md` "What the block already covers" still lists the same topics, which remain covered; no edit needed.

## Gates

- `pytest` (full suite, at `2d47c6c`): 2582 passed, 2 skipped. After the review fix, the touched test files only (as the coordinator asked): `tests/test_enforced_rules_pointers.py tests/test_agents_md_block.py tests/test_lean_rules.py tests/test_shared_checkout_guidance.py tests/test_review_round6_docs.py tests/test_brainstorm_prompt_fixes.py tests/test_doc_links.py tests/test_validate_stale_commands.py tests/test_specyrd_init_guide_block.py`: 88 passed
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: exit 0
- `specy-road file-limits`: OK

## Added

- `tests/test_enforced_rules_pointers.py` — new file; A2 and A3 have no existing test to extend.
- `REMOVED` table — the A2 mapping, one row per fact: removed text → pointer phrase → enforcing test.
- `_flat` helper — the CLAUDE.md block wraps sentences across lines, so matching must ignore line breaks.
- `test_each_removed_sentence_is_a_pointer_to_an_enforcement_point` — A2 (parametrized over `REMOVED`).
- `_BEFORE_LINES`, `_BEFORE_BYTES` and `test_the_meter_reports_a_shorter_section_than_before` — A3, measured through the meter's public `injected_context`.
- Helpers, branches or guards in product code: none. Mocks: none (`HOME`/`CODEX_HOME` are set so a machine-local file cannot enter the measurement).

## Review round 1 (cursor-grok-4.6-high, block at `2d47c6c`)

- **A2: MR-rejected tier dropped from the pickup-order pointer.** Restored: "`Blocked` first, then MR-rejected, then outline order", mapped to `tests/test_do_next_queue.py::test_available_orders_blocked_then_mr_rejected_then_not_started` in its own row.
- **Other pointers that had dropped a qualifier, now restored:** "not chunk order"; "phase *or milestone*"; "every leaf under it is `Complete`, not by its own `status`"; `--interactive` "by number"; `--under` "to a subtree"; pickup "syncs the integration branch", "never an ancestor", "the row records `owner`"; `on_complete: pr` "and its claim released"; review roles "on your own work" and the interactive human-approval exception (guidance, not enforcement, so it should not have been cut); CLAUDE.md "on the integration branch".
- **Mapping test granularity:** split into one row per fact so a dropped qualifier fails its own row.
