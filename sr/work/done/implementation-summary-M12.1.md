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

## Fix round 2

This round answers Sol's block of `ee9f8fd6` (R1–R3), after a merge of `origin/WIP/improvements-0-3-1`. The fix commit is `07134dd7`. I made each fix by design, so the same class of finding can't reappear in another form:

- **R1: one coverage check.** `review_deferral.block_problems(rounds, idx, reviewer, items)` replaces the earlier category-count and acceptance-set checks (`uncovered`). `review defer` (through `coverage_problems`) and the gate (`apply_deferrals`) both use it, against the review history. The rules:
  - Each item binds one to one to a finding in the blocking record: same category, and same text. The item's `finding` may carry a `<round>/<reviewer>: ` prefix.
  - Every finding in the record must be bound, and every failed acceptance id must be named by an item.
  - No correctness item may name an acceptance id that an earlier round passed. This check moved here from `deferral_problems`, so a hand-written marker can't skip it.
  - A record doesn't link findings to criteria. So a block with any correctness finding that also fails an id an earlier round passed is never resolved.
  - Consequence: a block that lists no findings (an id fails, but the findings lists are empty) can't be deferred, because there is nothing to bind to. Earlier tests that deferred such blocks now file a real boundary finding.
- **R3: item rounds.** An item's round is the round of its blocking commit (`round_of`, now public). `deferral_problems(..., covers)` refuses an item whose round is later than the RCA's `trigger.round`. Earlier-class evidence is checked against the item's own round. RCA records count when their `trigger.round` is earlier; markers count when their item's `round` is earlier. Markers now store a `round` per item.
- **R2: one transaction.** `TreeSnapshot((roadmap, planning), (marker,))` covers the follow-up leaves, the decision entry and the marker write. Any `ValueError`, `OSError`, `SystemExit` or `YAMLError` restores all three.
- **Tests.** The regression tests now live in `tests/test_review_defer_rounds.py`, split out of `tests/test_review_defer.py` because of the 400-line file limit. All round-2 tests fail at `ee9f8fd6` and pass now:
  - `test_round2_r1_items_bind_to_original_findings` (two cases: crossed categories, and swapped acceptance ids).
  - `test_round2_r2_a_marker_write_failure_rolls_back_everything`: the review directory is readable but not writable.
  - `test_round2_r3_an_item_round_comes_from_its_blocking_commit`: an RCA-1 item citing a round-3 commit is refused; RCA-3 for the same item is refused, citing RCA-2.
  - `test_round2_probe_the_gate_applies_the_correctness_rule_to_a_hand_written_marker`: covers the one real defect my probes found.
- **Earlier tests changed.** Four existing tests now file a round with a real finding (`_two_fail_round`), as binding requires. Two assertions follow the new message text. The rollback test now asserts the rollback message, `could not apply …: ledger write failed`, because with an empty-findings fixture it was passing on the refusal instead.
- **Targeted run.** The 10 review, RCA, gate, CLI and decisions test files: 148 passed. `specy-road file-limits` is OK, ruff is clean, and `check_test_private_imports` exits 0.

### Fix round 2: probes

I attacked the check through the public `review defer` and `evaluate_gate`. Each probe ran in a throwaway repo; the probe script lives outside the repo.

- **Correctness item on an earlier-passing id, via a hand-written marker:** a real defect. The gate didn't apply this item-level rule, so it resolved a block that `review defer` would have refused. Fixed by moving the rule into `block_problems`; the regression test is named above.
- **Item citing a reviewer absent from that round:** safe. Refused ("no blocking record from sol at that commit").
- **Item citing a commit absent from the history:** safe. Refused.
- **Item citing a passing record** (the reviewer approved that commit): safe. Refused ("no blocking record").
- **Duplicate items, including the same commit cited by short and full SHA:** safe. Items are grouped by round, and binding is one to one, so the second copy binds nothing and the whole record is refused.
- **Item quoting only part of a finding's text:** safe. It doesn't bind ("is no unlisted boundary finding"), and the full finding stays undeferred.
- **Input class with mixed case, tabs, newlines and runs of spaces:** safe. `"\tCRLF\nLINE   Endings "` matches an earlier `"crlf line endings"` and is refused.
- **Marker whose RCA file was removed after apply:** safe by design. The gate still resolves the block, because the closed decision is the approval and the marker is re-checked against the history. Re-filing a new `RCA-2.md` is refused as "already applied", so nothing can be applied twice.
- **Reviewer re-files the same commit with an extra finding after a deferral:** safe. The gate re-binds against the latest record, and the block counts again.
- **Hand-written marker on a block with no findings, or a REVIEW file with no history copy:** safe. The block keeps counting.
- **Closed decision recorded for another node:** safe. The block keeps counting.
- **One block's findings split across two RCAs:** conservative. `review defer` checks each record's coverage on its own, so the second, partial record is refused. A block is deferred by one record or not at all.

### Added (fix round 2)
- `review_deferral.block_problems`: the single binding check (R1).
- `review_deferral._binds`, `_passed_before`, `_evidence`: helpers for that check (R1, R3).
- `review_deferral.round_of`: made public (it was `_round_of`); used by `review defer` to set each marker item's round.
- `review_deferral.coverage_problems`: now groups items by round and calls `block_problems`.
- `deferral_problems`: gains `covers` (R3); its correctness check moved into `block_problems`.
- `review_defer`: the marker write is inside the snapshot transaction (R2); marker items carry `round`.
- Removed: `review_deferral.uncovered`, replaced by `block_problems`.
- Tests:
  - `tests/test_review_defer_rounds.py`: the new module, holding the fix-round-1 and fix-round-2 regressions.
  - Helper `_forge_closed_deferral`, a hand-written closed decision plus marker for gate probes.
  - The four round-2 tests named above.

## Fix round 3

This round answers cursor-grok-4.6-high's block of `95e82986` (R1). It was preceded by a merge of `origin/WIP/improvements-0-3-1`; the fix commit is `2c0dd06e`.

- **R1.** `_next_for` now checks for the marker of the covering `defer_findings` record. When that record is applied, `next` is `None`, and `next_why` reads "`RCA-n.md` is applied (`DEFERRAL-n.yaml`); the blocks it did not defer are fixed in this leaf…".
  - `review_cli` reports `fix_round_budget_spent` only when there is a `next` to run. Otherwise the leaf shows its gate state: `blocked` while sonnet's block counts.
  - A new forced RCA is not named in that case. `prompt --role rca --force` refuses until another review round lands, because the applied RCA covers the latest round.
  - Pinned through `handoff status` (JSON and text) in `test_defer_applies_and_resolves_only_that_reviewers_block_at_that_commit`.
- **Docs.** `docs/orchestration-review.md` now lists every next step and says each runs as printed, or that none exists after the deferral is applied.
- **Tests.** Four tests fail at `95e82986` and pass now: the R1 pin, plus three `test_round3_*` tests in `tests/test_review_defer_rounds.py`. The targeted run is 151 passed. `specy-road file-limits` is OK, ruff is clean, and `check_test_private_imports` exits 0.
- **Earlier tests changed:**
  - `test_budget_spent_names_the_rca_then_the_defer_command` now files a round with a real finding. Before, the status named `review defer` for a record that command refuses (the same defect as R1).
  - `test_r4_a_non_defer_rca_names_a_runnable_step_for_its_action` now rosters `composer` as an executor. Its reviewer case now expects `review-packet`.
  - The R4 `decisions add` call now runs through this checkout's CLI, not the `specy-road` on PATH. That one runs the WIP checkout, whose schema lacks `max_fix_rounds`.

### Fix round 3: next-step audit

I checked each state `fix_round_budget` can report. `test_round3_every_next_step_runs_or_is_absent` runs every `next` command exactly as printed, through `python -c "from specy_road.cli import main"` on this checkout, and requires exit 0.

1. **No RCA covers the latest round.** `next`: `specy-road prompt <ID> --role rca --force --reason 'fix-round budget spent' --model <analyst>`. The analyst is the first rostered non-human reviewer that has neither implemented nor reviewed the leaf. The command runs and exits 0; a forced RCA is accepted whenever a round exists since the last analysis, which holds because no RCA covers the latest round. **Defect found and fixed:** with no such reviewer, the old command contained a literal `MODEL`, which cannot run. It now names a `decisions add` for a human (`test_round3_no_independent_analyst_names_a_human_decision`).
2. **A covering RCA that does not recommend deferral:**
   - `continue_with_class_fix`, `restart_executor_fresh`, `fix_tests`, `fix_environment`: `next` is an executor prompt for the latest READY's agent; it runs and exits 0. **Defect found and fixed:** an agent without the executor role in the roster was named, and `prompt` refuses it. Such an agent now gets the `decisions add` fallback (`test_round3_a_ready_agent_without_the_executor_role_is_not_named`).
   - `change_or_reprompt_reviewer`: `next` is the reviewer prompt for the latest blocking reviewer. **Defect found and fixed:** without `PACKET.md`, `prompt --role reviewer` refuses. `next` is now `specy-road review-packet <ID>` (it runs, exit 0), then the reviewer prompt (it runs, exit 0).
   - `amend_criterion`, `split_leaf`, `escalate_human`: `next` is a complete `specy-road decisions add <ID> --kind decision …`. It runs, exits 0, and records an open decision for a human.
3. **An unapplied defer RCA.** `next` is `specy-road review defer <ID> --rca <file>`, but only when `applicable_record()` (the same checks the command runs before writing) accepts the record. The command is human-only: it needs a TTY, which the test supplies, and then it applies with exit 0. **Defect found and fixed:** a record `review defer` would refuse was still named. It now gets the `decisions add` fallback, and `next_why` quotes the refusal.
4. **An applied defer RCA with counted blocks remaining** (R1). `next` is `None` and the state is `blocked` (exit 1); no command is known to fail. Progress comes from fixing the remaining blocks in this leaf. After the next review round, the budget rules apply again and name a new forced RCA if no record covers that round.
5. **An applied defer RCA with no blocks.** `next` is `None`, and the state is the gate's own (`in-review`/`waiting`/`approved`), never `fix_round_budget_spent`, because that state needs a counted block. Pinned in the audit test after the apply.

### Added (fix round 3)
- `review_deferral._human_decision`: the one `decisions add` builder, used by the RCA-action fallback and the no-analyst case.
- `review_defer.applicable_record`: renamed from `_checked_record` (now public), so the budget step pre-checks a deferral exactly as the command does.
- Guards in `_next_for` / `fix_round_budget`:
  - an applied marker gives no next step;
  - a refused deferral gives a human decision;
  - an agent without the executor role is not named;
  - a missing packet gives `review-packet` first;
  - no analyst gives a human decision.
- `review_cli`: the spent state requires a non-null `next`.
- Test helpers `_runs`, `_cli` and `_this_checkout`: run a printed command through this checkout's package.
- Tests:
  - `test_round3_every_next_step_runs_or_is_absent`
  - `test_round3_a_ready_agent_without_the_executor_role_is_not_named`
  - `test_round3_no_independent_analyst_names_a_human_decision`
  - The R1 status assertions in `test_defer_applies_and_resolves_only_that_reviewers_block_at_that_commit`.

## Fix round 4: root-cause design

This round answers Sol's block of `780e53de` (R1–R4) and follows the coordinator's root-cause design. It was preceded by a merge of `origin/WIP/improvements-0-3-1`. The fix commit is `76ad8117`.

**New module, to add to the zones: `specy_road/review_next_step.py`.** It holds the next-step state machine that M14.9 and M14.10 will extend.

### Cause 1: the rules lived in two places. Now there is one function.

`review_deferral.qualify_deferral(items, evidence) -> list[problem]` holds every deferral rule:

- **Round:** an item's round comes from its blocking commit. That round must hold a blocking record from the item's reviewer, and must be no later than the round the source record covers.
- **New input class:** compared normalised, against evidence from earlier rounds only. The source record and its own marker are excluded.
- **Binding:** each item binds one to one to a finding of that record, matching category and text.
- **Coverage:** every finding is bound, and every failed acceptance id is named by an item.
- **Protected criteria:** a correctness item may not name an id that passed in an earlier round. A block that has any correctness finding and also fails such an id is never resolved.

The one helper, `_block_problems`, is called only from this function. These functions are gone: `deferral_problems`, `coverage_problems`, `block_problems` and `_evidence`.

Both callers build their evidence with `deferral_evidence(repo_root, node_id, source, covers)`. It draws on `loop_state`, which supplies the rounds and the RCAs validated against the schema and the history, and on the valid markers. The two callers are:
- `review defer` (`applicable_record`), which calls it before writing anything.
- The gate (`apply_deferrals`), which calls it on every marker naming a block, each time it evaluates. It resolves the block only when the marker's decision is closed **and** the marker's items still qualify.

The marker is a cache, not an authority. A block must be fully deferred by one marker.

**Agreement table** (`tests/test_review_deferral_agreement.py::test_review_defer_and_the_gate_agree`): the same items, through `review defer` in one repository and through a closed decision plus a hand-written marker and `evaluate_gate` in a twin repository.

| Case | `review defer` | gate | Red at `780e53de` |
|---|---|---|---|
| eligible (boundary/A1 binds its finding) | accepts | resolves | — |
| earlier_class (RCA-1 named `crlf  LINE endings`) — **R1** | refuses | keeps block | yes (old gate resolved it) |
| later_round (an RCA-1 item cites a round-2 commit) | refuses | keeps block | yes (old gate resolved it) |
| crossed_category | refuses | keeps block | no |
| unbound_text | refuses | keeps block | no |
| uncovered_failed_id (item names A2, A1 fails) | refuses | keeps block | no |
| absent_reviewer | refuses | keeps block | no |
| duplicate (short + full SHA) | refuses | keeps block | no |
| protected_block (correctness finding, A2 passed earlier) | refuses | keeps block | no |
| correctness_item (correctness item on earlier-passing A2) | refuses | keeps block | no |

`later_round` shows a second drift that no review had reported: the old gate never checked the covered round.

### Cause 2: markers were untrusted input. Now they are checked at the boundary.

`review_deferral.MARKER_SCHEMA` (JSON Schema, validated with `jsonschema`) is checked in `load_markers`, the only reader. It returns `(valid markers, one problem line per bad file)` and never raises on a marker's content. `LoopState.problems()` carries those lines, so `handoff status` (text and `--json`) and `review list` show one line naming the file, and a bad marker resolves nothing.

`test_a_malformed_marker_resolves_nothing_and_status_stays_usable` runs with `max_fix_rounds` unset. It covers six inputs:
- R4's exact `deferred: [incomplete write]`;
- non-mapping YAML;
- missing keys;
- wrong types;
- unparsable YAML;
- bad item fields.

All six fail at `780e53de`: either a traceback or no problem line.

### Cause 3: the next step was ad hoc. Now it is a state machine.

`review_next_step.facts()` collects a frozen `Facts`:
- budget and blocking rounds;
- whether a counted review blocks;
- the covering RCA as none, non_defer, defer_unapplied or defer_applied, plus `review defer`'s refusal reason;
- an available independent analyst;
- an available rostered executor that handed off;
- an available blocking reviewer;
- whether the packet exists.

"Available" uses `orchestrate_plan.is_available`, the rule `prompt` applies (R2). `STATES` is an ordered table; `classify()` takes the first row whose `when` holds, and its `step` yields one `Step(kind, next, why)`.

`fix_round_budget()` returns `None` only for `budget_unset`, so status is unchanged when no budget is set. `spent` means the budget is spent and any counted review blocks. `review_cli` reports `fix_round_budget_spent` exactly when `spent` is true, so it stays true after a partial deferral (R3).

**State table**: every row has a test in `tests/test_review_next_step.py` through `handoff status` `--json` and text. The test runs the printed command and requires it not to exit 1. `test_every_state_row_is_tested` fails if a row has no test.

| Row (first match wins) | When | Step | `next` (verified to run) |
|---|---|---|---|
| budget_unset | `max_fix_rounds` unset | none | — (no `fix_round_budget` key) |
| within_budget | blocking rounds < budget | none | — |
| spent_no_blocks | spent, no counted block | none | — (the gate's own state) |
| spent_no_rca | no covering RCA, analyst available | command | `prompt --role rca --force --reason … --model <analyst>` |
| spent_no_rca_no_analyst | no covering RCA, no available analyst (R2) | blocked | `decisions add …` |
| spent_defer_unapplied | covering defer RCA, `review defer` accepts it | command | `review defer <ID> --rca <file>` (run as a person, on a TTY) |
| spent_defer_refused | covering defer RCA it would refuse | blocked | `decisions add …` (`next_why` quotes the refusal) |
| spent_defer_applied | applied defer, blocks remain, executor available (R3) | command | `prompt --role executor --model <executor>` |
| spent_defer_applied_no_executor | applied defer, blocks remain, no executor (R3) | blocked | `decisions add …` |
| spent_rca_executor | executor action, executor available | command | `prompt --role executor --model <executor>` |
| spent_rca_packet | reviewer re-prompt, no PACKET.md | command | `review-packet <ID>` |
| spent_rca_reviewer | reviewer re-prompt, available blocking reviewer | command | `prompt --role reviewer --model <reviewer>` |
| spent_rca_human | any other covering RCA | blocked | `decisions add …` |

The defer rows never re-name `review defer` after an apply. M14.9 and M14.10 add rows by inserting a `State` before the row they refine; the coverage test will then ask for their test.

### Earlier tests changed
- `test_defer_applies_and_resolves_only_that_reviewers_block_at_that_commit` used to pin R3's wrong state, `blocked` with a null next step. It now pins `fix_round_budget_spent` / `spent_defer_applied_no_executor` / `blocked`.
- Three message assertions follow the new wording:
  - "the record covers";
  - "no available rostered reviewer";
  - the `decisions add` summary prefix.

### Verification
- The targeted run is 180 passed over 12 files: `test_review_next_step`, `test_review_deferral_agreement`, `test_review_defer`, `test_review_defer_rounds`, `test_review_rca`, `test_review_gate`, `test_review_cli`, `test_mark_implementation_reviewed_gate`, `test_decisions`, `test_decision_preferences`, `test_review_eligible` and `test_strong_review`.
- `specy-road file-limits` is OK, ruff is clean, and `check_test_private_imports` exits 0.

### Added (fix round 4)
- `review_deferral`:
  - `qualify_deferral`, `_block_problems`, `_earlier_classes`;
  - `Evidence`, `deferral_evidence`;
  - `Marker`, `MARKER_SCHEMA`, `_marker_validator`, `load_markers`, `CATEGORIES`.
- Moved out of `review_deferral` into `review_next_step`: `fix_round_budget` and all next-step logic.
- `review_next_step` (new module): `Facts`, `Step`, `State`, `STATES`, `classify`, `facts`, `fix_round_budget`, `_human`, `_executor`, `_available`, `_rca_why`, `_none`.
- `review_rca.LoopState.marker_problems`: bad-marker lines in the loop's problems.
- `review_cli`: the spent rule is `budget["spent"]`. It calls `fix_round_budget(..., bool(gate.blocks))` from `review_next_step`.
- `review_defer.applicable_record`: now `qualify_deferral` plus the follow-up field check.
- Tests:
  - `tests/test_review_deferral_agreement.py`: agreement table (10 cases) and malformed markers (6 cases);
  - `tests/test_review_next_step.py`: one test per row, plus the row-coverage test.
