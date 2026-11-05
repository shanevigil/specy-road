# 01 — Code heft, efficiency and coherence (specy_road/ + scripts/)

**Snapshot:** WIP `b216d799` (`snap/`), compared with the v0.2.3 release (`snap-v023/`).
**Method:** read-only. `wc`, AST scripts (import graph, SCCs, call/name references, density), vulture 2.16, radon cc, pylint R0801 at 4 lines, `python -X importtime`. Scripts are in `scratchpad/tools/`; raw outputs are in `scratchpad/analysis/` (`imports.json`, `vulture_*.txt`, `radon.json`, `dup4.txt`, `subsys.txt`).
**Prior work:** `docs/design-notes/lean-code-census.md` (2026-10-27, measured at 39.7k source lines) covers the *test* suite: coverage overlap, private-name coupling and unexecuted guards. This note covers the *source* and doesn't repeat that work. Where the census made a finding, this note says whether it still holds. Example: the census counted six `_now()` copies, and there are now nine.

---

## 0. Headline numbers

| metric | v0.2.3 | now | × |
|---|--:|--:|--:|
| `.py` files (specy_road + scripts) | 175 | 349 | 2.0 |
| lines | 31,553 | 66,724 | 2.1 |
| **characters** | 1.07 M | 2.66 M | **2.5** |
| lines > 100 chars | 78 | **3,068** | 39 |
| lines > 120 chars | 4 | 197 | — |
| functions | 1,339 | 3,196 | 2.4 |
| radon CC ≥ C (≥11) functions | 94 | **313** | 3.3 |
| `# noqa: C901` waivers | 0 | 22 | — |
| trailing (end-of-line) comments | 51 | 611 | 12 |
| milestone/slice/round refs in code (`M11.68`, `slice 7b`, `round 6`) | — | 127 | — |
| function-level (lazy) internal imports | 101 | 184 | 1.8 |
| files within 20 lines of the 400 cap | 8 | **38** | 4.8 |
| CLI subcommands (`add_parser` + dispatch tables) | 28 | 99 | 3.5 |
| distinct long flags | — | 237 (17 undocumented) | — |
| modules imported by `validate` at startup | 31 | **110** | 3.5 |
| modules imported by `finish-this-task` at startup | 36 | 108 | 3.0 |
| modules imported by `do-next-available-task` at startup | 64 | 147 | 2.3 |

**Key observation:** the 400-line cap is now partly *dodged by width* instead of honoured by design. Characters grew 2.5×, but lines grew only 2.1×. The average line went from 34 to 41 characters, and lines over 100 characters went from 78 to 3,068. Measured at v0.2.3's average line width, today's code is about **77.6k lines**, not 65k.

**What is *not* the problem** (each measured, so it can be ruled out):
- **Literal copy-paste:** pylint R0801 at a 4-line threshold finds 44 clone groups, about 333 duplicated lines in total. The clone gate (`scripts/check_clones.py`, a 9-pair baseline) works.
- **Dead code:** 6 functions with no references at all (47 lines) and 13 called only by tests (137 lines). The only whole unused or unwired modules are `behaviour_changes.py` (144) and `migrate_stable_node_keys.py` (112). The total is about 440 lines.
- **Undocumented flags:** 17 of 237.

**What is the problem:**
1. **New feature surface.** The worker/orchestration and review subsystems account for 53% of all growth.
2. **Fragmentation from the cap**, made worse by import cycles and module-level re-export shims.
3. **Semantic re-implementation.** The same rule (dependency readiness, roster eligibility, "is this a worktree root on branch X", atomic write, `now()`) is written again in each subsystem with a slightly different message, instead of being imported.

---

## 1. Module map by subsystem

Each module was assigned by name pattern; see `tools/subsys.py`. The full per-file list is in `analysis/subsys.txt`.

| subsystem | v0.2.3 files | v0.2.3 lines | now files | now lines | Δ lines | growth |
|---|--:|--:|--:|--:|--:|--:|
| worker/orchestration | 2 | 332 | 65 | 12,155 | +11,823 | 36.6× |
| review/handoff/gate | 3 | 1,135 | 40 | 8,099 | +6,964 | 7.1× |
| pickup/grind (do_next_*, grind_session_*, session_plan*) | 22 | 4,307 | 28 | 5,690 | +1,383 | 1.3× |
| upgrade/init/templates/agent files | 15 | 2,303 | 31 | 5,625 | +3,322 | 2.4× |
| finish/land (finish_*, milestone_*, nested_repos*) | 22 | 2,974 | 31 | 5,024 | +2,050 | 1.7× |
| brainstorm | 9 | 2,271 | 19 | 4,983 | +2,712 | 2.2× |
| roadmap graph/CRUD | 22 | 4,038 | 24 | 4,973 | +935 | 1.2× |
| registry/git/worktree/doctor | 12 | 1,965 | 26 | 4,535 | +2,570 | 2.3× |
| archive/history/search | 19 | 4,260 | 19 | 4,302 | +42 | 1.0× |
| PM UI server (gui_app*, roadmap_gui_*, pm_*) | 23 | 3,489 | 24 | 3,705 | +216 | 1.1× |
| brief/digest/export/planning | 14 | 2,619 | 17 | 3,281 | +662 | 1.3× |
| validate/file-limits | 6 | 1,131 | 11 | 2,359 | +1,228 | 2.1× |
| scripts/ (maintainer gates, census) | 3 | 252 | 11 | 1,341 | +1,089 | 5.3× |
| cli dispatch | 3 | 477 | 3 | 652 | +175 | 1.4× |
| **total** | **175** | **31,553** | **349** | **66,724** | **+35,171** | **2.1×** |

Breakdown of worker/orchestration (12.2k lines):

| part | lines | files |
|---|--:|--:|
| `worker_*` runtime (adapters, runner, lease, state, reconcile, ops) | 5,277 | 31 |
| roster, model profiles, `orchestrate plan`, harness facts | 3,251 | 16 |
| shared-checkout guard + session presence (`tool_call_guard*`, `session_*`, `orchestration_role_guard`) | 1,717 | 10 |
| chores, decisions, lessons | 1,284 | 6 |
| role prompts (`role_prompt*`) | 818 | 4 |

"Agent-file management" cuts across subsystems: managed blocks, stubs, skills, hooks, ignores, `harness_instruction_files`, `validate_stale_commands`, `version_skew`/`version_pin`, `behaviour_changes`. It went from 1,241 lines to **3,813**.

Subsystems with almost no growth since v0.2.3: archive/history/search, the PM UI server and the roadmap graph. Most of the lean-up opportunity is in worker, review, finish, pickup and agent-file code.

---

## 2. Fragmentation

### 2.1 Evidence that the cap drives splits
- **49 modules (8,225 lines) say in their docstring that they were split for the cap or for C901.** Examples: `worker_cli_args.py` (24 lines, "split from worker_cli for the file limit"), `role_prompt_stream.py` (28), `worker_lock.py` ("split from worker_state for the file limit"), `review_packet_observed.py` ("review_packet.py (at its line cap) imports"), `brainstorm_cli_revise.py` ("extracted so cmd_revise stays under C901") and `cli_usage.py`. Another 67 inline comments cite the cap.
- **38 files sit at 380–400 lines.** Each is one change away from the next split.
- **`worker_ops.py` is a facade that exists only because of the split.** It re-exports about 30 names, including private ones, from four `worker_ops_*` parts. It then replaces its own module class (`sys.modules[__name__].__class__ = _Facade`) so that `monkeypatch.setattr(ops, …)` in tests reaches every part. Its docstring gives the reason: "so leaves that change one step do not collide". The split serves parallel agents' merge conflicts and test patch targets, not readers.
- **19 modules carry 37 "re-exported" import lines** kept for callers or tests.
- **`brainstorm_cli_v2.py` and `brainstorm_cli_args_v2.py` are not a second implementation.** They hold the overflow subcommands of one CLI, so the "v2" names are misleading. Five files total 1,439 lines for about 20 subcommands, and `_load()` is defined twice (`brainstorm_cli.py:62`, `brainstorm_cli_v2.py:59`).

### 2.2 Single-importer siblings
- **93 modules (13,717 lines) have exactly one importer**, not counting tests and CLI entry points.
- **75 of those (11,149 lines) share a name prefix with their only importer.** Examples: `do_next_task_*` → `do_next_task`, `review_packet_*` → `review_packet`, `grind_session_*` → `grind_session`, `gui_app_routes_*` → `gui_app_api` (a 33-line aggregator), `worker_ops_*` → `worker_ops`.
- **92 modules are under 100 lines** (5,569 lines in total).

### 2.3 How many could merge

The simulation repeatedly folds a single-importer module into its importer while the result stays under the cap. It only counts header lines (docstring plus imports) of the folded module as saved.

| cap | modules merged | files after | header lines removed (upper bound) |
|--:|--:|--:|--:|
| 600 | 72 | 266 | ~1,630 |
| **800** | **88** | **250** | **~1,990** |
| 1,000 | 99 | 239 | ~2,230 |

Some imports would survive a merge, so the realistic saving is about 60% of the upper bound: **~1,000–1,300 lines and ~90 fewer files at an 800-line cap.** On top of that, about 60 re-export and facade lines go away, and a large share of the 184 lazy imports that exist only to break cycles between siblings.

The best candidates are in Appendix A.

---

## 3. Duplication and near-duplication

Literal duplication is low (§0). The repetition is semantic: the same rule rewritten with different names and messages.

| pattern | where (file:line) | copies | removable lines |
|---|---|--:|--:|
| **Unmet effective dependencies / readiness** | `bundled_scripts/do_next_available.py:124-136` and `:194-205` (two forms in one file); `session_plan.py:128-139`; `roadmap_explain.py:71-75`. Effective-dependency maps are also built in `roadmap_layout.py:62`, `brief_dependency_context.py:133`, `digest.py`. Across the package there are 44 ad-hoc `{n["id"]: n …}` / `{n["node_key"]: n …}` index builds, 14 linear `next(n for n in nodes if n["id"]==…)` lookups and 79 `load_roadmap()` calls, each returning a bare dict. | 4 + 44 + 14 | 250–400 with one `RoadmapIndex` (by_id, by_key, status, unmet, ready) |
| **Roster / eligibility preconditions** ("not in the roster", sensitivity, executor class, availability) | `bundled_scripts/role_prompt.py:173-203`; `worker_ops_launch.py:55-89`; `review_delegate.py:70-77`; `review_eligible.py:73-85`; `review_gate.py:203,359`; `orchestrate_assign.py:175`. The message strings are duplicated nearly verbatim. | 5–6 | 60–80 |
| **"Is this directory a worktree root with branch X?"** | `worker_ops_launch.py:92-101`; `bundled_scripts/chore_cli.py:109-115`; `worktree_delete_set.py:54-56`; `session_overlap.py:62`. `rev-parse --show-toplevel` is inlined 15 times although `runtime_paths.git_root` exists, and `branch --show-current` is inlined 10 times although `git_subprocess.current_branch_name` exists. | ~25 sites | 40–60 |
| **Private git wrappers beside `git_subprocess`** | `worktree_delete_set.py:24-45` (`git_run`/`git_out`/`git_path`); `bundled_scripts/update_specy_road.py:65-95` (`_git_output`/`_git_succeeds`/`_git_toplevel`); `bundled_scripts/repo_ops.py:33-47`; `ignore_report.py:71`; `integrity.py:196`; `pm_publish.py:47`. There are 52 `subprocess.run/Popen` sites overall. | 6 modules | 60–90 |
| **`now()` helpers** | `session_presence.py:67`, `worker_witness.py:33`, `reviewer_run_failure.py:24`, `worker_lease.py:51`, `worker_outbox.py:24`, `grind_session_events.py:34`, `decisions.py:103`, `worker_turn_check.py:74`, `worker_state.py:118`. There are 20 inline `datetime.now(timezone.utc)` calls. The census found 6 copies, so this has grown since. | 9 | 25 |
| **Atomic write (tmp + `os.replace`)** | `worker_state.py:122` (and `worker_outbox.py:28` delegates to its *private* function); `history_cache.py:76-97`; `bundled_scripts/brainstorm_session.py:352-359`; `bundled_scripts/roadmap_chunk_atomic.py:78-85`; `reviewer_run_failure.py:40`; `worker_lease.py:206`. Other record writers use non-atomic `write_text`. | 6 | 30–40 |
| **LLM provider client** | About 345 lines of Azure/OpenAI/Anthropic client code live inside the *CLI script* `bundled_scripts/review_node.py:396-740`, which is why that file has a 900-line override. `brainstorm_chat.py:27-35,101-145` imports its underscore-private helpers and re-implements `_complete_anthropic`/`complete_chat`. `roadmap_gui_remote` and two GUI route modules also reach into `review_node`. | 2 | 50–80, and the override goes away |
| **Registry I/O one-liners and constants** | `_save_registry` is defined identically in `finish_task.py:76`, `mark_implementation_reviewed.py:51` and `abort_task_pickup.py:86`. `REGISTRY_REL` is defined in `registry_yaml.py:31`, `pm_integration_registry.py:20`, `registry_remote_overlay_merge.py:21` and `review_target.py:37`. | 3 + 4 | 15 |
| **Session files** | `milestone_session.py` and `on_complete_session.py` (a 17–26-line clone in the baseline). | 2 | 20 |
| **Error → exit formatting** | 15 unrelated exception classes with no shared base (`WorkerError`, `ReviewError`, `DelegateError`, `BrainstormError`, …), 226 `SystemExit`/`sys.exit` sites and 159 `print("error: …", file=sys.stderr)` sites. `cli_entry.run_cli` exists but only 6 scripts use it. | — | 100–150 if one `SpecyError` is handled once in `run_cli` |
| **Argparse** | 58 parser-building functions (1,755 lines). `--json` is declared 29 times, `--ref` and `--model` 8 times each, `--base`/`--remote` 4–5 times with copy-pasted help. | — | 60–100 with shared `add_ref_arg` / `add_base_remote_args` |

**Estimated removable lines from de-duplication: ~700–1,000.**

---

## 4. Dead or barely used code

Found by an AST name-reference scan across specy_road, scripts and tests, cross-checked with vulture at 60%. Confidence is high for the "dead" rows. The scan matches by name only, so these are upper bounds on liveness: a name could still be reached through `getattr`, but none of these look like that.

**No references anywhere** (47 lines, high confidence):
- `roadmap_chunk_utils.resolve_chunk_file` (17)
- `finish_land_integration.integration_commits_ahead_of_remote` (14)
- `milestone_session.remove_milestone_session` (5)
- `roadmap_gui_settings_tokens._obfuscate_llm_git` (5)
- `upgrade_templates.missing_work_template_rels` (4)
- `worker_adapter_parsers.has_prompt_placeholder` (2)
- Unused locals and attributes: `registry_yaml.py:24 indentless`, `worker_cli_args.py:22 option_string`, `specyrd_hooks.HOOKS_REL`, `integrity_removals.REMOVAL_KEY`

**Referenced only by tests** (137 lines, high confidence they are production-dead):
- `export_roadmap_md.render_phase_doc` (36)
- `upgrade_templates.upgrade_help_step_labels` / `readme_upgrade_step_labels` (36)
- `managed_block.remove_managed_block` (13)
- `planning_sheet_bootstrap.ensure_planning_sheet_for_new_node` / `remove_planning_sheet_if_present` (19)
- `review_record_rules.defect_word`, `worker_state.set_lease` / `record_intervention`, `roadmap_layout.compute_depths`, `history_index.clear_memo`, and test-reset hooks in `llm_throughput` and `review_node`
- `review_packet.py:44` imports `test_integrity_section` and never uses it

**Whole modules:**
- `behaviour_changes.py` (144): imported only by its test. Its docstring says a later leaf (M13.14) "wires these patterns into validate", and that hasn't landed. This is a speculative catalogue.
- `bundled_scripts/migrate_stable_node_keys.py` (112): no importer, not in the CLI, no tests, and no docs outside its own docstring. It is a one-time migration for pre-stable-key roadmaps.

**CLI overlap and aliases** (coherence more than dead code):
- **Cleanup.** `doctor --fix` already covers merged branches, stale worktrees, registry rows and stashes. It imports `branches_cli` functions and even shells out to `registry_prune` (`doctor.py:143`). `branches prune`, `registry-prune` and `worktree prune` remain separate commands, an automatic orchestrator cleanup is being built (commit `72e34813`), and `finish-this-task --delete-branch` and `grind-session --delete-merged-branches` add more. That is five or six ways to clean up after landed leaves.
- **Status and listing.** `handoff status` and `review list` both read `work/reviews/` and evaluate the gate. Both, plus `ready`, dispatch to `review_cli.py`.
- **Archiving.** `archive-node` is self-described as "legacy hard-remove" next to `archive`.
- **`update` vs `upgrade`.** `update` fast-forwards a toolkit git clone; `upgrade` refreshes a consumer repo after a pip upgrade. The names don't say which is which.
- **`specyrd`** is a second console entry point with exactly one subcommand (`init`), next to `specy-road init project|gui`.
- **"session" means five things:** `grind-session`; `session start|end|list|check|guard` (presence records); `start-milestone-session`; `.on-complete-<id>.yaml` session files; and harness-native session ids in `worker_sessions.py`. `session_plan.py` is actually the grind-session plan.

**Total dead or unwired: ~440 source lines, plus their tests.**

---

## 5. Coherence and layering

**`bundled_scripts/` is half library.**
- It holds 150 modules: 48 CLI entry points (11,975 lines) and **102 library modules (19,560 lines)**.
- 29 of those library modules are imported by package-level `specy_road/*.py` code. The package has **105 import edges from 51 package modules into `bundled_scripts`**.
- 16 *entry-point scripts* are imported as libraries:
  - `generate_brief` by 8 modules
  - `chore_cli` by 6 (including `worker_ops_message`, `review_delegate`, `worker_reconcile`)
  - `role_prompt` by 3
  - `review_node` by 4
  - `validate_roadmap` by 4
  - `refresh_stubs` by `version_pin` and `validate_roadmap`
  - `grind_session_cleanup.merged_into` by `doctor_worktrees`, `worktree_prune` and `finish_modes`

**Import cycles (strongly connected components):**
- **One 45-module SCC** that spans `cli`, `specyrd_cli`, `init_project`, `roadmap_load`, `digest`, `generate_brief`, `review_gate`/`review_files`/`review_target`/`review_rca`, `orchestration_config`/`orchestration_pinned`, `worker_state`, `decisions`, `validate_stale_commands`, `finish_ancestor_rollup` and others. It is held together by 23 function-level imports. `roadmap_load` (the graph loader) lazily imports `finish_ancestor_rollup`, which lazily imports five `review_*` modules.
- **One 25-module SCC** joins roadmap CRUD (`roadmap_crud_ops` ↔ `roadmap_chunk_router` ↔ `roadmap_crud_dependency_ops` ↔ `roadmap_crud_argparse`) with the worker ops and chore CLI.
- **11 smaller cycles**, for example `nested_repos` ↔ `nested_repos_land` ↔ `finish_implementation_check`, `brainstorm_promote` ↔ `brainstorm_prompt`, and `grind_session` ↔ `grind_session_step`.

**Effect:**
- Import fan-out at startup is 3–3.5× larger than in v0.2.3 (§0).
- Every command runs in a **child process**: `cli._run` → `python -m specy_road.bundled_scripts.X`. Measured costs:
  - `specy-road --version`: 113 ms
  - `validate --help`: ~400 ms
  - `worker --help`: 475 ms
  - bare interpreter: 38 ms
- Some scripts start yet another interpreter for a sibling command:
  - `doctor.py:143` (`registry_prune`)
  - `mark_implementation_reviewed.py:324` (`specy_road.cli`)
- Some code exists only to pass arguments across that process boundary:
  - `cli._args_repo_root_first`
  - `cli_entry.run_forwarded_cli`, which strips the command name again
  - `orchestration_guard_cli` "drop prefixes forwarded by cli"

**Naming:**
- `*_cli.py`, `*_args.py`, `*_argparse.py` and `*_cli_args*.py` all mean "argparse for X".
- `review_defer.py` (CLI) sits next to `review_deferral.py` (rules). `review_gate.py`, `review_gate_ready.py` and `review_ready_merge.py` split one concept three ways.
- `roadmap_gui_*` lives in `bundled_scripts/` while `gui_app_*` lives in the package.
- Six bundled scripts still use a module-level `ROOT = Path.cwd()` with `global ROOT`, which is incompatible with in-process dispatch.

---

## 6. Defensive-patch accretion

**Indicators:**
- CC ≥ 11 functions went from 94 to 313.
- 22 `noqa: C901` waivers, all reading "baseline 2026-10-28; simplify, then drop this".
- 611 trailing comments explain a special case in place (up from 51).
- 127 milestone, slice or review-round references are embedded in code comments and docstrings, for example `worker_sessions.py` "(review round 6, B13)".

**Worst hotspots** (radon CC, length):

| function | CC | shape |
|---|--:|---|
| `tool_call_guard.classify_segment` (`tool_call_guard.py:192`) | **83** | A shell-syntax denylist grown adversarially: nested `$()` up to 8 levels, `eval`, `sh -c` flag variants, unbalanced quotes, then about 15 git-verb special cases. It continues in `_opaque` (CC 30), `_git_subcommand` (CC 20) and `tool_call_guard_shapes.py`. Test files `test_tool_call_guard` (70 tests) and `test_review_round6_guard` (67) are 90%+ zero-unique-coverage per the census. This is an arms race with shell syntax. |
| `role_prompt.build_prompt` (`bundled_scripts/role_prompt.py:167`) | 45 | Roster, availability, sensitivity and eligibility checks (duplicated in `worker_ops_launch`), then a four-role `if/elif` assembling text. |
| `session_plan._classify` / `_compute_waves` | 28 / 26 | Readiness rules re-derived (see §3). |
| `brainstorm_fields.parse_extra` | 28 | — |
| `specyrd_skills.ensure_link` | 28 | Per-harness symlink/copy edge cases. |
| `review_deferral._block_problems`, `review_next_step.facts` | 27 / 26 | The fix-round, RCA and deferral policy engine. |
| `roadmap_crud_argparse.expand_list_edits`, `orchestrate_cli.render`, `model_profiles._structure_errors`, `roadmap_layout.compute_dependency_steps`, `worker_reconcile._reconcile_locked` | 25–27 | — |

**Accretion at file level** (grew 2–3× inside a file that existed at v0.2.3):

| file | v0.2.3 | now |
|---|--:|--:|
| `roadmap_crud_dependency_ops` | 129 | 398 |
| `finish_land_integration` | 115 | 383 |
| `finish_ancestor_rollup` | 96 | 292 |
| `finish_modes` | 166 | 351 |
| `init_project` | 103 | 266 |
| `validate_roadmap` | 148 | 359 |
| `brainstorm_cli_args` | 173 | 386 |

**Review-loop escalation machinery** is 1,517 lines: `review_rca`, `review_deferral`, `review_defer`, `review_next_step`, `rework_rca`, `role_prompt_rca`, `role_prompt_rework`. It encodes fix-round budgets, RCA triggers, deferral binding and protected criteria. Of all the review code, this part was most clearly shaped by successive review findings.

---

## 7. Top 15 simplification opportunities

**Ranking.** Score = estimated lines removed × risk weight (low = 1.0, medium = 0.5, high = 0.25), with ties broken by coherence gain. The estimates overlap: #1 shares header lines with #5, #9, #13 and #14. **The de-duplicated total of items 1–11 and 13–15 is ~4,000–4,500 lines (6–7%) and ~100 fewer files.** Larger cuts need product decisions (#12 and the feature notes after the table).

| # | opportunity | files | rationale | est. lines saved | risk | score | guarding tests |
|--:|---|---|---|--:|---|--:|---|
| 1 | **Fold single-importer siblings into their parent under an 800-line (or per-subsystem) cap** | 88 modules; Appendix A | Of the 93 single-importer modules, 75 are named siblings and 49 say in their docstring that they exist for the cap. Folding removes headers, the re-export shims and the `worker_ops` `_Facade` hack, and most sibling cycles. Allow the cap at 800 *and* enforce a 100-character width at the same time, so the cap stops being dodged by line width. | 1,000–1,300 | low–med (pure moves; tests patch module attributes, and the private-import baseline has 120 entries) | ~900 | full `pytest -n auto`; `scripts/check_test_private_imports.py` and `check_clones.py` (update their baselines); `specy-road file-limits` |
| 2 | **Delete dead and unwired code** | `behaviour_changes.py`, `bundled_scripts/migrate_stable_node_keys.py`, the 19 functions in §4, the unused import at `review_packet.py:44` | No production caller. `behaviour_changes` waits on an unbuilt leaf; reintroduce it with its consumer. | ~440 (+ ~150 test lines) | low | 440 | `tests/test_behaviour_changes.py` (delete with it); remaining suite; vulture in CI as an advisory gate |
| 3 | **One `RoadmapIndex` for graph queries** (by_id, by_key, statuses, effective deps, `unmet()`, `ready()`) | `do_next_available.py:124-205`, `session_plan.py:128-170`, `roadmap_explain.py:71`, `roadmap_layout.py:62`, `brief_dependency_context.py:133`, `digest.py`, 44 index builds, 14 linear lookups | Pickup, `grind-session --plan`, `why-blocked`, the brief and the digest each re-derive readiness. Today they agree by test, not by construction. | 250–400 | medium | 160 | `test_do_next_queue`, `test_session_plan*`, `test_cli_query_commands`, `test_why_blocked_plan_holds`, `test_generate_brief*`, `test_digest`; `specy-road digest --check` / `export --check` on the dogfood fixture (byte-identical output) |
| 4 | **Consolidate cleanup commands under `doctor`** (`--kind branches\|registry\|worktrees\|stashes`). Keep `worktree prune <ID>` as the single-leaf safe path. Have the orchestrator auto-cleanup call the same planner. | `bundled_scripts/branches_cli.py`, `registry_prune.py`, `doctor.py` (including its subprocess at `:143`), `doctor_worktrees.py`, `grind_session_cleanup.py` | Five or six overlapping cleanup paths, each with its own "merged?" and "live?" logic and its own confirmation UX. `merged_into` lives in a grind CLI module. | ~300 + usage/docs | medium (public CLI; use `REPLACED_COMMANDS` in `cli.py:107` for aliases) | 150 | `test_doctor*`, `test_branch_cleanup`, `test_registry_prune`, `test_worktree_prune`, `test_grind_session_cleanup`; `validate_stale_commands` tests |
| 5 | **Extract `llm_client.py` from `review_node.py`** | `bundled_scripts/review_node.py:396-740`, `brainstorm_chat.py:27-145`, `roadmap_gui_remote.py`, `gui_app_routes_brainstorm.py`, `gui_app_routes_workspace.py`, `llm_throughput.py` | The provider client lives in a CLI script, is imported by underscore name from four modules, and is re-implemented in `brainstorm_chat`. Extracting it removes the 900-line override for `review_node`. | 80–120 | low | 100 | `test_review_node` (18, several private), `test_brainstorm_chat`, `test_llm_throughput`, `test_gui_app_brainstorm`, `test_roadmap_gui_remote` |
| 6 | **Shared helpers for git, time and atomic writes.** Use `git_subprocess.git_root`/`current_branch_name`/`is_worktree_root(path, branch)` everywhere; add one `utc_now()` / `utc_now_iso()` and one `atomic_write_text()`. | §3 rows: `worktree_delete_set.py:24-56`, `update_specy_road.py:65-95`, `repo_ops.py:33-47`, `ignore_report.py:71`, `integrity.py:196`, `pm_publish.py:47`, 25 inline `show-toplevel`/`show-current` calls, 9 `_now`, 6 atomic writers | Mechanical, and it removes drift. For example, `worker_outbox` currently imports a *private* `worker_state._write_atomic`. | 150–200 | low | 175 | `test_git_subprocess`, `test_worktree_prune`, `test_update_specy_road`, `test_worker_state`, `test_history_cache`, `test_brainstorm_session`; full suite |
| 7 | **One `check_assignment(config, model, node, role)`** for roster, role, availability, sensitivity and executor class | `role_prompt.py:173-203`, `worker_ops_launch.py:55-89`, `review_delegate.py:70-77`, `review_eligible.py:73-85`, `review_gate.py:203,359` | The same five rules are written five times with near-identical messages. A divergence would let `worker delegate` launch a model that `prompt` would refuse. | 60–80 | low | 70 | `test_models_and_prompt`, `test_worker_cli` (delegate), `test_review_eligible`, `test_review_gate*`, `test_orchestrate_plan` |
| 8 | **Move library code out of `bundled_scripts/` and break the 45- and 25-module SCCs** | the 102 library modules (start with the 29 that the package imports: `roadmap_load`, `roadmap_chunk_utils`, `roadmap_crud_ops`, `brief_acceptance`, `roadmap_layout`, `generate_brief.render_brief`, `chore_cli`'s store, `grind_session_cleanup.merged_into`, `review_node`'s LLM client) | Package code imports CLI scripts, and `roadmap_load` lazily imports the review gate. 184 function-level imports exist mostly to dodge cycles. Startup imports went from 31 to 110 modules for `validate`. | 150–250 (lazy imports + re-exports), plus faster startup | medium (import paths in tests and `monkeypatch` string targets) | 100 | full suite; an import-graph check in CI ("package must not import bundled_scripts entry points"); `-X importtime` budget for `validate` |
| 9 | **Dispatch subcommands in-process** (`importlib` + `main(argv)`) instead of `python -m` per command | `cli.py:203-221` (`_run`), `cli.py:182-200`, `cli_entry.run_forwarded_cli`, `orchestration_guard_cli.py:61`, `doctor.py:143`, `mark_implementation_reviewed.py:324`; 6 scripts with `global ROOT` | Saves an interpreter start and a second import of the package on every command (~100–150 ms each, worse in grind and orchestration loops). It also removes the code that only passes arguments across the process boundary. | 80–120 | medium (module-level `ROOT`/state and `SystemExit` semantics; about 220 tests already drive the CLI by subprocess and will catch regressions) | 50 | CLI subprocess tests (`test_cli*`, `test_*_cli`, `test_cli_imports_without_gui_extra`); time `specy-road validate --help` before and after |
| 10 | **Review subsystem, mechanical part.** Fold `review_ready_merge` (41), `review_bookkeeping` (57), `review_gate_agreement` (54), `review_strong` (83), `review_resumed_delta` (70) and `review_policy_ref` (129) into `review_gate`/`review_policy`. Merge `handoff status` and `review list` into one read command. Rename `review_defer`/`review_deferral`. | `specy_road/review_*.py`, `bundled_scripts/review_cli.py`, `review_packet_*` | 40 modules for one gate; three read paths over `work/reviews/`. | ~300 | medium | 150 | `test_review_gate*`, `test_review_cli*`, `test_mark_implementation_reviewed*`, `test_review_packet*` |
| 11 | **Brainstorm CLI from five files to two** (parser, handlers). Drop the "v2" names and de-duplicate `_load`/`_slug`. | `bundled_scripts/brainstorm_cli*.py` (1,439 lines) | The split follows the cap, not the design. "v2" misleads. | 100–150 | low | 125 | `test_brainstorm_cli*`, `test_brainstorm_v2`, `test_review_round6_brainstorm`, `test_gui_app_brainstorm` |
| 12 | **Replace the shell-parsing guard with a structural rule.** Every live session or worker gets its own worktree (already the worker default `work/.worktrees/<codename>`). Keep presence records and the overlap check, and drop the denylist parser. | `tool_call_guard.py` (399, CC-83 function), `tool_call_guard_shapes.py` (104), `tool_call_guard_adapters.py` (172), parts of `orchestration_role_guard.py`, about 140 guard tests | A denylist over shell syntax can't be complete (each review round adds a shape) and it is the codebase's worst complexity hotspot. Worktree isolation removes the hazard instead of pattern-matching it. | 600–900 (+ ~1,000 test lines) | **high** (safety feature; product decision; the hook adapters for three harnesses depend on it) | 190 | `test_tool_call_guard`, `test_review_round6_guard`, `test_hook_adapters`, `test_session_*`; a new test that a second session without its own worktree is refused |
| 13 | **Agent-file management: one managed-block engine.** Merge `agents_md_block` (400), `agent_guide_block` (106), `managed_block` (196) and `agents_md_report` (136); merge `refresh_stubs` and `refresh_stubs_report`; consider folding `specyrd init` into `specy-road init stubs`, keeping `specyrd` as a thin alias. | §1 agent-file list (3,813 lines, up from 1,241) | Three block writers and two reporters for marker-delimited text in agent files. | 200–300 | medium (`specyrd` is a published entry point; keep the alias) | 125 | `test_agents_md_block`, `test_specyrd_init_guide_block`, `test_managed_block`, `test_refresh_stubs`, `test_specyrd_*`, `test_upgrade*` |
| 14 | **Unified error type and exit handling.** Add `SpecyError(msg, code)` as the base of the 15 error classes and handle it once in `cli_entry.run_cli`. Add shared argparse helpers (`add_json_arg`, `add_ref_arg`, `add_base_remote_args`). | the 15 error classes in §3; 226 exit sites; 58 parser builders | Every script hand-rolls catch, print and exit. | 150–250 | low–med | 120 | stderr and exit-code assertions across the CLI tests (the census notes stderr text is asserted via `capsys`, so messages must stay byte-identical) |
| 15 | **Prune and rename the CLI surface.** Retire `archive-node` (legacy) behind `archive --hard-remove`; rename `update` to `self-update`; rename `session` (presence) to `presence`, or `session_plan` to `grind_plan`; register the old names in `REPLACED_COMMANDS`. | `cli.py`, `cli_usage.py`, `roadmap_crud_argparse.py`, templates, `suggested_prompts/` | 99 subcommands. "Session" means five things. `update` and `upgrade` are easily confused. | 100–150 (+ docs) | medium (consumer prompts and docs must move together, per CLAUDE.md maintainer hygiene) | 60 | `test_validate_stale_commands`, `test_cli`, `test_refresh_stubs` (skills and stubs name commands) |

### Feature-level options

These are outside the mechanical total and are decisions for the maintainer, not refactors:
- **Fix-round escalation engine** (RCA, deferral, next-step, rework: 1,517 lines, §6). Ask whether budgets, protected criteria and RCA-driven deferral earn their weight against a simpler "block → rework → re-review, escalate to a human after N rounds".
- **Brainstorm** (4,983 lines plus 300 lines of GUI routes, web search providers and a quote-verification fetcher). It is self-contained and could ship as an optional extra or plugin, which would take ~5k lines out of the core install.
- **Chores, decisions and lessons** (1,284 lines). These are three record types with their own CLI and storage. A single "note" record type with a `kind` field could serve all three.

---

## 8. Governance recommendations

Each one prevents the patterns above from coming back.

1. **Make the cap meaningful.** Set a per-file cap of about 800 for package modules, *together with* a formatter-enforced line width (100). Width is currently the escape valve: 3,068 lines over 100 characters, up from 78. Keep the 80-line function cap and burn down the 22 `noqa: C901` waivers.
2. **Add an import-layering gate** next to `check_clones.py`. Package code must not import `bundled_scripts` entry points, and new SCCs fail the gate. The current SCCs go in a baseline that can only shrink.
3. **Make vulture an advisory CI step** with a whitelist for FastAPI routes and pytest fixtures. It found every dead item in §4 in about one second.
4. **Keep provenance out of code.** Drop milestone, slice and round references from comments (127 now); that history belongs in commits and `sr/`.
5. **Brief agents on the shared helpers before they write their own.** Write and maintain one "shared helpers" section in the agent brief (git, time, atomic write, roster check, roadmap index) so leaf agents reuse them. Most of §3 is leaves re-solving a solved problem without knowing the helper exists.

---

## Appendix A — Fold candidates

Each row is a single importer and a combined size of 800 lines or less. Rows are grouped by subsystem; the simulation merged 88 modules.

- **worker:** `worker_ops_launch` (289), `worker_ops_message` (126), `worker_ops_slots` (81) and `worker_ops_lifecycle` (75) into `worker_ops` (59, with its facade hack removed), ≈630 lines. `worker_cli_args` (24) and `worker_hook` (87) into `worker_cli`. `worker_schema` (39) into `worker_state`. `worker_exit` (54) into `worker_runner`. `worker_witness` (139) into `worker_lease`. `worker_adapter_cursor` (100) and `worker_adapter_claude` (160) into `worker_adapters` (61).
- **pickup/grind:** `do_next_task_virtual_complete` (48), `do_next_task_held_claim` (104), `do_next_task_leaf_guards` (126), `do_next_task_interactive` (135) and `do_next_task_args` (204) into `do_next_task`. `grind_session_limits` (71) and `grind_session_step` (120) into `grind_session`. `abort_task_pickup_own_commit` (59) into `abort_task_pickup`.
- **finish:** `finish_task_gates` (73), `finish_pr_body` (110), `finish_task_args` (134) and `finish_work_artifacts` (199) into `finish_task`. `finish_land_check` (89) into `finish_land_integration`. `nested_repos_land` (250) into `nested_repos` (a cycle today).
- **review:** `review_packet_observed` (59), `review_packet_nested` (80) and `review_packet_uncommitted_refs` (119) into `review_packet`. `review_ready_merge` (41), `review_eligible` (149) and `review_next_step` (178) into `review_cli`. `review_bookkeeping` (57) into `review_gate`.
- **PM UI:** `gui_app_api` (33), `gui_app_routes_publish` (31) and `gui_app_routes_workers` (57) into `gui_app`. `roadmap_gui_pr_pickers` (27) into `roadmap_gui_remote`. `roadmap_gui_settings_tokens` (98) into `roadmap_gui_settings`.
- **misc:**
  - `validate_notices` (20) into `validate_roadmap`; `role_prompt_stream` (28) into `role_prompt`; `brainstorm_cli_revise` (64) and `brainstorm_close` (77) into the brainstorm CLI
  - `doctor_env_setup` (91) into `doctor`; `session_overlap` (100) into `session_cli`; `reconcile_branch` (89) into `reconcile_branch_cli` (55)
  - `orchestration_guard_adapters` (125) and `orchestration_role_guard` (205) into `orchestration_guard_cli` (79)
  - `refresh_stubs_report` (121) into `refresh_stubs`; `upgrade_templates` (161) into `upgrade`; `agents_md_report` (136) into `agents_md_block`
  - `archive_git` (100) into `archive_plan`; `search_fallback` (123) into `search_index`; `file_limits_jsx` (134) into `file_limits_js`; `roadmap_crud_delete` (109) into `roadmap_crud_ops`
  - `bundled_scripts/roadmap_crud.py` (17, a three-line `main`) into `roadmap_crud_argparse`; `registration_pickup_commit` (14) into `do_next_task`

## Appendix B — Reproduce

```
S=<scratchpad>
python3 $S/tools/subsys.py $S/analysis/now_files.txt $S/analysis/old_files.txt   # §1 table
python3 $S/tools/imports.py $S/snap $S/analysis/imports.json                      # fan-in, SCCs, lazy imports
python3 $S/tools/deadfn.py $S/snap                                                # §4 dead / tests-only
python3 $S/tools/density.py $S/snap $S/snap-v023                                  # comments, docstrings, function length
$S/venv/bin/vulture specy_road scripts tests --min-confidence 60
$S/venv/bin/radon cc -s -n C -j specy_road scripts
$S/venv/bin/pylint --disable=all --enable=duplicate-code --min-similarity-lines=4 --ignore-imports=y --ignore-docstrings=y --ignore-comments=y --ignore-signatures=y specy_road
```
