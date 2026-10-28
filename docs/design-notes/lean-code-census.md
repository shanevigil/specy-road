# Lean-code census: are 2,092 tests specification or sediment?

**Status:** measurement note (2026-10-27), base `20430b9`, run on the `chore/lean-census` worktree. Read-only on source and tests; every script is under [`scripts/census/`](../../scripts/census/). Motivated by the two October 2026 lean-testing research reports; this runs the one-day subset of their closing experiments.

## Summary

- Suite: **2,092 collected tests** (1,752 test functions, the rest parametrised), **32,720 test lines** against **39,754 source lines**; ratio **0.82**. Full run **8:00 wall** in-process, **9:30** with subprocess tracing; everything passes.
- Line coverage of `specy_road/`: **82 % in-process, 86 % with subprocesses traced**. 220 collected tests (CLI-via-subprocess) leave no in-process trace and are invisible to per-test overlap figures.
- **Private-name coupling:** 199 of 1,752 test functions (**11 %**) read a `_`-name, patch a `_`-target or assert on call records; **none** assert on log text. Hand sample of 30 flagged tests: **21 legitimately pinned, 8 implementation-pinned, 1 false positive**. Extrapolated, about **3 % of the suite** would break on a behaviour-preserving restructure.
- **Review-round files:** 254 tests; **191 (75 %)** have >= 95 % line overlap with tests outside those files, **89** cover no line of their own, **58** of those have a single non-round twin covering everything they touch. 165 still cover at least one unique line.
- **Whole suite:** **1,316 of 1,874 traced tests (70 %)** cover no line that some other test does not also cover. This is a consolidation signal, not a deletion list: the guard and search-provider files are parametrised input tables that share one classifier.
- **Defensive lines:** 1,702 `except`/`raise`/early-`return`/`is None`/`isinstance` lines; **705 (41 %)** never executed. Hand check of 30: **26 reachable-untested, 3 uncertain, 1 unreachable**. The untested guards are mostly input validation on user, file, HTTP and git boundaries, not impossible states.
- **Duplication:** pylint finds **12 clone pairs** of 7-17 lines, nine of them argparse or YAML boilerplate. The 0.3 worker modules (all new since `v0.2.3`) carry **six copies of `_now()`**, a duplicated schema validator, a duplicated `_target()` and a re-exported `_write_atomic`.
- **Size by era:** pre-0.3 (367 commits, Apr-Oct 2026) added 37.4k source / 27.4k test lines and 1,386 tests; the 0.3 line (68 commits, two days) added 8.6k / 6.5k and 366 tests. Test-to-source ratio of added lines **0.73 before, 0.76 after**; test deletions stay at 3.5 % of test additions in both eras.
- **Mutation census (eight modules, 2,604 of 3,186 mutants before the 2 h cap):** **74 %** killed; survivors cluster in the three harness output parsers (143 of 651). Not comparable with CI's run, so it seeds no baseline (section 5).

**Too many tests?** The count is not the problem; the *shape* is. 70 % of tests add no unique line and the review-round files duplicate line coverage almost completely, but line overlap does not prove value overlap: a round test that feeds the same classifier a new input shape can still be the only test that kills a mutant. The honest verdict is "many tests, heavily overlapping by lines, sorted into files by when they were written rather than by what they specify". Folding the 58 strict twins and merging the parametrised round tables into their home files would remove the sediment without losing specification.

**Tests pinned to internals?** Modest. 11 % touch a private name and most of those pin a parser, a message builder or a boundary fake, which is the behaviour. The real implementation-pinning sits in a few files (`test_grind_session_in_flight`, `test_abort_task_pickup`, `test_claim_traps`, `test_roadmap_gui_remote`) that patch four or five collaborators to reach one public result, and in call-record assertions on faked `git_run`. Around 3 % of the suite; worth fixing where touched, not worth a campaign.

**Unreachable defensive code?** Not what the data shows. 41 % of guard lines are unexecuted, but 26 of 30 sampled have a concrete trigger outside the test suite (bad roadmap JSON, corrupt settings file, `git add` failing, DNS failure). Only one is excluded by a repository invariant. The problem is the opposite of the hypothesis: boundary validation that nothing exercises.

**Duplication?** Low in the pre-0.3 code and concentrated in the two-day 0.3 worker line: the same timestamp helper six times, the same schema validator twice, argparse blocks copied between commands. Small, mechanical, and a direct symptom of generating modules one at a time without a reuse pass.

## 1. Private-name coupling census

`scripts/census/private_coupling.py` AST-scans every `tests/test_*.py`. Per test function: `private` = reads `_x` on a `specy_road` module alias or uses a `_x` imported from one; `patch` = `monkeypatch.setattr` on a `_`-target; `callrec` = `call_count`/`assert_called*`/`mock_calls` or an assertion on a locally recorded call list; `log` = `caplog` in an assertion; `via helper` = calls a same-file helper that is itself flagged. Dunder names are excluded.

| file | tests | private | patch | callrec | log | any direct | share | via helper |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| test_do_next_queue.py | 20 | 18 | 0 | 0 | 0 | 18 | 90% | 0 |
| test_review_node.py | 18 | 11 | 8 | 3 | 0 | 15 | 83% | 0 |
| test_finish_task_commands.py | 9 | 8 | 1 | 1 | 0 | 9 | 100% | 0 |
| test_registry_prune.py | 9 | 9 | 0 | 1 | 0 | 9 | 100% | 0 |
| test_registry_remote_overlay_sync.py | 11 | 6 | 0 | 5 | 0 | 9 | 82% | 0 |
| test_roadmap_gui_remote.py | 14 | 7 | 0 | 4 | 0 | 9 | 64% | 0 |
| test_grind_session_implement_resilience.py | 14 | 0 | 0 | 8 | 0 | 8 | 57% | 0 |
| test_abort_task_pickup.py | 7 | 2 | 5 | 2 | 0 | 7 | 100% | 0 |
| test_grind_session_implement.py | 18 | 2 | 1 | 5 | 0 | 7 | 39% | 9 |
| test_finish_bookkeeping_wiring.py | 6 | 6 | 0 | 4 | 0 | 6 | 100% | 6 |
| test_grind_session_in_flight.py | 15 | 1 | 4 | 2 | 0 | 6 | 40% | 0 |
| test_do_next_task_pickup.py | 6 | 0 | 5 | 4 | 0 | 5 | 83% | 0 |
| test_do_next_virtual_pickup.py | 6 | 5 | 0 | 0 | 0 | 5 | 83% | 0 |
| test_review_round6_evidence.py | 14 | 5 | 0 | 0 | 0 | 5 | 36% | 0 |
| test_review_round6_runner.py | 11 | 2 | 2 | 1 | 0 | 5 | 45% | 0 |
| (other 100 files) | 1,574 | 45 | 23 | 21 | 0 | 76 | 5% | 11 |
| **total** | **1,752** | **127** | **49** | **57** | **0** | **199** | **11%** | **26** |

Mocking style is `monkeypatch` on module attributes; `unittest.mock` appears in two files. `caplog` is never asserted on; stderr text is (via `capsys`), which this census counts as behaviour.

**Hand classification, stratified sample of 30** (14 private, 7 patch, 6 callrec, 3 via-helper; seed 20430). "legit" = the private name is the behaviour (parser, message builder, boundary fake); "impl" = would break on a behaviour-preserving rename or restructure.

| # | test | verdict | why |
|---|---|---|---|
| 1 | test_review_round6_evidence::test_uncommitted_rename_is_seen_by_reconcile | legit | `_changed_since` is the git-status parser |
| 2 | test_roadmap_gui_remote::test_github_pr_detail_rejected_closed_unmerged | impl | pins the two-call `requests.get` order via `side_effect` |
| 3 | test_do_next_finished_unmerged::test_drop_finished_unmerged_filters_and_reports | legit | pure filter helper plus stderr reason |
| 4 | test_do_next_queue::test_exit_no_actionable_leaves_names_the_integration_branch | legit | diagnostic text is the user contract |
| 5 | test_review_node::test_azure_settings_prefers_specy_over_azure_aliases | legit | env-precedence resolver |
| 6 | test_worker_review_round2::test_cgnat_addresses_are_off_host | legit | pure predicate; `getaddrinfo` is the boundary |
| 7 | test_agents_md_block::test_force_rewrites_only_the_block | false positive | `__version__` import; scanner fixed |
| 8 | test_do_next_queue::test_exit_no_actionable_leaves_has_deterministic_diagnostics | legit | same helper as 4 and 9 (merge the three) |
| 9 | test_do_next_queue::test_exit_no_actionable_leaves_hint_without_a_known_branch | legit | see 8 |
| 10 | test_mark_implementation_reviewed_gate::test_finish_refuses_work_committed_after_approval | legit | `_impl_review_or_exit` is the gate |
| 11 | test_roadmap_gui_remote::test_github_pr_detail_merged_from_state_all | impl | as 2 |
| 12 | test_grind_session_in_flight::test_human_in_flight_branch_complete_mentions_merge_not_abort | legit | text builder |
| 13 | test_registry_remote_overlay_sync::test_maybe_auto_git_fetch_records_timeout_status | impl | clears the private `_LAST_FETCH_MONO` cache global |
| 14 | test_review_node::test_normalize_review_strips_markdown_fence | legit | parser |
| 15 | test_grind_session_in_flight::test_loop_without_the_flag_stops_with_exit_six | impl | four internal seams patched to reach one public result |
| 16 | test_grind_session_in_flight::test_loop_resumes_instead_of_exiting_six | impl | as 15 plus a recorded CLI call list |
| 17 | test_gui_archive_routes::test_listing_survives_a_failing_candidate_scan | legit | fault injection at the route's import seam; asserts HTTP |
| 18 | test_review_round4_sol_b::test_the_byte_cap_blocks_rather_than_truncates | legit (borderline) | three private fakes, all at the socket boundary |
| 19 | test_abort_task_pickup::test_abort_allows_ahead_with_force | impl | four patched collaborators plus git-subcommand list |
| 20 | test_review_node::test_shared_catalog_max_files_footer | legit | overrides a cap constant to reach the footer |
| 21 | test_claim_traps::test_local_pickup_skips_sync_and_push | impl | patches `_push_integration_branch` with `raising=False`, so `pushed == []` cannot fail if the name moves |
| 22 | test_registry_prune::test_removal_drops_only_named_rows_and_pushes | impl | asserts `("push","origin","dev") in calls` on a faked `git_run` |
| 23 | test_registry_remote_overlay_sync::test_maybe_auto_integration_ff_skips_without_env_or_settings | legit | "no git invoked" is the behaviour |
| 24 | test_grind_session_implement::test_a_successful_run_never_waits | legit | shell runner is the boundary |
| 25 | test_runtime_paths::test_a_recorded_root_may_not_escape_its_checkout | legit | public function; helper only writes a manifest |
| 26 | test_grind_session_implement::test_a_timed_limit_is_waited_out_and_the_session_resumed | legit | the resumed command line is the harness contract |
| 27 | test_roadmap_gui_remote::test_test_git_remote_github_ok | legit | HTTP boundary plus URL |
| 28 | test_grind_session_step::test_finish_refuses_pr_mode | legit | harness fake records CLI calls |
| 29 | test_grind_session_step::test_finish_without_until_match_does_not_stop | legit | public event stream |
| 30 | test_grind_session_implement::test_a_spend_limit_stops_immediately | legit | exit code and stderr |

**Result: 21 legit, 8 impl, 1 false positive.** 8/29 = 28 % of flagged tests, i.e. roughly 55 tests or 3 % of the suite, are implementation-pinned.

## 2. Review-round overlap

One run of `pytest --cov=specy_road --cov-context=test`; `scripts/census/coverage_overlap.py round` reads `contexts_by_lineno`. For each test in a review-round file: the share of its (file, line) set also covered by at least one test outside those files. Subprocess-only tests are absent (see Not measured).

| round file | tests | median overlap | >= 95 % (fold candidates) | zero unique lines | ...with one twin at 100 % | keep (unique lines) |
|---|---:|---:|---:|---:|---:|---:|
| test_review_round2_routing.py | 10 | 100.0% | 9 | 6 | 3 | 4 |
| test_review_round4_sol.py | 27 | 99.5% | 24 | 8 | 5 | 19 |
| test_review_round4_sol_b.py | 6 | 98.9% | 4 | 3 | 1 | 3 |
| test_review_round5.py | 24 | 99.7% | 18 | 11 | 5 | 13 |
| test_review_round6_brainstorm.py | 14 | 99.8% | 9 | 5 | 4 | 9 |
| test_review_round6_docs.py | 7 | 100.0% | 7 | 5 | 3 | 2 |
| test_review_round6_evidence.py | 14 | 99.0% | 10 | 2 | 1 | 12 |
| test_review_round6_guard.py | 67 | 96.8% | 44 | 12 | 10 | 55 |
| test_review_round6_ops.py | 26 | 99.2% | 17 | 9 | 6 | 17 |
| test_review_round6_policy.py | 12 | 93.2% | 5 | 2 | 1 | 10 |
| test_review_round6_runner.py | 11 | 99.0% | 9 | 3 | 3 | 8 |
| test_worker_faults.py | 1 | 99.6% | 1 | 0 | 0 | 1 |
| test_worker_review_round1.py | 10 | 100.0% | 9 | 7 | 5 | 3 |
| test_worker_review_round2.py | 25 | 100.0% | 25 | 16 | 11 | 9 |
| **total** | **254** | | **191** | **89** | **58** | **165** |

The twins cluster: `test_tool_call_guard.py` is the best twin for 70 candidates, `test_worker_cli.py` for 50, `test_worker_adapters.py` for 13, `test_specyrd_skills.py` for 12. Strict fold candidates (zero unique lines, one non-round test covers 100 % of them), up to four per file; the full 191-row list comes from the script:

| round test | non-round twin covering 100 % of its lines |
|---|---|
| `test_review_round2_routing::test_a_users_own_skill_directory_is_reported_skipped` | `test_specyrd_skills::test_init_without_force_keeps_a_users_skill_directory` |
| `test_review_round2_routing::test_refresh_stubs_does_not_create_claude_md` | `test_agents_md_block::test_refresh_stubs_reapplies_the_block` |
| `test_review_round2_routing::test_the_commands_hint_is_only_for_old_harness_stubs` | `test_specyrd_skills::test_refresh_migrates_a_pre_skills_install_and_names_the_old_stubs` |
| `test_review_round4_sol::test_opaque_shapes_and_bare_commits_are_refused[git commit -m x]` | `test_tool_call_guard::test_destructive_commands_are_classified[...]` |
| `test_review_round4_sol::test_opaque_shapes_without_git_pass[...]` (3 params) | `test_tool_call_guard::test_ordinary_commands_pass[...]` |
| `test_review_round4_sol_b::test_search_results_are_delimited_as_untrusted` | `test_brainstorm_chat::test_a_failing_search_becomes_text_the_model_can_read` |
| `test_review_round5::test_adopt_is_one_transaction` | `test_worker_cli::test_adopt_open_list_status_and_handoff_status` |
| `test_review_round5::test_event_sequences_survive_a_record_that_lags_the_log` | `test_worker_cli::test_adopt_open_list_status_and_handoff_status` |
| `test_review_round5::test_more_wrapper_shapes_are_classified[timeout 10 git stash]` | `test_tool_call_guard::test_destructive_commands_are_classified[command git stash]` |
| `test_review_round5::test_round_one_does_not_point_at_the_roadmap_digest` | `test_brainstorm_v2::test_panel_writes_independent_shards` |
| `test_review_round6_brainstorm::test_gui_payload_carries_the_planned_round_count` | `test_gui_app_brainstorm::test_promote_writes_nodes_and_reports_them` |
| `test_review_round6_brainstorm::test_later_rounds_and_shards_carry_the_allow_list_too` | `test_brainstorm_v2::test_panel_writes_independent_shards` |
| `test_review_round6_brainstorm::test_round_one_prompt_carries_the_write_allow_list` | `test_brainstorm_v2::test_promote_carries_evidence_hypothesis_and_alternatives_into_the_sheet` |
| `test_review_round6_brainstorm::test_start_help_no_longer_claims_research` | `test_brainstorm_v2::test_promote_carries_evidence_hypothesis_and_alternatives_into_the_sheet` |
| `test_review_round6_docs::test_force_rewrites_what_the_manifest_owns` | `test_specyrd_skills::test_a_wrong_link_is_repaired` |
| `test_review_round6_docs::test_refresh_links_a_canonical_skill_another_recorded_pack_owns` | `test_specyrd_skills::test_a_wrong_link_is_repaired` |
| `test_review_round6_docs::test_refresh_with_two_packs_keeps_the_shared_skills_for_the_second_pack` | `test_refresh_stubs::test_a_second_run_changes_nothing` |
| `test_review_round6_evidence::test_notes_digest_normalises_line_endings_and_trailing_whitespace` | `test_review_signing::test_human_approval_needs_a_key_under_signed_reviews` |
| `test_review_round6_guard::test_env_config_check_leaves_ordinary_commands_alone[git commit ...]` | `test_tool_call_guard::test_ordinary_commands_pass[git commit -m 'x' src/a.py]` |
| `test_review_round6_guard::test_every_harness_form_denies_env_alias_with_a_live_peer[*]` (3 params) | `test_tool_call_guard::test_cli_command_mode_exit_codes` |
| `test_review_round6_ops::test_delegate_in_the_same_checkout_writes_the_missing_brief` | `test_worker_cli::test_sync_delta_and_ack` |
| `test_review_round6_ops::test_delegate_runs_preflight_outside_the_workers_lock` | `test_worker_cli::test_handoff_reclaim_round_trip_and_hook_evidence` |
| `test_review_round6_ops::test_whole_word_placeholders_are_accepted[*]` (2 params) | `test_worker_cli::test_sync_delta_and_ack` |
| `test_review_round6_policy::test_the_committed_profile_is_used_when_the_tree_matches_or_lacks_it` | `test_models_and_prompt::test_prompt_cli_channel_refuses_without_placeholder` |
| `test_review_round6_runner::test_a_huge_stdin_prompt_travels_in_a_0600_file_not_argv` | `test_worker_cli::test_sync_delta_and_ack` |
| `test_review_round6_runner::test_parsed_output_is_worker_suggestion_and_lifecycle_stays_system` | `test_worker_adapters::test_run_records_session_id_events_and_a_clean_exit` |
| `test_review_round6_runner::test_the_checkpoint_is_by_content_not_mtime` | `test_worker_adapters::test_run_marks_completed_when_ready_exists_and_failed_on_nonzero_exit` |
| `test_worker_review_round1::test_a_flag_set_while_the_wrapper_streams_survives` | `test_worker_cli::test_message_resume_lease_and_interrupt` |
| `test_worker_review_round1::test_a_wrapper_with_a_long_command_line_is_still_recognised` | `test_worker_cli::test_terminate_a_live_worker` |
| `test_worker_review_round1::test_an_op_id_names_one_operation` | `test_worker_state::test_op_outbox_answers_a_retry_from_the_first_result` |
| `test_worker_review_round1::test_terminate_reaches_the_harness_and_its_children` | `test_worker_cli::test_terminate_a_live_worker` |
| `test_worker_review_round2::test_a_prompt_containing_the_placeholder_cannot_break_the_quoting` | `test_worker_adapters::test_generic_needs_a_cli_and_custom_cli_overrides_any_harness` |
| `test_worker_review_round2::test_codex_resume_keeps_the_sandbox_and_reads_stdin` | `test_worker_adapters::test_default_commands_follow_the_documented_cli_flags` |
| `test_worker_review_round2::test_malformed_hook_stdin_denies` | `test_hook_adapters::test_internal_errors_fail_closed` |

Caveat that applies to every row: identical line sets with different inputs are not the same specification. `test_a_wrapper_with_a_long_command_line_is_still_recognised` executes the same lines as `test_terminate_a_live_worker` but is the regression test for the `ps -ww` fix in `20430b9`. Folding means moving the input into the twin's parametrisation, not deleting it.

## 3. Unique-coverage redundancy, whole suite

`scripts/census/coverage_overlap.py unique`: tests with coverage data 1,874; **1,316 (70 %) cover zero lines that no other test covers.**

| test file | tests | zero-unique | share |
|---|---:|---:|---:|
| test_tool_call_guard.py | 70 | 65 | 93% |
| test_review_round6_guard.py | 67 | 60 | 90% |
| test_brainstorm_search_providers.py | 40 | 38 | 95% |
| test_contract_citations.py | 36 | 35 | 97% |
| test_worker_review_round2.py | 25 | 23 | 92% |
| test_search_index.py | 25 | 22 | 88% |
| test_roadmap_crud.py | 21 | 20 | 95% |
| test_grind_session_implement.py | 25 | 20 | 80% |
| test_review_round6_ops.py | 26 | 19 | 73% |
| test_grind_session_step.py | 24 | 18 | 75% |
| test_finish_implementation_check.py | 19 | 18 | 95% |
| test_brainstorm_session.py | 27 | 18 | 67% |
| test_review_round5.py | 24 | 17 | 71% |
| test_text_sections.py | 20 | 17 | 85% |
| test_do_next_queue.py | 20 | 16 | 80% |

The top files are input tables over one classifier (`tool_call_guard`, search providers, contract citations): zero unique lines is expected there and says nothing about value. The signal is in files like `test_do_next_queue.py` (16 of 20, and 90 % private-coupled), where several tests drive the same message builder.

## 4. Never-executed defensive lines

`scripts/census/unexecuted_guards.py` against the subprocess-aware run (`.pth` + `COVERAGE_PROCESS_START`, 86 % line coverage). Guard kinds: `except` handler line, `raise`, `return`/`return None` directly inside an `if`, `if ... is None`, `if isinstance(...)`.

| module | except | raise | return | is-none | isinst | unexecuted |
|---|---:|---:|---:|---:|---:|---:|
| bundled_scripts/review_node.py | 15 (16) | 18 (20) | 1 (1) | 2 (4) | 2 (2) | 38 |
| gui_app_routes_nodes.py | 7 (11) | 13 (18) | 1 (1) | 0 (1) | 0 (0) | 21 |
| bundled_scripts/roadmap_edit_fields.py | 2 (2) | 11 (15) | 4 (9) | 0 (4) | 1 (1) | 18 |
| bundled_scripts/roadmap_crud_ops.py | 3 (7) | 11 (19) | 3 (6) | 0 (3) | 0 (4) | 17 |
| bundled_scripts/roadmap_move_node.py | 2 (2) | 7 (7) | 4 (4) | 2 (3) | 0 (4) | 15 |
| bundled_scripts/roadmap_outline_ops.py | 0 (0) | 8 (10) | 4 (4) | 3 (5) | 0 (5) | 15 |
| bundled_scripts/planning_artifacts.py | 6 (6) | 2 (4) | 6 (9) | 0 (1) | 0 (3) | 14 |
| bundled_scripts/update_specy_road.py | 1 (1) | 5 (5) | 5 (10) | 3 (5) | 0 (0) | 14 |
| milestone_chunk_io.py | 0 (0) | 7 (7) | 0 (0) | 3 (3) | 4 (4) | 14 |
| pm_publish.py | 0 (0) | 14 (16) | 0 (2) | 0 (1) | 0 (0) | 14 |
| bundled_scripts/brainstorm_research.py | 5 (6) | 8 (13) | 0 (0) | 0 (0) | 0 (3) | 13 |
| bundled_scripts/roadmap_chunk_utils.py | 7 (8) | 2 (4) | 3 (5) | 0 (1) | 0 (8) | 12 |
| cli.py | 3 (3) | 7 (12) | 0 (0) | 2 (2) | 0 (0) | 12 |
| (other modules) | | | | | | 475 |
| **total** (unexecuted of all) | **245 (337)** | **269 (501)** | **143 (306)** | **24 (308)** | **24 (250)** | **705 (1,702)** |

`is None` and `isinstance` checks are almost all executed (92 %, 90 %): the shape-checking that reads as paranoia is exercised. What is not exercised is **73 % of `except` handlers and 54 % of `raise` sites**. `review_node.py` alone has 38, which is the LLM-provider adapter that no test drives end to end.

**Hand check, 30 sampled (seed 761).** Trigger classes: user input, file, HTTP, git/subprocess, network, environment, concurrency.

| guard | kind | verdict | trigger |
|---|---|---|---|
| archive_deep.py:107 | return | reachable | archive record whose `chunk` file was deleted |
| brainstorm_verify.py:54 | except | reachable | DNS failure in `getaddrinfo` |
| llm_throughput.py:153 | return | reachable | provider response without `usage` |
| mark_implementation_reviewed.py:219 | raise | reachable | user declines the approval prompt |
| reconcile_milestone_status.py:58 | return | uncertain | node `id` not a string; schema forbids, reader takes raw nodes |
| refresh_schemas.py:99 | raise | **unreachable** | bundled `schemas/` missing; `verify_wheel_contents` guards the wheel |
| review_node.py:246 | except | reachable | file removed between listing and `stat` |
| roadmap_chunk_atomic.py:94 | return | uncertain | `rollback()` before `stage()`; caller ordering |
| roadmap_chunk_router.py:148 | return | uncertain | node absent from `nodes_after`; callers build it from the node |
| roadmap_chunk_router_pick.py:341 | raise | reachable | derived chunk path containing `..` |
| roadmap_chunk_utils.py:201 | return | reachable | `manifest.json` with empty `includes` |
| roadmap_crud_dependency_ops.py:101 | raise | reachable | bad dependency key |
| roadmap_edit_fields.py:285 | raise | reachable | `decision.status` outside the enum |
| roadmap_edit_fields.py:98 | raise | reachable | `parent_id` equal to own id |
| roadmap_gui_settings.py:121 | except | reachable | corrupt `gui-settings.json` |
| roadmap_load_at_ref.py:43 | return | reachable | manifest at a git ref that is not an object |
| scaffold_planning.py:55 | raise | reachable | unknown node id |
| start_milestone_session.py:156 | raise | reachable | parent already carrying `milestone_execution` |
| start_milestone_session.py:48 | raise | reachable | unknown node id |
| sync_planning_artifacts.py:28 | except | reachable | unnormalisable `planning_dir` |
| gui_app_routes_planning.py:67 | except | reachable | scaffold `ValueError` to HTTP 400 |
| gui_app_routes_workspace.py:145 | raise | reachable | `OSError` on write (read-only tree) |
| history_git.py:169 | return | reachable | `git cat-file --batch` answering `<sha> missing` |
| managed_block.py:122 | except | reachable | undecodable `AGENTS.md` |
| pm_gui_concurrency.py:47 | except | reachable | non-integer fingerprint header |
| pm_publish.py:186 | raise | reachable | every changed file gitignored, `git add` stages nothing |
| pm_publish.py:251 | raise | reachable | `git add` failing (index lock) |
| search_index.py:114 | except | reachable | SQLite write failure |
| specyrd_cli.py:28 | except | reachable | corrupt `.specyrd/manifest.json` |
| worker_ops.py:101 | raise | reachable | eligibility class not matched by the model profile |

**Split: 26 reachable-untested, 3 uncertain, 1 unreachable.**

## 5. Mutation census, scoped

Scoped `mutmut 3.8.0` run on the eight most-imported modules, every line mutated (not only covered ones), full suite minus the two deselected tests below, `--max-children 8`. It hit its two-hour cap: **2,604 of 3,186 mutants reached** (582 not checked, 92 with no covering test, 1 timeout). Score is killed / (killed + survived), so unreached mutants are left out rather than counted as survivors; the partly reached modules are samples.

| module | killed | survived | not scored | score |
|---|---:|---:|---:|---:|
| `review_files` | 245 | 32 | 59 | 88.4 % |
| `worker_state` | 176 | 40 | 347 | 81.5 % |
| `archive_ops` | 174 | 41 | 0 | 80.9 % |
| `worker_ops` | 613 | 177 | 3 | 77.6 % |
| `bundled_scripts.roadmap_chunk_utils` | 113 | 43 | 61 | 72.4 % |
| `worker_adapters` | 430 | 237 | 29 | 64.5 % |
| `bundled_scripts.roadmap_load` | 95 | 57 | 143 | 62.5 % |
| `gui_app` | 15 | 24 | 32 | 38.5 % |
| **total** | **1,861** | **651** | **674** | **74.1 %** |

Survivors cluster in a few functions: the three harness output parsers (`Cursor.parse` 72, `Codex.parse` 38, `ClaudeCode.parse` 33), then `worker_ops._send` 25, `archive_ops.auto_archive_candidates` 25, `gui_app.create_app` 24, `worker_ops._check_eligible` 20 and `_preflight` 19. The parsers are the clearest gap: the tests feed them a few representative event lines, so a mutated field name or event type in the less common branches goes unnoticed. That matches section 4: the weakness is untested input shapes at boundaries, not surplus tests.

**Not a baseline.** `constraints/mutation-baseline.json` is not seeded from this run. CI's `mutation.yml` mutates the whole package, covered lines only, with the full suite, so its per-module scores are not comparable with these; seeding from here would fail the weekly report on a configuration change, not a regression. The first complete CI run seeds it (`scripts/mutation_report.py --write-baseline`).

**Not a consolidation licence.** `mutmut results` says whether a mutant was killed, not which tests killed it, so it cannot yet show that a review-round test's mutants are also killed elsewhere. Folding round tests (section 2) still needs a per-test kill check on the touched module.

## 6. Duplication baseline

`pylint --disable=all --enable=duplicate-code --min-similarity-lines=6 --ignore-imports=y --ignore-docstrings=y --ignore-signatures=y specy_road` (3.5 s): **12 clone pairs**.

| file A | file B | lines | what |
|---|---|---:|---|
| milestone_session | on_complete_session | 17 | YAML session read/write (`version`/`node_id`/`codename` round trip) |
| do_next_task_args | pm_sync | 12 | `--base`/`--remote` argparse block |
| abort_task_pickup | registry_prune | 12 | `--base`/`--remote` argparse block |
| review_files | worker_state | 12 | `_validator` + schema-error formatting |
| pm_sync | start_milestone_session | 11 | argparse block |
| abort_task_pickup | do_next_task | 10 | resolve-and-print integration defaults |
| refresh_schemas | refresh_stubs | 10 | argparse block |
| model_profiles | review_files | 10 | `_split` front-matter splitter (`---` fence scan) |
| brainstorm_chat | review_node | 9 | provider error printing |
| finish_task | mark_implementation_reviewed | 9 | argparse block |
| worker_lock | worker_witness | 8 | re-entrant lock depth bookkeeping on `_LOCAL` |
| roadmap_chunk_router_pick | roadmap_chunk_utils | 7 | manifest include path escape check |

**Reuse audit, helpers added since `v0.2.3`** (46 new source files, 400 new `def`s; duplicates of an older helper's job):

| new helper | duplicates | note |
|---|---|---|
| `worker_witness._now`, `worker_outbox._now`, `worker_lease._now`, `worker_state._now`, `worker_ops._now` (identical bodies) | `archive_plan.utc_now_iso` (old) | six copies of one line; `session_presence._now` returns a `datetime`, `grind_session_events._now_iso` (old) a `Z` form: three timestamp formats in one package |
| `worker_state._validator` + `schema_errors` | `review_files._validator` + `_schema_errors` (old) | byte-identical pair; the pylint clone above |
| `worker_reconcile._target` | `worker_ops._target` (both new) | same `resolve_target` wrap, different error text |
| `model_profiles._split` | `review_files` front-matter split (old) | the pylint clone above |
| `worker_outbox._write_atomic` | `worker_state._write_atomic` | a two-line re-export, not a copy; fine |
| `update_specy_road._git_output` (old) and `repo_ops.git_capture` | `git_subprocess.git_stdout` (old) | three ways to capture git stdout; pre-dates 0.3, listed for completeness |

## 7. Size by era

Split at `266f700` (first commit of the 0.3 line, 2026-10-26). `git log --numstat` over `specy_road/*.py` and `tests/*.py`; test count = `def test_` at the era's end commit.

| era | commits | source +/- | test +/- | tests at end | test/source lines at end | ratio of added lines |
|---|---:|---:|---:|---:|---:|---:|
| pre-0.3 (`3b56519`..`266f700`, Apr 5 - Oct 26) | 367 | +37,447 / -4,707 | +27,382 / -962 | 1,386 | 26,419 / 32,717 = 0.81 | 0.73 |
| 0.3 line (`266f700`..`20430b9`, Oct 26 - 27) | 68 | +8,577 / -1,539 | +6,531 / -232 | 1,752 | 32,720 / 39,754 = 0.82 | 0.76 |
| for reference, at `v0.2.3` | | | | 1,310 | 25,228 / 31,301 = 0.81 | |

The ratio is flat across eras. What differs is pace: the 0.3 line added 22 % of today's source and 21 % of its tests in two days. Test deletions are 3.5 % of test additions in both eras against 12.6 % and 17.9 % for source; tests are added and almost never removed, which is the Milanese et al. pattern the research report cites.

## Recommended consolidations

1. **Fold the 58 strict twins** (section 2 list) into their non-round files as extra parametrise rows or extra assertions, then retire the empty round files. Start with `test_worker_review_round2.py` (16 zero-unique) and `test_review_round6_guard.py` (12), whose twins are `test_worker_cli.py` and `test_tool_call_guard.py`. Keep every input; drop only the duplicate scaffolding.
2. **Merge the `test_do_next_queue.py` trio** (`test_exit_no_actionable_leaves_*`, rows 4/8/9 above) into one parametrised test of `_exit_no_actionable_leaves`.
3. **Unpin the eight implementation-pinned tests** when their files are next touched: replace `side_effect` ordering in `test_roadmap_gui_remote` with a URL-keyed fake; drop `raising=False` in `test_claim_traps::test_local_pickup_skips_sync_and_push` (it silently disarms the assertion); assert on registry state rather than `git_run` argument tuples in `test_registry_prune`.
4. **Guards to cover, not delete:** the input-validation `raise`s in `roadmap_edit_fields.py` (11 unexecuted), `roadmap_crud_ops.py` (11) and `gui_app_routes_nodes.py` (13) are one parametrised bad-input test each. `review_node.py`'s 33 unexecuted handlers need a fake provider fixture; that is the single largest untested surface.
5. **Guard to delete:** `refresh_schemas.py:99` (packaging invariant already enforced by `verify_wheel_contents`). The three "uncertain" rows need a caller trace before deciding; none is worth more than a comment.
6. **Duplication:** one `specy_road.clock.now_iso()` replacing the six `_now` copies; `worker_state.schema_errors` importing `review_files._validator` instead of copying it; a shared `add_base_remote_args(parser)` for the four argparse clones.

## Not measured

- **Subprocess-only tests in overlap figures.** 220 collected tests leave no in-process coverage context (CLI tests that spawn `specy-road`), so sections 2 and 3 are computed over 1,874 tests. Section 4 does include their lines via a second run with subprocess tracing (82 % to 86 %).
- **Refactor-resilience trial, review-loop archaeology, matched-era author comparison, ablated AGENTS.md trial** from the research reports: not run; each needs source changes or multi-run harnesses outside a one-day read-only census.
- **Branch coverage.** Line contexts only; an executed `if` line whose false arm never ran counts as executed.
- **Per-module mutation wall time** is approximate (derived from five-minute progress snapshots); mutmut 3 does not report it.
- **Mutation beyond eight modules, and the 582 mutants the capped run did not reach.** Which tests kill which mutants (needed before folding round tests).

## Reproduction

```bash
python -m venv /tmp/census-venv && /tmp/census-venv/bin/pip install -e '.[dev]' 'pytest<9' pytest-cov mutmut pylint
PYTHONPATH=$PWD pytest -q -p no:cacheprovider --cov=specy_road --cov-context=test --cov-report=
python scripts/census/private_coupling.py tests
python scripts/census/coverage_overlap.py round .coverage
python scripts/census/coverage_overlap.py unique .coverage --top 15
python scripts/census/unexecuted_guards.py .coverage
rm -rf tests/fixtures/specy_road_dogfood/.specyrd/cache .coverage
```

Mutmut 3.8 needs `pytest<9` (its harness reads `item._nodeid`), a `[tool.mutmut]` block in a scratch copy with `only_mutate` and an `also_copy` list of every top-level path the tests read, and `--deselect` for `test_cli_loop_base_dependencies.py` and `test_file_limits_passes_on_repo`, both of which fail on the instrumented sources by design.
