# Implementation summary: M11.71 — review loops escalate on their own; criteria are written with bounds

## Touch zones (final)

Committed on this branch with `specy-road edit-node M11.71 --add touch_zones=…` (commit `512c7626`), at the
maintainer's direction, on top of the original seven:

- `specy_road/bundled_scripts/role_prompt.py` — `prompt`'s argparse and the `rca` gate in `build_prompt` (A1 `--force`).
- `specy_road/bundled_scripts/planning_sheet_bootstrap.py` — added as asked; **left unchanged**, because it reads the
  template's `##` titles and none changed.
- `specy_road/templates/planning-node/feature-sheet.md.template` — the planning-sheet template (A2). The maintainer
  named it `feature-sheet.md`; zones match a file exactly or a directory prefix, so the real file name was used.
- `specy_road/schemas/rca-record.schema.json` — not in the maintainer's list; found while implementing. Its
  `trigger.rule` enum (`additionalProperties: false`) would reject an RCA record for the new `same_family` rule or a
  `forced` analysis, so no such escalation could ever be resolved.

Unchanged zones: `specy_road/review_gate.py`, `specy_road/bundled_scripts/review_cli.py` (status already reports
whatever `loop_state` returns, including the new `family`/`reason` keys in `escalation`).

## A1 — escalation by reviewer family, and `prompt --role rca --force --reason`

- `review_rca.escalation` gains a `same_family` rule between `same_acceptance` and `review_rounds`: for each roster
  family (an unrostered model is its own family), take its verdict in each round it reviewed since the last RCA
  (block if any of its models blocks there); when its last `escalate_same_acceptance_blocks` verdicts all block, the
  leaf escalates, whatever acceptance ids or models those blocks named. An approval from the family breaks the run;
  rounds the family did not review neither break nor extend it. The per-id rule is kept and checked first. No new
  policy key: the threshold reuses `escalate_same_acceptance_blocks` (3), so `orchestration_config.py` and the
  orchestration schema stay untouched.
- `prompt --role rca --force --reason '<why>'` builds an RCA prompt on a leaf that is not escalated
  (`review_rca.forced_escalation`, rule `forced`). It needs a review round since the last RCA; an active escalation wins
  and `--force` is ignored with a note on stderr. `--force` without a non-empty `--reason`, `--reason` without
  `--force`, or `--force` with another role is an argparse error (exit 2). The reason is recorded in the prompt
  (`describe()`) and pre-filled into the RCA skeleton's `trigger.reason`; the schema requires `reason` when the rule
  is `forced`. A forced record validates only when no escalation was active at its round (otherwise the usual
  rule-mismatch error), and it resolves rounds up to its `round` like any RCA.
- The rca precondition no longer says "stop unless `handoff status` reports `escalated`" for a forced prompt; it uses
  the generic registry-claim check instead.
- The RCA gate moved from `role_prompt.build_prompt` into `review_rca.rca_trigger` (same two error messages; the
  not-escalated one now also names `--force --reason`), which keeps `build_prompt` shorter.

## A2 — acceptance-criteria checklist

- `docs/roadmap-authoring.md`, section "Writing implementable `agentic` tasks": a bold-lead paragraph
  **Acceptance criteria checklist.** with the three items (state what is out of scope; bound concurrency and input
  classes; name the observable check). The doc sits at the 400-line docs cap, so to fit the paragraph two hard-wrapped
  two-line paragraphs in the same section ("Worth adding when they apply…", "**Example (JSON node excerpt).**…") were
  joined onto one line each; their words are unchanged.
- The feature-sheet template's `## Tasks / checklist` gains one line pointing to that checklist. It is not under
  `## Approach` or `## Intent`, whose template bodies are the unauthored-sheet fingerprint
  (`planning_sheet_bootstrap._PLACEHOLDER_SECTIONS`).
- `docs/orchestration-review.md`: the escalation paragraph names `same_family` and `--force --reason`.

## Verification

- `pytest -n 4 tests/test_review_rca.py tests/test_planning_sheet_bootstrap.py tests/test_role_prompt_file_limits.py`: 31 passed.
- The 27 neighbouring test files that touch prompts, the review CLI and files, the sheet template and the two docs
  (`grep -rlE "orchestration-review.md|roadmap-authoring.md|rca-record|feature-sheet|role_prompt|review_rca" tests`,
  plus `test_review_cli`, `test_unauthored_leaf_guard`, `test_brief_placeholder_intent`,
  `test_finish_scaffold_planning`, `test_brainstorm_promote_judgement`): 360 passed.
- `specy-road file-limits`: OK. `docs/roadmap-authoring.md` stays at 400 lines (see A2).
- `scripts/check_test_private_imports.py`: 0 new.
- Not clean, not from this change: `ruff check specy_road tests scripts` reports one C901 in
  `specy_road/bundled_scripts/review_packet_uncommitted_refs.py`, which this branch does not touch (`ruff check` on
  the changed files passes). `scripts/check_clones.py` could not run: `pylint` is not installed in this environment.
- Full `pytest -n auto` was not run (load average ~40 on this machine; the targeted runs took 3 and 6 minutes).

## Added

### Helpers / branches / guards
- `review_rca.Round.family_verdicts` — per round, each family's block-or-not verdict; the family rule's input.
- `review_rca._family` — model → roster family, falling back to the model id, so an unrostered model still counts.
- `review_rca._family_streak` — the family whose last N verdicts all block; the `same_family` rule.
- `review_rca.escalation(..., family=)` parameter and its `same_family` branch — A1's new rule.
- `review_rca.forced_escalation` — the `forced` escalation, `None` when no round is unresolved or the reason is blank.
- `review_rca.rca_trigger` — the RCA gate (not escalated / forced / party), moved out of `build_prompt` and extended for force.
- `review_rca.rca_trigger` stderr note when `--force` meets an active escalation — the reason would otherwise vanish silently.
- `review_rca._rca_semantic_errors` `forced` branch — validates a forced record against the rounds it claims.
- `Escalation.family` / `Escalation.reason` fields and their `describe()` cases — name the trigger in status and the prompt.
- `LoopState.resolved` — rounds already covered by an RCA, needed to compute a forced window.
- `_skeleton` `reason:` in the trigger line — pre-fills the recorded reason into the analyst's record.
- `role_prompt.main` `--force` / `--reason` options and their two `p.error` guards — the CLI half of A1.
- `role_prompt.build_prompt(force_reason=)` — passes the reason to `rca_trigger`.
- `role_prompt_rca.precondition(forced=)` — a forced prompt must not tell the analyst to stop because nothing is escalated.
- Schema: `trigger.rule` gains `same_family` and `forced`; `trigger.reason` with `if rule == forced then required`.

### Mocks
- none

### Tests
- `tests/test_review_rca.py::_rca(trigger=)` — lets a test write a record for another rule.
- `tests/test_review_rca.py::FAMILY_ROSTER`, `_family_round` — a second anthropic reviewer, and rounds failing a chosen id.
- `test_one_family_blocking_three_rounds_escalates_across_ids_and_models` — A1 rule across ids and models, its RCA prompt and a resolving `same_family` record.
- `test_a_family_approval_resets_its_count_and_families_count_apart` — the rule's two negative cases.
- `test_force_starts_an_rca_with_a_recorded_reason` — `--force`: prompt, precondition, party refusal, CLI, schema-required reason, resolution, and the nothing-to-analyse refusal.
- `test_force_needs_the_rca_role_and_a_reason` — the four argparse refusals.
- `test_an_active_escalation_wins_over_force` — force is ignored when escalated; a forced record cannot resolve a real escalation.
- `tests/test_planning_sheet_bootstrap.py::test_feature_sheet_template_points_to_the_acceptance_checklist` — A2 template pointer and the three checklist items in the doc.
