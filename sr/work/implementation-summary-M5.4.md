# Implementation summary: `M5.4` — enforced rules become one-line pointers

base: 4c89fdd5930c2c4ac597fc7259fb0501f400f7ae

## What changed

Candidates came from each rule's provenance line (`enforced: …`, added by M5.1). A rule was shrunk only where its `enforced:` names a refusal or behaviour the CLI already guarantees; the pointer keeps the command and the effect, so an agent still saves the wasted turn before enforcement fires.

`specy_road/templates/specyrd/agents-md-block.md`, `## Task loop`:

- **Task pickup** — "registers (rows record `owner`) … The target is always a leaf; ancestors only roll up progress" becomes "syncs the integration branch, claims a leaf, never an ancestor (the row records `owner`), pushes the claim, then creates `feature/rm-*`"; the `--local` advice stays.
- **`on_complete: pr`** — "do not re-pick: pickup refuses …" becomes "pickup will not re-pick it"; "`Complete` and its claim released only on its feature branch" and the instruction to leave the integration-branch row alone stay.
- **Pickup order** — the two bullets merge into one line: pickup decides readiness and order (`Blocked` first, then MR-rejected, then outline order, not chunk order; a phase or milestone dependency is met when every leaf under it is `Complete`, not by its own `status`; only a `type: gate` dependency holds work back, never `execution_milestone`), with `--interactive` (by number) and `--under` (a subtree).
- **Review roles** — "it refuses without a recorded review. Policy: `roadmap/orchestration.yaml`." becomes "it refuses without the reviews `roadmap/orchestration.yaml` requires". The executor/reviewer division of labour and the interactive human-approval exception stay: the gate does not check who the executor was, so those parts are guidance, not enforcement.

- **Shared checkouts** (review round 2) — the guard-enforced sentences ("Commit by explicit path …; never `git add -A`, `git commit -a`, or a bare `git commit` — the index is shared." and "Never `stash`, `reset --hard`, `checkout -- .`, `clean`, `rebase`, `commit --amend`, or switch branches in a tree another session may be using") leave the paragraph for one line: **Git in a shared tree:** commit only with `git commit --only <paths>`; never stash, hard-reset, discard changes, clean, rebase, amend or switch branches in a tree another session may be using. The opt-in tool-call guard (`specy-road session guard`) refuses these while another session is live; `docs/orchestration.md` lists them all. The commands stay named because the hooks are opt-in and without them this line is the only check. The paragraph keeps its guidance (session start/list, `git status`, your own worktree for pickup and grind, your own files, `base: <sha>`, the toolkit floor) and becomes a list item, so the pointer line costs no extra line. The pointer is a separate line rather than a sentence in the paragraph because rendering turns `docs/orchestration.md` into a versioned GitHub URL, and the paragraph is copied word for word into the bootstrap prompt (`test_bootstrap_prompt_carries_the_same_rule`): a URL there would break that copy at the next version bump.

`specy_road/templates/specyrd/claude-md-block.md`: **Roadmap-linked implementation** names `specy-road do-next-available-task` as the thing that registers the claim on the integration branch and creates `feature/rm-<codename>`, instead of restating both steps. "Don't rename a node's title mid-flight" stays (nothing enforces it). **Other agents share this checkout** (round 2): "commit by explicit path, never `-A`/`-a`; no stash, reset, or branch switches here — use your own worktree" becomes "use your own worktree; the opt-in tool-call guard refuses stash, reset, branch switches and `-A`/`-a` while another session is live".

`suggested_prompts/bootstrap-agents-md.md` (added to the touch zones for round 2): the reproduced shared-checkout paragraph is replaced by the new paragraph and the pointer line, as two sub-bullets.

Provenance lines were updated for the changed and merged bullets; every rule still carries one.

### Left alone, and why

- **Lean changes and tests**: enforced only by reviewer judgement and the CI private-import baseline, and pinned word for word to the toolkit's root `AGENTS.md` and the bootstrap prompt (both outside the touch zones).
- Abort-after-finish (finish only warns), Running many leaves, Workers, When nothing is pickable, Finding things, Precedence: guidance or advisory per their provenance.

## Acceptance

- **A1** — each rule above whose provenance names a CLI refusal or guarantee (review gate, pickup) or a tool-call guard denial (shared-tree git) is one line naming what enforces it; the guard line also says the hooks are opt-in. Validate enforces none of the block's rules beyond the block-staleness warning (Precedence).
- **A2** — `tests/test_enforced_rules_pointers.py::test_each_removed_sentence_is_a_pointer_to_an_enforcement_point` has one row per removed fact (23 rows; round 2 added five, mapped to `tests/test_tool_call_guard.py::test_destructive_commands_are_classified` and `::test_deny_only_with_another_live_session`); for each it asserts the old text is gone from the rendered block, the pointer phrase carrying that fact is present, and the named enforcing test (`tests/<file>::<test>`) exists. A pointer that drops a qualifier fails its own row: rendering the block without "then MR-rejected, " fails the MR-rejected row.
- **A3** — context meter (`print_injected_context` on a fresh `init project`, which is what `validate` prints):
  - before (base `4c89fdd`): `specy-road section 52 lines, 7,679 bytes`
  - after round 1: `specy-road section 51 lines, 7,561 bytes`
  - after round 2: `specy-road section 51 lines, 7,672 bytes` (−1 line, −7 bytes against the pre-M5.4 base). The guard pointer adds the guard's name, its opt-in status and a docs link that renders as a 79-byte URL, which together outweigh the two sentences it replaces. The margin is small but measured.
  - CLAUDE.md block rendered (empty prefix): 73 lines; round 2 moves it from 3,049 to 3,076 bytes (+27) because the pointer names the guard and its live-session condition. A3 measures the AGENTS.md section only.
  - `test_the_meter_reports_a_shorter_section_than_before` asserts the meter's numbers stay under the pre-M5.4 measurement.

## Touch zones (confirmed)

`specy_road/templates/specyrd/agents-md-block.md`, `specy_road/templates/specyrd/claude-md-block.md`, `tests/`, and `suggested_prompts/bootstrap-agents-md.md` (added for round 2: the shared-checkout paragraph is pinned word for word there).

## Follow-ups (outside this leaf)

- `sr/AGENTS.md` carries the old managed block; `specy-road validate` on `sr/` will warn it is stale until someone runs `specy-road refresh-stubs` there.
- `docs/orchestration.md` § "Working in one shared checkout" says the scaffold `AGENTS.md` repeats its rules; it now points at them instead. That still holds, so no edit.

## Gates

- `pytest` (full suite, at `2d47c6c`): 2582 passed, 2 skipped. After the review fix, the touched test files only (as the coordinator asked): `tests/test_enforced_rules_pointers.py tests/test_agents_md_block.py tests/test_lean_rules.py tests/test_shared_checkout_guidance.py tests/test_review_round6_docs.py tests/test_brainstorm_prompt_fixes.py tests/test_doc_links.py tests/test_validate_stale_commands.py tests/test_specyrd_init_guide_block.py`: 88 passed
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: exit 0
- `specy-road file-limits`: OK
- Round 2 (at `fe54752`), touched and related files only: `pytest tests/test_enforced_rules_pointers.py tests/test_shared_checkout_guidance.py tests/test_agents_md_block.py tests/test_lean_rules.py tests/test_review_round6_docs.py tests/test_brainstorm_prompt_fixes.py tests/test_doc_links.py tests/test_validate_stale_commands.py tests/test_specyrd_init_guide_block.py tests/test_tool_call_guard.py`: 194 passed; `specy-road validate` (dogfood) exit 0; `specy-road file-limits` OK; `ruff check` on the two edited test files clean. Full suite not re-run.

## Review round 1 (cursor-grok-4.6-high, block at `2d47c6c`)

- **A2: MR-rejected tier dropped from the pickup-order pointer.** Restored: "`Blocked` first, then MR-rejected, then outline order", mapped to `tests/test_do_next_queue.py::test_available_orders_blocked_then_mr_rejected_then_not_started` in its own row.
- **Other pointers that had dropped a qualifier, now restored:** "not chunk order"; "phase *or milestone*"; "every leaf under it is `Complete`, not by its own `status`"; `--interactive` "by number"; `--under` "to a subtree"; pickup "syncs the integration branch", "never an ancestor", "the row records `owner`"; `on_complete: pr` "and its claim released"; review roles "on your own work" and the interactive human-approval exception (guidance, not enforcement, so it should not have been cut); CLAUDE.md "on the integration branch".
- **Mapping test granularity:** split into one row per fact so a dropped qualifier fails its own row.

## Review round 2 (gpt-6.1-sol block at `d1f35f3`; cursor-grok-4.6-high approved)

- **A1: guard-enforced shared-checkout rules still restated.** Now one pointer line naming `specy-road session guard`, marked opt-in, citing `docs/orchestration.md`, and keeping the commands as guidance for sessions without hooks. The CLAUDE.md line and the bootstrap prompt follow. The removed sentences are mapped in five new `REMOVED` rows.

## Added

- `tests/test_enforced_rules_pointers.py` — new file; A2 and A3 have no existing test to extend.
- `REMOVED` table — the A2 mapping, one row per fact: removed text → pointer phrase → enforcing test.
- `_flat` helper — the CLAUDE.md block wraps sentences across lines, so matching must ignore line breaks.
- `test_each_removed_sentence_is_a_pointer_to_an_enforcement_point` — A2 (parametrized over `REMOVED`).
- `_BEFORE_LINES`, `_BEFORE_BYTES` and `test_the_meter_reports_a_shorter_section_than_before` — A3, measured through the meter's public `injected_context`.
- Round 2: five `REMOVED` rows (three AGENTS.md, two CLAUDE.md) for the guard-enforced shared-checkout sentences — A2 for the new pointer.
- Round 2: `_SENTENCES` in `tests/test_shared_checkout_guidance.py` pins the new pointer phrases in place of the removed sentence; `test_claude_md_block_points_at_it` asserts the CLAUDE.md guard pointer in place of the removed `never -A/-a` wording; `test_bootstrap_prompt_carries_the_same_rule` keeps its paragraph assertion unchanged and gains one assertion that the prompt also carries the pointer line, up to its docs link, because the pointer left the pinned paragraph.
- Helpers, branches or guards in product code: none. Mocks: none (`HOME`/`CODEX_HOME` are set so a machine-local file cannot enter the measurement).
