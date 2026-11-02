# Implementation summary: `M5.4` — enforced rules become one-line pointers

base: 4c89fdd5930c2c4ac597fc7259fb0501f400f7ae

## What changed

Candidates came from each rule's provenance line (`enforced: …`, added by M5.1). A rule was shrunk only where its `enforced:` names a refusal or behaviour the CLI already guarantees; the pointer keeps the command and the effect, so an agent still saves the wasted turn before enforcement fires.

`specy_road/templates/specyrd/agents-md-block.md`, `## Task loop`:

- **Task pickup** — the step-by-step of what pickup does (sync, register, `owner`, push, branch) and "the target is always a leaf" become "claims a leaf, pushes the claim, then creates `feature/rm-*`"; the `--local` advice stays.
- **`on_complete: pr`** — "do not re-pick: pickup refuses …" becomes "pickup will not re-pick it"; the instruction to leave the integration-branch row alone stays.
- **Pickup order** — the two bullets (Blocked first / `execution_milestone` / gate / rollup, and outline order / `--interactive` / `--under`) merge into one line that says pickup decides readiness and order and names each fact in a parenthesis.
- **Review roles** — the human-approval exception, "never `--yes` on your own work; it refuses …" and "Policy: …" become one clause: "`mark-implementation-reviewed` refuses without the reviews `roadmap/orchestration.yaml` requires". The executor/reviewer division of labour stays: the gate does not check who the executor was, so that part is guidance, not enforcement.

`specy_road/templates/specyrd/claude-md-block.md`: **Roadmap-linked implementation** names `specy-road do-next-available-task` as the thing that registers the claim and creates `feature/rm-<codename>`, instead of restating both steps. "Don't rename a node's title mid-flight" stays (nothing enforces it).

Provenance lines were updated for the changed and merged bullets; every rule still carries one.

### Left alone, and why

- **Shared checkouts paragraph** (and its CLAUDE.md pointer): the tool-call guard would cover the stash/reset/branch-switch part, but its hooks are opt-in (`docs/optional-ai-tooling-patterns.md`: "Hooks are not installed for you"), so in most consumer repos the prose is the only protection. Its provenance already says "the rest is advisory". It is also pinned verbatim in `suggested_prompts/bootstrap-agents-md.md` (outside the touch zones).
- **Lean changes and tests**: enforced only by reviewer judgement and the CI private-import baseline, and pinned word for word to the toolkit's root `AGENTS.md` and the bootstrap prompt (both outside the touch zones).
- Abort-after-finish (finish only warns), Running many leaves, Workers, When nothing is pickable, Finding things, Precedence: guidance or advisory per their provenance.

## Acceptance

- **A1** — each rule above whose provenance names a CLI refusal or guarantee (review gate, pickup) is one line naming the command that enforces it. Validate enforces none of the block's rules beyond the block-staleness warning (Precedence), and the tool-call guard is opt-in (see above).
- **A2** — `tests/test_enforced_rules_pointers.py::test_each_removed_sentence_is_a_pointer_to_an_enforcement_point` lists all 15 removed sentences; for each it asserts the sentence is gone from the rendered block, its pointer is present, and the named enforcing test (`tests/<file>::<test>`) exists.
- **A3** — context meter (`print_injected_context` on a fresh `init project`, which is what `validate` prints):
  - before (base `4c89fdd`): `specy-road section 52 lines, 7,679 bytes`
  - after: `specy-road section 51 lines, 7,185 bytes` (−1 line, −494 bytes)
  - CLAUDE.md block rendered: 73 lines, 3,325 → 3,286 bytes.
  - `test_the_meter_reports_a_shorter_section_than_before` asserts the meter's numbers stay under the pre-M5.4 measurement.

## Touch zones (confirmed)

`specy_road/templates/specyrd/agents-md-block.md`, `specy_road/templates/specyrd/claude-md-block.md`, `tests/`. No other path was needed.

## Follow-ups (outside this leaf)

- `sr/AGENTS.md` carries the old managed block; `specy-road validate` on `sr/` will warn it is stale until someone runs `specy-road refresh-stubs` there.
- `suggested_prompts/bootstrap-agents-md.md` "What the block already covers" still lists the same topics, which remain covered; no edit needed.

## Gates

- `pytest` (full suite): 2582 passed, 2 skipped
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: exit 0
- `specy-road file-limits`: OK

## Added

- `tests/test_enforced_rules_pointers.py` — new file; A2 and A3 have no existing test to extend.
- `REMOVED` table — the A2 mapping: removed sentence → pointer → enforcing test.
- `_flat` helper — the CLAUDE.md block wraps sentences across lines, so matching must ignore line breaks.
- `test_each_removed_sentence_is_a_pointer_to_an_enforcement_point` — A2 (parametrized over `REMOVED`).
- `_BEFORE_LINES`, `_BEFORE_BYTES` and `test_the_meter_reports_a_shorter_section_than_before` — A3, measured through the meter's public `injected_context`.
- Helpers, branches or guards in product code: none. Mocks: none (`HOME`/`CODEX_HOME` are set so a machine-local file cannot enter the measurement).
