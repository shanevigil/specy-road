# Implementation summary — M3.5 `brainstorm-converge-checks`

Branch `feature/rm-brainstorm-converge-checks`, from `76433b5`, with `origin/WIP/improvements-0-3-1` merged at `26b4302`. That merge widened the touch zones with `specy_road/bundled_scripts/brainstorm_fields.py`, which A4 needs: it holds the list of allowed verification states that every session read is checked against.

## Acceptance

- **A1:** `brainstorm recommend --check` writes nothing. It does not switch the mode or write the prompt. It lists each idea with no cluster, no recommendation, or neither (`B3    no cluster and no recommendation  Three`), prints `N of M idea(s) not converged` with the `revise` command that fixes them, and exits 1. When every idea has both, it exits 0 and prints the next step. All ideas are checked, because the converge prompt asks for a verdict on every one.
- **A2:** `_print_rows` prints critic lines only when `--show-verdicts` is passed, the same rule as the recommendation column and `why:`. The `--show-verdicts` help now mentions critics.
- **A3:** `shortlist` defaults to ideas recommended `strong` (it used to take `strong` or `consider`). Named ids are still taken as given. `evidence` warns on stderr when more than 15 ideas are selected (`MAX_EVIDENCE_IDEAS`), whether by default or by name, and still writes the prompt.
- **A4:** `check_source` records `matched` when it finds the quote. `VERIFICATIONS` now lists `matched` instead of `retrieved`. `parse_extra` reads the old name `retrieved` as `matched` through `VERIFICATION_ALIASES`, so an older session is saved back as `matched`.
- **A5:** `promote` (including `--dry-run`) warns on stderr, before it writes anything, for each idea it is about to promote on a `strong` verdict that no `matched` source backs. That covers sources that are unverified, not found or blocked, and ideas with no sources at all. Each warning lists the source states and names the fix: `verify`, or `evidence <ID>` when there are no sources. It warns and does not refuse.

`docs/brainstorming.md` covers each of these in sections 2 through 5.

## Touch zones

The final list is the brief's zones plus `specy_road/bundled_scripts/brainstorm_fields.py`. `brainstorm_cli_args_v2.py` changed only in its `evidence` help text.

Two files outside the zones still use the old wording. I left them unedited because neither is needed for the criteria:

- **`docs/agentic-sandbox-runbook.md`**, step 6, asks the tester to count `retrieved` sources and hand-check five `retrieved` quotes. After this change it should say `matched`.
- **`CHANGELOG.md`**, `## [Unreleased]`, has no entry for these changes. The rename of a stored state, together with the read alias, is worth a line there.

## Verification

- `pytest`: 2401 passed, 2 skipped, 1 failed. The failure is `tests/test_validate_file_limits.py::test_file_limits_passes_on_repo`, because `specy_road/bundled_scripts/worker_cli.py` (408 lines) and `specy_road/worker_adapters.py` (430 lines) are over the 400-line cap. Both are untouched here and are the same size at the base `76433b5`.
- `specy-road file-limits` reports the same two files and nothing else. `brainstorm_cli.py` is 365 lines.
- `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`: exit 0.
- `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`: OK.
- `ruff check specy_road tests scripts`: all checks passed.
- `scripts/check_test_private_imports.py`: 0 new.
- `scripts/check_clones.py` could not run, because `pylint` is not installed in this environment.

## Added

- Helper `_check_converge` in `brainstorm_cli.py`: `recommend --check`'s report and exit code (A1). It is a private function beside `cmd_recommend`, not a new module.
- Helper `unverified_strong` in `brainstorm_promote.py`: the ideas `promote` is about to land on a `strong` verdict with no `matched` source (A5). It reuses `pending_ideas`.
- Constant `MAX_EVIDENCE_IDEAS = 15` in `brainstorm_prompt_evidence.py`: the evidence warning threshold (A3).
- Constant `VERIFICATION_ALIASES` in `brainstorm_fields.py`: maps the old state name `retrieved` to `matched` when a session is read (A4).
- Branch `if ns.check` in `cmd_recommend`: `--check` inspects the session and writes nothing (A1).
- Option `--check` on `recommend` in `brainstorm_cli_args.py` (A1).
- Branch `if len(ideas) > MAX_EVIDENCE_IDEAS` in `cmd_evidence`: the warning (A3).
- Loop over `unverified_strong` in `cmd_promote`, with the `verify` or `evidence <ID>` fix: one warning per idea (A5).
- Guard changed: `if verdicts and i.critic` in `_print_rows`. Critics are gated like the verdicts (A2).
- Mocks: none.
- Test `test_recommend_check_lists_every_idea_the_converge_pass_missed` (`tests/test_brainstorm_v2.py`): the exit codes, one line per gap, and that `--check` writes neither the mode nor the prompt (A1).
- Test `test_promote_warns_for_each_strong_idea_no_matched_source_backs` (`tests/test_brainstorm_v2.py`): a warning for a strong idea with unverified sources and for one with no sources; none for a strong idea with a `matched` source or for a `consider` (A5).
- Extended `test_list_by_cluster_hides_verdicts_unless_asked`: critic text is now absent without `--show-verdicts` and present with it (A2). This assertion was inverted to match the new behaviour that A2 requires.
- Extended `test_evidence_prompt_covers_the_shortlist_only`: a `consider` idea is left out of the default selection; 15 named ideas do not warn and 16 do (A3).
- Extended `test_v1_session_files_still_read`: a source saved as `retrieved` reads as `matched` and is written back as `matched` (A4).
- Updated `test_check_source_states` and `test_verify_asks_before_fetching_and_records_states`: the expected state is now `matched` instead of `retrieved` (A4).
