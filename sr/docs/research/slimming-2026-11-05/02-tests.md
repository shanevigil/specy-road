# specy-road test suite: size, redundancy, gaps, and a target shape

Snapshot: WIP HEAD `b216d799` (scratch copy, no git metadata), compared with v0.2.3.
Everything was measured on the snapshot copy; nothing in the live checkout was touched.

## 0. Method (and its limits)

* **Runtime / inventory.** Ran `pytest -n 16 --durations=0 --junitxml` in the snapshot, then did static AST analysis of `tests/test_*.py`.
* **Per-test coverage.** I used `pytest-cov --cov-branch --cov-context=test` for in-process code. Python subprocesses were captured too, through a `sitecustomize` hook (scratch dir on `PYTHONPATH`) that starts coverage in every child process. Each child got a static context equal to the parent test's node id, set by an autouse fixture loaded with `-p`. That captured 1,069 child processes from 464 tests. Main and child data were combined, and the analysis uses the **arc table (branch arcs)** per test. Arcs that run only at import/collection time (context `""`) are credited to no test.
* "**Unique**" means: an arc covered by exactly one test in the whole suite.
* **Near-duplicate.** For every zero-unique test, I took the nearest neighbour by Jaccard similarity of arc sets. Candidates were the tests that share its 3 rarest arcs.
* **Caveats.**
  * Durations were taken under `-n 16` on a machine that was also running a live build. They are inflated, so treat them as relative.
  * Six tests fail in the snapshot only because it is not a git checkout (`claude_config_dir` ×4, `lean_gates::test_machine_paths…`, `running_toolkit_version`). Three more fail only under coverage instrumentation (`ready_command` ×2, `review_delegate` ×1).
  * Subprocesses launched with a hand-built env that drops `PYTHONPATH`, and non-Python subprocesses (shell wrappers, git), are not attributed.
  * 193 items execute no `specy_road` code at all: lean gates over `scripts/`, docs/rules pointers, release scripts, wheel contents. They are judged separately below.
  * Coverage proves execution, not checking. "Zero unique coverage" is a lead for review, not a verdict (see §2).

## 1. Inventory

### Headline numbers

| | v0.2.3 | WIP (b216d799) | growth |
|---|---|---|---|
| test files (`test_*.py`) | 147 | 353 (+13 helper modules) | 2.4× |
| test functions | 1,310 | 3,325 | 2.5× |
| collected items | 1,462 | 4,400 | 3.0× |
| test lines | 25.1k | 64.2k | 2.6× |
| `specy_road` source lines | 31.3k | 65.4k | 2.1× |
| line+branch coverage of `specy_road` | 79% | **89%** (91.2% lines, 83.7% branches) | +10 pts |
| wall time, same machine, `-n 16` | 58.6 s | 110–114 s | 1.9× |

The ratio of test lines to source lines (about 1:1) is not alarming on its own. The bloat shows up in three places instead:

* how many tests exercise each behaviour;
* how much each test costs (git and subprocess);
* how the files are organised.

### By subsystem (file-name classification)

| subsystem | files | test fns | items | lines | CPU-s | items with 0 unique arcs |
|---|---|---|---|---|---|---|
| roadmap/validate/brief/search/history | 61 | 593 | 642 | 10.6k | 129 | 71% |
| review (gate, packet, defer, rca, rounds) | 43 | 552 | 796 | 9.5k | 416 | 77% |
| worker/worktree/roster/harness | 45 | 471 | 690 | 8.8k | 300 | 78% |
| init/upgrade/install/docs/cli | 50 | 371 | 567 | 7.7k | 136 | 85% |
| registry/git/integrity/lean/file-limits | 30 | 274 | 415 | 5.0k | 102 | 85% |
| brainstorm | 16 | 230 | 301 | 3.9k | 80 | 69% |
| pickup/do-next/session | 31 | 217 | 228 | 5.2k | 92 | 66% |
| orchestrate/grind/milestone | 22 | 194 | 259 | 3.6k | 57 | 75% |
| finish/land/nested | 25 | 180 | 228 | 4.2k | 157 | 75% |
| gui / pm-gui | 17 | 128 | 135 | 3.2k | 38 | 60% |
| archive | 6 | 62 | 63 | 1.2k | 15 | 68% |
| other (doctor, fixture guard, …) | 7 | 53 | 76 | 1.2k | 116 | 79% |

### By style

The style was classified per file, from its content. Many files mix styles.

| style | files | test fns | CPU-s |
|---|---|---|---|
| pure unit (no git, no CLI) | 100 | 863 | 91 |
| builds real git repos (in-process calls) | 78 | 705 | 549 |
| git repo + in-process `main([...])` | 42 | 422 | 350 |
| CLI subprocess (no git) | 39 | 376 | 184 |
| git + subprocess + in-process CLI | 27 | 301 | 184 |
| CLI subprocess + git | 31 | 262 | 186 |
| in-process CLI only | 16 | 213 | 48 |
| FastAPI `TestClient` (some mixed) | 15 | 131 | 39 |

* **Subprocess tests.** Measured per test, **464 tests spawn `python -m specy_road…` subprocesses (1,069 processes)**. They account for **32% of total CPU-time**. One test spawns 18 processes.
* **Git repos.** 111 test/helper files run `git init`; 90 files call git directly.
* **Where the time goes.** 1,911 items (43%) finish in under 50 ms. The 418 items that take 1 s or more consume most of the runtime.

### Per-leaf / per-finding files

32 files are named after a roadmap leaf, a review round, or a pre-release section rather than a module:

* `test_review_round{2,4,4b,5}_*`, `test_review_round6_{brainstorm,docs,evidence,guard,ops,policy,runner}`
* `test_worker_review_round{1,2}`, `test_prerelease_{apps,files,review,s2,s5,s7,workers}`
* `test_m11_27_small_cli_fixes`, `test_m13_7_*`, `test_*_m36/_m37/_m310`
* `test_*_fixes`, `test_pm_gui_field_repros`, `test_review_hardening`, …

Together these hold 297 functions and 405 items, 6.1k lines, and 180 CPU-s. 101 files have a module docstring citing a review, finding, round, or regression.

These files are no more redundant than the rest (78% zero-unique vs 76%). **The redundancy is pervasive, not confined to round files.** Their real cost is organisational. For example, `test_m11_27_small_cli_fixes.py` covers `role_prompt`, `validate_roadmap`, `finish_ancestor_rollup`, `worker_runner` and `worker list`. It builds its own 70-line roadmap repo inline, and imports private helpers from two other test files.

* **File sizes.** Median file is 8 tests and 166 lines. 112 files have ≤5 tests; 59 have ≤3.
* **Parametrization.** 241 `parametrize` decorators produce 1,248 items. 1,134 of those items (91%) have zero unique arcs: most are input tables walking the same path, which is cheap and fine when they are unit-level.

### Slowest 30 tests

Measured on a loaded machine under `-n 16`. Total CPU across all items was 1,637 s.

* The top 30 take 179 s (**10.9%**).
* The top 100 take 25%, the top 300 take 47%, and the top 1,000 take 80%.

| # | s | test | unique arcs |
|---|---|---|---|
| 1 | 17.8 | `test_lean_gates.py::test_check_clones_passes_on_committed_baseline` (runs pylint clone detection over the whole repo: a CI gate, not a unit test) | n/a |
| 2 | 8.7 | `test_review_defer_rounds.py::test_round3_every_next_step_runs_or_is_absent` | 0 |
| 3 | 7.4 | `test_doctor_live.py::test_r3_a_fresh_branch_at_another_branchs_unlanded_tip_has_no_commits` | 0 |
| 4 | 6.7 | `test_worker_faults.py::test_output_clears_a_stall_shorter_than_the_write_window` (real sleeps) | 1 |
| 5 | 6.6 | `test_doctor_live.py::test_a_claimed_worktree_on_a_fresh_branch_is_live_and_fix_leaves_it` | 0 |
| 6 | 6.6 | `test_pickup_register_digest.py::test_abort_after_pushed_pickup_regenerates_the_digest_on_integration` | 13 |
| 7 | 6.5 | `test_prerelease_apps.py::test_abort_of_a_local_pickup_drops_the_claim_without_pushing` | 1 |
| 8 | 6.3 | `test_red_green.py::test_record_has_one_outcome_per_test_at_base_and_head` | 83 |
| 9 | 6.3 | `test_worker_queue_message.py::test_two_cli_messages_during_a_live_turn_are_appended_and_delivered` | 0 |
| 10 | 6.0 | `test_doctor_live.py::test_f4_a_fast_forwarded_commit_with_no_local_branch_is_merged_but_left` | 0 |
| 11 | 5.7 | `test_pickup_register_digest.py::test_failed_pickup_self_heal_leaves_integration_digest_current` | 3 |
| 12 | 5.7 | `test_pickup_register_digest.py::test_abort_drops_a_local_register_commit_that_carries_the_digest` | 0 |
| 13 | 5.6 | `test_refusals_name_their_fix.py::test_each_refusal_exits_1_and_names_a_runnable_next_step[_milestone_approval_on_a_dirty_tree]` | 0 |
| 14 | 5.5 | `test_doctor.py::test_fix_leaves_what_changed_after_listing` | 7 |
| 15 | 5.4 | `test_worker_queue_message.py::test_message_while_running_queues_and_delivers` | 0 |
| 16 | 5.2 | `test_doctor_live.py::test_f4_a_fast_forwarded_commit_with_an_expired_reflog_is_merged_but_left` | 3 |
| 17 | 5.2 | `test_doctor_live.py::test_r5_f1_a_copy_of_a_merged_branch_has_no_commits_of_its_own` | 0 |
| 18 | 5.1 | `test_pickup_register_digest.py::test_pickup_commits_the_digest_with_the_claim` | 0 |
| 19 | 5.0 | `test_doctor_live.py::test_r4_a_claim_beats_a_session_and_a_session_alone_still_protects` | 1 |
| 20 | 4.9 | `test_doctor_live.py::test_r5_f2_a_local_namesake_at_the_remote_tip_keeps_the_remotes_finish_merge` | 0 |
| 21 | 4.9 | `test_worker_faults.py::test_last_output_at_is_written_at_most_every_five_seconds` (real sleeps) | 0 |
| 22 | 4.8 | `test_doctor_live.py::test_r1_a_reused_branch_name_with_a_creation_only_reflog_has_no_commits` | 0 |
| 23 | 4.7 | `test_doctor_live.py::test_f1_a_claimed_worktree_whose_directory_moved_is_live_not_missing` | 0 |
| 24 | 4.7 | `test_prerelease_s2.py::test_rerunning_finish_retries_a_failed_merge_landing` | 2 |
| 25 | 4.7 | `test_milestone_full_review.py::test_approval_through_mark_implementation_reviewed_releases_the_rollup` | 3 |
| 26 | 4.6 | `test_brainstorm_cli.py::test_promote_writes_accepted_ideas_into_the_graph` | 0 |
| 27 | 4.6 | `test_doctor.py::test_fix_leaves_a_temporary_worktree_another_command_is_using[specy-road-nested-land-]` | 0 |
| 28 | 4.5 | `test_finish_work_cleanup.py::test_an_opted_in_completed_worker_goes_through_review_to_finish` | 0 |
| 29 | 4.5 | `test_review_next_step.py::test_spent_defer_unapplied_then_applied_rows` | 0 |
| 30 | 4.4 | `test_rollup_branch_cleanup.py::test_rollup_finish_deletes_the_leaf_once_it_is_in_the_rollup` | 0 |

22 of the slowest 30 add **no unique arcs**. `test_doctor_live.py` alone costs 71 CPU-s: it is a series of named review-finding scenarios (`r1`, `r3`, `r4`, `r5_f1`, `r5_f2`, `f1`, `f4`…), each building a fresh repo plus a bare remote. Other heavy files:

* `brainstorm_cli` 60 s
* `doctor` 35 s
* `review_defer_rounds` 28 s
* `review_next_step` 27 s
* `review_deferral_agreement` 27 s
* `review_rca` 25 s
* `review_packet` 24 s
* `lean_gates` 24 s
* `pickup_register_digest` 23 s

## 2. Redundancy

### Coverage-only numbers (upper bounds, not a deletion list)

| measure | value |
|---|---|
| items with coverage contexts | 4,207 (193 run no `specy_road` code) |
| distinct arcs covered | 52,199 |
| items with **0 unique arcs** | **3,201 (76%)** — they use 1,109 of 1,637 CPU-s (68%) |
| items with 1–2 / 3–10 / 11–50 / >50 unique arcs | 421 / 480 / 102 / 3 |
| greedy minimum set reproducing 100% of arc coverage | **1,385 items** (31% of the suite) |
| time-weighted greedy minimum set | 1,696 items, **658 CPU-s (41% of runtime)** |
| items with identical arc sets to another item | 1,147 in 390 groups (757 removable keeping one per group; 178 groups are just params of one function) |
| items whose arc set ⊆ one other single test | 1,836 (962 of them dominated by a test in the same file) |
| test files that add 0 unique arcs **as a whole file** | 46 |
| test files where every test has 0 unique arcs | 66 |

So if coverage were the only criterion, about 3,000 items could go. That figure is misleading. A 76% zero-unique rate is normal for a layered suite: each narrow unit test is "covered" by some end-to-end test that happens to run the same code without checking it. The useful signal is **how close** a test is to its nearest neighbour.

Nearest-neighbour Jaccard over the 3,187 non-empty zero-unique items:

| Jaccard to nearest test | param sibling | same file | other file | total |
|---|---|---|---|---|
| ≥ 0.95 (same path) | 772 | 783 | 319 | **1,874** |
| 0.80–0.95 | 101 | 283 | 174 | 558 |
| 0.50–0.80 | 18 | 185 | 163 | 366 |
| < 0.50 (narrow slice of a bigger test) | 5 | 164 | 220 | 389 |

### Manual classification of a random sample

I took a random sample of non-parametrized pairs with Jaccard ≥ 0.95 and read both tests in each pair.

| pair (test ~ nearest neighbour) | verdict |
|---|---|
| `review_next_step::test_budget_unset` ~ `review_defer::test_budget_unset_reports_nothing_new` | **(a)** same scenario, same assertion |
| `specyrd_skills::test_init_without_force_keeps_a_users_skill_directory` ~ `review_round2_routing::test_a_users_own_skill_directory_is_reported_skipped` | **(a)** |
| `grind_session_implement_resilience::test_the_default_ceiling_still_refuses_that_reset` ~ `grind_session_implement::test_a_reset_beyond_the_wait_ceiling_stops` | **(a)** |
| `roadmap_crud::test_edit_node_cli` ~ `roadmap_crud_edit_node_chunks::test_edit_node_in_place_lists_read_and_written_chunk` | **(a)** strict subset of the assertions |
| `review_round6_guard::test_explicit_pathspecs_pass[...]` ~ `tool_call_guard::test_ordinary_commands_pass[...]` (identical row in two files) | **(a)/(b)** one classifier table split across 3 files (`tool_call_guard`, `review_round5`, `review_round6_guard`) |
| `review_round5::test_more_wrapper_shapes_are_classified[...]` ~ `tool_call_guard::test_destructive_commands_are_classified[...]` | **(b)** |
| `version_skew_install::test_symlinked_prefix…` ~ `…test_no_shadow_warning…` | **(b)** one table |
| `pm_gui_git_remote_verify::…enabled_false_without_repo_and_token[...]` ~ `…enabled_true_when_gates_satisfied` | **(b)** truth table written as separate tests |
| `search_cli::test_multi_word_queries_are_joined` ~ `test_rebuild_still_answers` | **(b)**; both only assert `"result(s)" in out` (weak) |
| `agent_ignores::test_orchestration_local_overlay_is_gitignored` ~ `test_git_actually_ignores_the_caches_afterwards` | **(b)** one "git check-ignore over paths" table |
| `integrity_python::test_skip_decorator_on_class…` ~ `test_tests_inside_control_flow_are_compared[...]` | **(b)** |
| `archive_ops::test_round_trip_restores_a_byte_identical_tree` ~ `archive_dependencies::test_the_dependency_edge_survives…` | **(d)** different invariant |
| `review_round4_sol::test_concurrent_reclaims_record_one_intervention` ~ `review_round6_ops::test_a_crashed_reclaim_is_repaired_once` | **(d)** concurrency vs crash recovery |
| `finish_ancestor_rollup::test_identifies_stale_ancestors…` ~ `test_skips_ancestors_owned_by_the_milestone_rollup…` | **(d)** data-dependent behaviour on the same path |
| `gui_safe_saves::test_put_hash_is_of_its_own_write…` ~ `test_fresh_save_accepted…` | **(d)** race |
| `doctor_live::test_r5_f2_…` ~ `test_an_unclaimed_branch_with_no_commits_is_never_merged` | **(d)**, but expensive; each scenario is a fresh repo plus a bare remote |

The low-Jaccard bucket (< 0.5) is mostly focused unit tests of pure functions, which are worth keeping (d). Examples:

* `file_limits_engine::test_merge_exclude_patterns_merges_keys`
* `llm_throughput::test_estimate_tokens_min_one`
* `human_acceptance::test_marker_and_decision_lines`

### Estimate by category

These are extrapolated from the sample. Treat them as ±30% ranges.

* **(a) Duplicate assertion of the same behaviour: ~300–400 items.** Concentrated in the ≥0.95 cross-file bucket (319) and the per-round/per-leaf files that re-test what the module file already tests. These can be deleted after checking each pair.
* **(b) Narrow single-input regressions that a table would subsume: ~500–700 functions.** These should be folded into roughly 120–180 parametrized tests. The item count drops less than the function count, because rows survive as cheap params; the win is that each scenario's setup runs once. Hot spots:
  * the tool-call guard classifier (3 files)
  * `refusals_name_their_fix`
  * pm-gui settings gates
  * agent-ignores paths
  * integrity_python shapes
  * version-skew launchers
  * hook adapters
  * the `review_record_rules` refusals
* **(c) Implementation-detail tests: ~150–200 functions.**
  * 137 test functions in 40 files call or import `specy_road` private names (`_x`).
  * 100 `monkeypatch.setattr` calls in 25 files patch private names. Most-patched: `_cmdline` 13, `_run_shell` 6, `_run_capturing` 5, `_now_iso` 5, `_load_branch_enrichment` 5, `_assert_current_branch_equals` 5, `_push_integration_branch` 4, `_make_client` 4.
  * Most of these seams should become public injection points (a clock, a runner, a client factory), with tests rewritten against them, not deleted.
* **(d) Genuinely valuable: the remaining ~2,200–2,500 functions.** These include:
  * all 1,006 items with unique arcs
  * the low-Jaccard focused unit tests
  * concurrency, crash and race tests
  * the git-semantics scenarios in doctor/finish/land, which are expensive but real

**Bottom line: about 30–35% of test functions can be removed or merged with zero coverage loss and no loss of checked behaviour: roughly 3,325 → 2,100–2,300 functions.** Removing time-dominated duplicates, and moving subprocess/git setup to shared templates, should cut CPU-time by 40–50%. The time-weighted cover shows 41% of current CPU keeps 100% of arcs.

### The 193 items that cover no `specy_road` code

* `lean_gates` (45): runs repo gates over `scripts/`. `test_check_clones_passes_on_committed_baseline` alone is 17.8 s and duplicates the CI lint/clone step. Make it a CI job or mark it `slow`.
* `enforced_rules_pointers` 24, `cli_loop_base_dependencies` 18, `release_harness` 18, `check_release_version` 7, `verify_wheel_contents` 6, and docs/regression-catalogue checks.

These are repository-consistency checks. Keep them, but put them in a `tests/repo/` (or `-m repo`) lane so they are not mistaken for product tests.

### Files that add zero unique arcs as a whole

There are 46. Review these first for deletion or merging:

`agent_ignores, claude_config_dir, cli_imports_without_gui_extra, context_regressions, do_next_gate, doctor_classification, enforced_rules_pointers, file_limits_gitignore, finish_pr_body, grind_session_claude, grind_session_resume_command, init_project, init_project_gitignore, lean_rules, milestone_lock, model_profile_aliases, nested_zone_paths, one_readiness_rule, orchestrate_spread, package_data_schemas, pickup_orchestration_hint, pm_gui_field_repros, pm_gui_fingerprint, pm_integration_registry, prerelease_s7, project_layouts_outside, reconcile_milestone_status, registry_commit_scope, registry_overlap_warnings, registry_yaml, review_effort_study, review_eligible, roadmap_gui_pr_pickers, role_prompt_file_limits, running_toolkit_version, runtime_dirs_not_dirty, sandbox_setup_polish, session_plan_touch_zones, shared_checkout_guidance, start_milestone_session_reentry, validate_acceptance_coverage, worker_lease_races, worker_reconcile_contract, worker_reviews_dir_before_launch, worker_runner_safe_path, worktree_paths_agree`

Some of these exist for good reasons (packaging, import-without-extras, lease races) even though their arcs are covered elsewhere.

## 3. Coverage and gaps

**Overall: 89% (lines 30,885/33,882 = 91.2%; branches 9,506/11,358 = 83.7%; 1,402 partial branches).** In-process coverage alone is 86%; the subprocess tests add 3 points. The suite is bloated and also has holes. The gaps that matter are in milestone and graph-edit paths, not in glue code:

| module | cover | what is unexercised |
|---|---|---|
| `bundled_scripts/start_milestone_session.py` | **29%** | `main`, `_validate_parent`, `_ensure_rollup_branch` (rollup branch creation) |
| `milestone_chunk_io.py` | **53%** | `write_milestone_execution`, `patch_milestone_execution_state`, `maybe_promote_milestone_to_pending_mr` |
| `milestone_rollup_git.py` | 71% | `_cherry_pick_deterministically`, `cherry_pick_bookkeeping_to_integration`, `merge_leaf_into_rollup` |
| `bundled_scripts/reconcile_milestone_status.py` | 64% | `_plan_open_state`, `_plan_closed_state` |
| `bundled_scripts/open_milestone_pr.py` | 36% | `main` |
| `bundled_scripts/roadmap_outline_ops.py` | 66% | `apply_indent`, `apply_outdent`, `_validate_reparent_target` (graph restructuring; a good property-test target) |
| `bundled_scripts/roadmap_edit_fields.py` | 74% | `_set_parent_id`, `_apply_decision`, `_apply_scalar_top_level`, `_set_type` |
| `bundled_scripts/archive_cli.py` | 69% | `_cmd_archive_auto`, `cmd_restore` error paths |
| `bundled_scripts/scaffold_planning.py` | 53% | `main`, `scaffold_planning_for_node` |
| `bundled_scripts/update_specy_road.py` | 65% | kit-root discovery, `_git_fast_forward`, dirty-tree guard |
| `specyrd_cli.py` / `cli_init.py` / `cli.py` | 62% / 60% / 74% | interactive prompts, `install-gui`/npm build, `_cmd_gui` (lower value) |
| `gui_app_routes_planning.py` / `_workspace.py` | 61% / 57% | `api_planning_artifacts`, `_api_workspace_files`, LLM/git test endpoints |
| `bundled_scripts/review_node.py` | 57% | Azure/OpenAI client construction, `ping_llm` (external API glue; low value, use a contract-level fake) |
| `bundled_scripts/migrate_stable_node_keys.py` | **0%** | entire module: either dead (delete it) or an untested migration (test it) |
| `toolkit_version.py` | 46% | partly an artefact of the snapshot having no `.git` |

So the suite exercises the leaf-level worker/review/finish flows many times over, while the **milestone rollup lifecycle and outline restructuring are thin**.

## 4. Structural problems

1. **Files are organised by delivery event, not by module.** There are 353 flat files: 32 per-leaf/per-round files and 112 files with ≤5 tests. A single module is often tested from 5–10 files. For example, the review gate/defer/packet code is spread over 43 files, and the tool-call guard over 3.
2. **Test files import from other test files.** 98 files do `from tests.test_x import _helper`. Top sources: `test_worker_cli` (33 importers), `test_models_and_prompt` (21), `test_orchestrate_plan` (10), `test_roadmap_crud` (9). This makes test modules load-bearing libraries with private (`_repo`, `_launch`) APIs. Deleting or renaming one test file breaks unrelated ones.
3. **Fixtures and helpers are duplicated.**
   * 105 helper names are defined in more than one file (500 definitions). 53 groups have byte-identical bodies (177 definitions). Examples:
     * `repo` fixture: 40 files, 22 identical
     * `_cli`: 30 files
     * `_git`: 29
     * `_run`: 23
     * `_repo`: 20
     * `dogfood_copy`: 7
     * `api_client`: 6
     * `_mutation_headers`: 6 identical
   * 41 files hand-write `manifest.json`, 38 hand-write `git-workflow.yaml`, and 48 `copytree` the dogfood fixture. 105 literal node-key UUIDs are pasted across files.
   * There are already 11 `*_repo_helpers.py` modules, which overlap: `review_repo_helpers`, `milestone_repo_helpers`, `pickup_repo_helpers`, `integrity_repo_helpers`, `unauthored_repo_helpers`, … The root `conftest.py` only holds safety guards.
4. **Assertions match message text.** Of 9,568 asserts, 2,426 are membership checks and 1,496 are `"<literal ≥12 chars>" in output`. Some of this is intentional, because the project treats "refusals name their fix" as a contract. But most of it pins prose and makes wording edits ripple through many files. There are also 86 `==` comparisons against strings of 25+ characters.
5. **Private names are monkeypatched.** 100 patches in 25 files, plus 137 test functions touching `_private` names (see §2(c)). Several patch the same seam repeatedly (`_cmdline`, `_run_shell`, `_now_iso`), which shows a missing public injection point.
6. **Tests depend on wall-clock time.** 16 files use `time.sleep`, including `time.sleep(30)` ×3 (stub processes) and the `worker_faults` stall tests (5–7 s each, timing-sensitive).
7. **Subprocess CLI tests are used where in-process would do.** 464 tests spawn Python CLIs, at 32% of CPU. A handful of end-to-end entry-point smoke tests is enough; the rest can call `main(argv)` in-process. Many already have in-process equivalents.

## 5. Recommendation

### Target shape

* **About 2,100–2,300 test functions (~3,000 items), in ~130–160 files, with a full run under ~35 s at `-n auto`**, keeping coverage at or above 89% and raising branch coverage from 83.7% toward 87%+ by filling the §3 gaps.
* **Layout mirrors the package:**
  * `tests/unit/<module>_test.py`: pure functions and parsers. The bulk of the suite, fast.
  * `tests/flows/<area>/`: git-backed scenarios (finish/land, doctor, pickup, worker lifecycle, review gate), one file per user-visible flow.
  * `tests/cli/`: about 30–50 subprocess smoke tests, one per console entry point and exit-code contract. Everything else runs `main(argv)` in-process with `capsys`.
  * `tests/gui/`: `TestClient` routes, with the fingerprint/header contract as one parametrized test over all mutation routes.
  * `tests/repo/` (marker `repo`): docs/rules/packaging/release/lean-gate consistency checks; `check_clones` moves to CI only.
* **Fixture strategy.** Put these in `tests/conftest.py` plus `tests/support/`, with no imports from `test_*.py`:
  * A single `RoadmapBuilder` / `roadmap_repo(nodes=..., workflow=..., orchestration=...)` factory that writes the manifest, chunks, planning sheets, registry and `git-workflow.yaml`, and generates node keys deterministically. It replaces the 41 hand-written manifests and the pasted UUIDs.
  * A `git_repo` / `bare_remote` pair built once per session as a template and `copytree`'d per test (or `git clone --shared`). This removes `git init`/commit cost from about 1,000 tests.
  * `run_cli(argv)` in-process, plus `run_cli_subprocess(argv)` only for the smoke lane.
  * `dogfood_copy`, `api_client`, `fake_harness` (the `FAKE` worker script now imported from `test_worker_cli`), and an injectable clock that replaces `_now_iso` patching.
* **Property-based tests** (Hypothesis) for parsers and pure transforms, replacing dozens of single-input regressions:
  * `tool_call_guard.classify`: generated shell words, wrappers, quoting, and `--` pathspecs. This subsumes the 3-file table.
  * outline renumber / indent / outdent / rebalance: invariants such as ids being unique and contiguous, the parent/child relation preserved, and round-trip stability. This also fills the 66% gap in `roadmap_outline_ops`.
  * `managed_block`: insert/replace is idempotent and preserves outside text.
  * `text_sections` and planning-sheet parsing, and review READY front-matter parsing.
  * registry YAML round-trip, file-limits engine merge/exclude semantics, history events.
* **Assertions.** Prefer structured results (return objects, JSON output, exit codes, error codes or keys) over prose. Keep exactly one message-contract table, for example `refusals_name_their_fix`, that asserts each refusal names a runnable next step. Other tests should assert the code or kind, not the sentence.

### Staged plan (each stage keeps the suite green and coverage flat or higher)

0. **Instrument (1 day).**
   * Add an opt-in `make test-coverage-contexts` that reproduces this analysis: arc-level contexts, including subprocesses via a `sitecustomize` hook or coverage `patch = subprocess`.
   * Record a baseline of the arc set, coverage %, and `--durations`.
   * Add a coverage ratchet to CI (fail below 89% line+branch).
   * Mark `slow` (> 1 s) and `repo` tests.
1. **Consolidate fixtures, no deletions (2–3 days).**
   * Create `tests/support/`.
   * Move the 53 identical helper groups and the 11 `*_repo_helpers` there.
   * Replace all 98 cross-test-file imports.
   * Introduce `roadmap_repo` and the session-cached git template, and migrate the heaviest files first: `doctor_live`, `pickup_register_digest`, `review_*`, `brainstorm_cli`.
   * Gate: same item count, same arc set.
2. **Re-home files, no deletions (2 days).**
   * Fold the 32 per-leaf/per-round files and the ≤5-test files into per-module files under the new layout.
   * Rename tests for the behaviour they check. Keep finding ids only as comments or param ids.
   * Gate: identical node count, identical arc set.
3. **Deduplicate with a worklist (incremental, per module).**
   * Work through the identical-arc groups (390) and the ≥0.95 Jaccard pairs (1,102 non-param).
   * For each pair, decide (a) delete, (b) fold into a table, or (d) keep.
   * Each PR must show an unchanged arc set for the touched modules. Where many tests of one module go at once, optionally run `mutmut`/`cosmic-ray` on that module to confirm surviving mutants did not increase.
   * Convert subprocess CLI tests to in-process except the smoke lane.
4. **Fix the seams (ongoing).** Replace private-name monkeypatching with public injection points (runner, clock, client factory, cmdline reader) and rewrite those ~150–200 tests against them. Replace sleep-based timing tests with an injectable clock.
5. **Fill the gaps.** Milestone session and rollup git, `milestone_chunk_io`, `reconcile_milestone_status` states, `roadmap_outline_ops`, `roadmap_edit_fields`, archive auto/restore errors, `update_specy_road`. Decide whether `migrate_stable_node_keys` is dead.

### Rule for review-finding regression tests

Add a **new test function** for a review finding only when all of these hold:

1. **It reproduces red-green.** It fails on the pre-fix code and passes after.
2. **It is not a row.** If the failing case is a new input to behaviour that already has a test or table in that module's test file, add a parametrize row (with the finding id as the param id) instead of a function.
3. **It checks a distinct behaviour.** Either it adds unique arcs or branches (checked with the contexts job), or it asserts an outcome no existing test asserts (a race, a crash-recovery path, a git-semantics edge). Otherwise strengthen the existing test's assertions.
4. **It is cheapest-level.** Reproduce at the unit level if possible. Use a git repo only for git semantics, and a subprocess only for entry-point and exit-code contracts.
5. **It lives with its module** and is named for the behaviour, never `round6`, `s5`, `m11_27` or `fixes`. The finding id goes in a comment.
6. **It asserts structure, not prose,** unless the message itself is the contract.

Findings that only change wording, or that are already caught by an existing assertion once the code is fixed, need no new test.

## Appendix: data files (scratchpad)

* `analysis/data/junit.xml`, `durations.json`: baseline run
* `analysis/data/covreport.txt`, `cov.json`: combined coverage report
* `analysis/data/uniq.json`, `redund2.json`: per-test unique arcs, dominators, zero-unique files
* `analysis/data/jacc.json`: nearest neighbour and Jaccard for every zero-unique test (the stage-3 worklist)
* `analysis/data/greedy.json`, `greedy_time.json`: minimal covering sets
* `analysis/data/inv.json`, `inv023.json`, `helpers_dup.txt`: static inventory, now and at v0.2.3
* `cov/all/.coverage`: combined SQLite coverage data with per-test contexts (~150 MB)
* Scripts: `analysis/inventory.py`, `redund.py`, `redund2.py`, `jacc.py`, `show.py`, `subsys.py`; coverage hooks in `covhook/`
