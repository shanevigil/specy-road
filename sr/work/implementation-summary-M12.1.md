# Implementation summary: M12.1 — fix-round budget and deferral of new-input-class findings

Base `6d080df2`; implementation commit `6a29081e`.

## What changed

- **A1 — budget.** `policy.max_fix_rounds` (integer ≥ 1, no default) in
  `specy_road/templates/project/schemas/orchestration.schema.json`, read with `policy.get(...)`.
  `review_deferral.fix_round_budget()` counts blocking rounds from `review_rounds()` (a round blocks when any
  record in it blocks). `review_cli._node_status()` adds `fix_round_budget` to the status dict **only when the
  key is set**, and sets state `fix_round_budget_spent` (exit 1) when the budget is spent and a counted review
  still blocks. It ranks after `executor_blocked` and ahead of `escalated`. `_render()` prints the next command:
  a forced RCA (`specy-road prompt <ID> --role rca --force --reason "fix-round budget spent" --model <…>`) while
  no valid RCA covers the latest round, then `specy-road review defer <ID> --rca <path>` when that RCA recommends
  `defer_findings`. For any other recommended action it points at `review list`.
- **A2 — schema.** `rca-record.schema.json`: `defer_findings` added to `recommended_action.type`. New
  `deferred_findings` array (minItems 1) whose items require finding, reviewer, commit, category (the four
  review-record finding keys), acceptance_id, input_class, follow_up_title and follow_up_acceptance. A root
  `allOf` if/then makes the array required for that type. `finding_disposition` items accept an optional
  `input_class`. `review_rca.ACTIONS`, `_skeleton()` and `rca_preamble()` now carry the shape and the rule.
- **A3 — apply.** `specy-road review defer <ID> --rca <file>` is a `review` subcommand registered from
  `review_cli.build_parser()`, so there is no new entrypoint. It refuses unless `sys.stdin.isatty()`, has no
  `--yes`, shows the items and asks `[y/N]`. It refuses the whole record when the record is invalid, is not
  `defer_findings`, was already applied, or any item has a `deferral_problems()` problem. It also refuses when
  git `user.name`/`user.email` are unset or the parent is milestone-locked. Otherwise it:
  1. adds one `Not Started` task per distinct follow-up title as a sibling of the leaf. It uses
     `next_child_id` + `new_node_key` + `next_sibling_order` + `append_node_to_chunk`, and the codename comes
     from `ensure_codename_for_new_node` inside that write.
  2. calls `decisions.add_entry(kind="decision")` then `close_entry(..., ledger_only=True)`. The answer names
     each finding, its input class, the follow-up id and the approver.
  3. writes `work/reviews/<ID>/DEFERRAL-<round>.yaml`, which records the decision id, approver, follow-up ids
     and each deferred `(reviewer, full commit, …)`.

  The gate's `evaluate_gate()` calls `review_deferral.apply_deferrals()` after counting. That moves a block to
  `ineligible` as `deferred by <decision id>` only when a marker names that reviewer and commit, and the
  decision is closed for that node in `decisions.yaml`.
- **A4 — refusals.** `review_deferral.deferral_problems(rounds, rcas, applied, item)` has three checks:
  - The normalised input class (lower-cased, whitespace collapsed) is already named in another RCA record's
    `deferred_findings` or `finding_disposition`, or in an applied marker. The problem names that file.
  - A `correctness` item is on an acceptance id an earlier round (by commit order) marked `pass`. The problem
    names the round number and its models.
  - (needed to find "earlier") The item's reviewer filed no blocking record at the item's commit.
- **A5 — docs.** `docs/orchestration-review.md` gains a `fix_round_budget_spent` state row, an exit-code entry
  and a "Fix-round budget and deferral" section. `docs/design-notes/review-loop-rca.md` gains a
  `defer_findings` table row, the record fields, and an "Adopted: the fix-round budget and deferral" section
  covering the budget, the input-class rule, applying it, and the audit trail RCA → decision → follow-up leaf.

## Touch zones (final list)

The brief's zones, plus two **new modules** that I had to create to stay under `specy-road file-limits`.
`review_gate.py` was already at 400 lines, `review_cli.py` at 387, and the rule pushed `review_rca.py` to 407.

- `specy_road/review_deferral.py` (new): the input-class rule `deferral_problems` and `normalise_input_class`,
  marker read/write, the gate hook `apply_deferrals`, and the budget `fix_round_budget`. The plan named
  `review_rca.py` for the rule, but it did not fit.
- `specy_road/bundled_scripts/review_defer.py` (new): the `review defer` subcommand.

To fit the cap, `review_gate.py` had one `GateResult(...)` constructor call compacted from 8 lines to 3. No
comments or docstrings were removed.

Not changed, worth a follow-up outside these zones: `docs/orchestration.md:78` lists policy keys
(`max_workers`, `escalate_*`) and could mention `max_fix_rounds`. `specy_road/templates/project/roadmap/orchestration.yaml`
needs no change, because the key stays unset by default.

## Verification

- `python -m pytest -n 4 -q tests/test_review_defer.py tests/test_review_rca.py tests/test_review_gate.py tests/test_review_cli.py tests/test_mark_implementation_reviewed_gate.py tests/test_decisions.py`
  passes. The wider review/decisions/schema set gave 784 passed, and the full `pytest -n 4` gave 3969 passed.
- `specy-road file-limits` is OK. `ruff check` on the touched files is clean.
  `scripts/check_test_private_imports.py` exits 0, and `scripts/check_clones.py` reports 0 new.
- Existing review/RCA tests pass unchanged.

## Added

### Helpers
- `review_deferral.normalise_input_class`: the single definition of "two input classes match".
- `review_deferral._round_of`: finds the round of an item's commit, with short or full SHA matched by prefix.
- `review_deferral.deferral_problems`: the never-deferrable rule (A4), pure.
- `review_deferral.marker_path` / `list_applied` / `write_marker`: the applied-deferral marker beside the RCA record.
- `review_deferral.deferred_by`: the closed decision that resolves a (reviewer, commit) block.
- `review_deferral.apply_deferrals`: the gate hook (A3).
- `review_deferral.fix_round_budget`: blocking-round count, the spent flag and the next command (A1).
- `review_defer._approver`: the approver from git config, named in the decision.
- `review_defer._add_follow_ups`: adds the follow-up leaf through the add-node write, one per distinct title.
- `review_defer._checked_record`: every refusal that happens before anything is written.
- `review_defer.cmd_review_defer` / `add_parser`: the human-only subcommand.

### Branches or guards
- `review_defer`: refuses without a TTY; this is the human-only rule.
- `review_defer`: refuses an invalid record, a record that is not `defer_findings`, or one already applied (its marker exists), so it cannot be applied twice.
- `review_defer`: refuses when git user.name/email are both unset, because the decision must name the approver.
- `review_defer`: refuses when the parent is milestone-locked; this is the same guard add-node applies.
- `review_defer`: aborts with nothing written when the confirmation is not `y`.
- `decisions.close_entry(ledger_only=...)`: closes a `decision` without a planning-sheet line, because `review defer` keeps its audit trail in the RCA record and marker. The default is unchanged.
- `review_cli._node_status`: adds the `fix_round_budget` key and state only when `max_fix_rounds` is set, so an unset budget leaves output unchanged.
- `review_cli._render`: prints the `fix_round_budget_spent` line with the next command.
- `deferral_problems`: refuses when the item's reviewer has no blocking record at its commit, because "earlier round" is undefined without it.

### Mocks
- `tests/test_review_defer.py::_Tty` plus a `builtins.input` monkeypatch (`human` fixture): simulates a person at a terminal answering `y`.
- `builtins.input` set to `pytest.fail` in the non-TTY test: proves it refuses before prompting.

### Tests (`tests/test_review_defer.py`)
- `test_schema_accepts_defer_findings_only_with_its_list`: A2 accept/reject, including the required item fields and the optional disposition `input_class`.
- `test_budget_unset_reports_nothing_new`: A1/A5, an unset budget adds no key and no line.
- `test_budget_spent_names_the_rca_then_the_defer_command`: A1, state, JSON, text and both next commands.
- `test_defer_refuses_a_run_without_a_terminal`: A3, non-TTY gives exit 1 with nothing written.
- `test_defer_applies_and_resolves_only_that_reviewers_block_at_that_commit`: A3, follow-up leaf, closed decision naming finding and approver, marker; another reviewer's block on the same commit and the same reviewer's later block still count.
- `test_an_open_or_missing_decision_does_not_resolve_the_block`: the gate needs the decision in `decisions.yaml`.
- `test_refuses_an_input_class_an_earlier_record_named`: A4(a), `"Empty  Final message"` vs `"empty final message"`, naming RCA-1.md, with nothing written.
- `test_refuses_a_correctness_finding_on_an_id_an_earlier_round_passed`: A4(b), naming round 1, with nothing written.
- `test_a_finding_on_an_earlier_commit_needs_a_block_there`: the no-blocking-record guard.
- `test_rca_prompt_states_the_deferral_rule_and_shape`: the analyst prompt carries the rule and the `deferred_findings` shape.

## Fix round 1

This round answers Sol's (gpt-6.1-sol) block of `6f5d36dc`, which listed required changes R1 to R5. It was preceded by a merge of `origin/WIP/improvements-0-3-1`. The fix commit is `e60f0ebc`. Each R-regression in `tests/test_review_defer.py` fails at `6f5d36dc` and passes now: 8 failed, and 1 positive control passed, when run in a throwaway worktree.

- **R1.** `review_deferral.uncovered()` lists what a blocking record names that the deferred items leave open: each failed acceptance id that no item names, and each findings category with more findings than items.
  - `review defer` refuses a record when `coverage_problems()` finds any such gap. A correctness finding on an id that passed earlier can never be deferred, so a block that contains one can never be resolved.
  - The gate removes a block only when the closed-decision items cover all of it.
  - Tests: `test_r1_a_partial_deferral_neither_applies_nor_hides_the_rest_of_the_block` (covers the CLI refusal and the gate with a hand-written marker), and `test_r1_a_deferral_covering_every_finding_of_the_block_resolves_it`.
- **R2.** `apply_deferrals()` reads markers first, and reads `decisions.yaml` only when a marker names that block. An unreadable ledger closes nothing, so the block keeps counting.
  - Test: `test_r2_no_marker_means_the_ledger_is_never_read`, with `entries: [` in the ledger, checked through `evaluate_gate` and `handoff status`.
- **R3.** Collision evidence is limited to RCA records with a smaller `trigger.round` and to markers with a smaller `round`. Markers now record `round`.
  - Test: `test_r3_a_later_record_is_not_earlier_evidence`.
- **R4.** `fix_round_budget(repo_root, config, loop, node_id)` returns `next` as a command only, shell-quoted, and puts the explanation in `next_why`. The commands are:
  - a forced RCA naming a concrete analyst: the first rostered non-human reviewer that is not a party;
  - `review defer` for `defer_findings`;
  - an executor prompt for the latest READY's agent for `continue_with_class_fix`, `restart_executor_fresh`, `fix_tests` and `fix_environment`;
  - a reviewer prompt for the latest blocking reviewer for `change_or_reprompt_reviewer`;
  - otherwise a complete `specy-road decisions add … --kind decision` that records the action for a human.
  - Test: `test_r4_a_non_defer_rca_names_a_runnable_step_for_its_action`, parametrised over three actions. The `decisions add` case is actually run.
- **R5.**
  - `_follow_up_problems()` checks every whitespace-collapsed title and acceptance line before anything is written.
  - The roadmap writes (follow-up leaves plus the decision) run inside a `TreeSnapshot` of `roadmap/` and `planning/`, which is restored on failure.
  - The marker is written last.
  - Tests: `test_r5_an_empty_second_title_fails_before_any_node_is_written` and `test_r5_a_failed_roadmap_write_is_rolled_back`.
- **Docs.** `docs/orchestration-review.md` and `docs/design-notes/review-loop-rca.md` now describe the coverage rule, the earlier-rounds-only rule, `next` and `next_why`, and the rollback.
- **Other changes.** My own round-0 assertion on the forced-RCA command was updated to the new concrete command, `--model sol`.

### Added (fix round 1)
- `review_deferral.uncovered`, `coverage_problems` (R1).
- `review_deferral._closed_decisions` (R2): a lazy, error-tolerant ledger read.
- `review_deferral._next_for` and `_EXECUTOR_ACTIONS` (R4).
- `review_defer._norm`, `_follow_up_problems` (R5).
- `review_defer._record`: the roadmap writes, wrapped in a snapshot (R5).
- Guards:
  - earlier-round filters on the RCA records and markers (R3);
  - snapshot restore on `ValueError`, `OSError` or `SystemExit` (R5);
  - when no analyst is found, the forced-RCA command falls back to `MODEL`, which `next_why` explains (R4).
- Mocks: `close_entry` monkeypatched to raise, used in the R5 rollback test.
- Tests: the eight R-tests named above, plus the helper `_two_fail_round`. `tests.test_review_cli._ready` is reused for a valid READY.
