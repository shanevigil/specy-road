# Implementation summary — M3.5 `brainstorm-converge-checks`

Branch `feature/rm-brainstorm-converge-checks`, from `76433b5`, with `origin/WIP/improvements-0-3-1` merged at `26b4302`. That merge widened the touch zones with `specy_road/bundled_scripts/brainstorm_fields.py`, which A4 needs: it holds the list of allowed verification states that every session read is checked against.

## Acceptance

- **A1:** `brainstorm recommend --check` writes nothing. It does not switch the mode or write the prompt. It lists each idea with no cluster, no recommendation, or neither (`B3    no cluster and no recommendation  Three`), prints `N of M idea(s) not converged` with the `revise` command that fixes them, and exits 1. When every idea has both, it exits 0 and prints the next step. All ideas are checked, because the converge prompt asks for a verdict on every one.
- **A2:** `_print_rows` prints critic lines only when `--show-verdicts` is passed, the same rule as the recommendation column and `why:`. The `--show-verdicts` help now mentions critics.
- **A3:** `shortlist` defaults to ideas recommended `strong` (it used to take `strong` or `consider`). Named ids are still taken as given. `evidence` warns on stderr when more than 15 ideas are selected (`MAX_EVIDENCE_IDEAS`), whether by default or by name, and still writes the prompt.
- **A4:** `check_source` records `matched` when it finds the quote. `VERIFICATIONS` now lists `matched` instead of `retrieved`. `parse_extra` reads the old name `retrieved` as `matched` through `VERIFICATION_ALIASES`, so an older session is saved back as `matched`.
- **A5:** `promote` (including `--dry-run`) warns on stderr, before it writes anything, for each idea it is about to promote on a `strong` verdict that no `matched` source backs. That covers sources that are unverified, not found or blocked, and ideas with no sources at all. Each warning lists the source states and names the fix: `verify`, or `evidence <ID>` when there are no sources. It warns and does not refuse.

`docs/brainstorming.md` covers each of these in sections 2 through 5. `docs/agentic-sandbox-runbook.md` step 6 now uses `matched` for the release evidence/verify check (Sol round 2).

## Touch zones

Final list: brief zones plus `specy_road/bundled_scripts/brainstorm_fields.py`, plus `docs/agentic-sandbox-runbook.md` (added in roadmap `M3.json` and `sr/roadmap/registry.yaml` for review round 2). `brainstorm_cli_args_v2.py` changed only in its `evidence` help text.

`CHANGELOG.md` `## [Unreleased]` still has no entry for the verification rename; optional maintainer follow-up outside this leaf.

## Verification

- `pytest tests/test_brainstorm_v2.py tests/test_brainstorm_verify.py tests/test_brainstorm_cli.py -q`: pass (includes runbook regression test).
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- Full `pytest`: 2401 passed, 2 skipped, 1 failed — `test_file_limits_passes_on_repo` (pre-existing `worker_cli.py` / `worker_adapters.py` over cap; untouched).

## Review round 1

Sol blocked on two items. Grok approved.

- **Unreachable fallbacks, fixed.** `unverified_strong` and the `promote` warning read `s["verification"]`; promote-warning test covers `not-found`.
- **Runbook, deferred** until touch zone added (round 2).

## Review round 2

Sol blocked on runbook regression only (A1–A5 pass).

- **Fixed:** `docs/agentic-sandbox-runbook.md` step 6 — `retrieved` → `matched` in the share-count and hand-check instructions. Touch zones updated in `sr/roadmap/phases/M3.json` and `sr/roadmap/registry.yaml`. Test `test_agentic_runbook_evidence_step_uses_matched_verification_state` locks step 6.

## Added

- Helper `_check_converge` in `brainstorm_cli.py`: `recommend --check`'s report and exit code (A1).
- Helper `unverified_strong` in `brainstorm_promote.py`: strong pending ideas with no `matched` source (A5).
- Constant `MAX_EVIDENCE_IDEAS = 15` in `brainstorm_prompt_evidence.py` (A3).
- Constant `VERIFICATION_ALIASES` in `brainstorm_fields.py`: `retrieved` → `matched` on read (A4).
- Branch `if ns.check` in `cmd_recommend` (A1); `--check` on `recommend` in `brainstorm_cli_args.py` (A1).
- Branch `if len(ideas) > MAX_EVIDENCE_IDEAS` in `cmd_evidence` (A3).
- Loop over `unverified_strong` in `cmd_promote` (A5).
- Guard `if verdicts and i.critic` in `_print_rows` (A2).
- Mocks: none.
- Test `test_recommend_check_lists_every_idea_the_converge_pass_missed` (A1).
- Test `test_promote_warns_for_each_strong_idea_no_matched_source_backs` (A5).
- Extended `test_list_by_cluster_hides_verdicts_unless_asked` (A2).
- Extended `test_evidence_prompt_covers_the_shortlist_only` (A3).
- Extended `test_v1_session_files_still_read` (A4).
- Updated `test_check_source_states` and `test_verify_asks_before_fetching_and_records_states` (A4).
- Test `test_agentic_runbook_evidence_step_uses_matched_verification_state`: step 6 names `matched`, not `retrieved` (review round 2 regression).
