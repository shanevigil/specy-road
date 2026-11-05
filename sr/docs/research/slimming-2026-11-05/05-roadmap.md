# 05 — Roadmap and feature-surface review (slimming input)

Read-only review of the specy-road toolkit at WIP HEAD `b216d799` (snapshot `scratchpad/snap`), compared with the v0.2.3 snapshot (`scratchpad/snap-v023`). Nothing under the live checkout was modified. Working data: `scratchpad/analysis/work05/` (task list, capability map script, per-capability counts, review-record counts).

## 0. Headline numbers

| Measure | v0.2.3 (2026-09-09) | WIP HEAD (2026-11-05) | Change |
|---|---|---|---|
| Python source lines, `specy_road/**/*.py` | 31,301 | 65,383 | +109% |
| Python test lines, `tests/*.py` | 25,228 | 65,323 | +159% |
| Modules (`specy_road/*.py` + `bundled_scripts/*.py`) | 82 + 94 | 192 + 151 | +95% |
| Top-level CLI commands (`cli.py` tables) | 45 | 68 | +23 |
| `add_parser` calls (all subcommand levels) | 28 | 99 | ×3.5 |
| `add_argument` calls | 182 | 463 | ×2.5 |
| `git-workflow.yaml` keys | 12 | 20 (+`env_setup`, `grind`, `nested_repos` sub-objects) | +8 |
| `orchestration.yaml` | did not exist | 19 roster fields + 4 channel kinds + 18 policy keys + `substitutions` | new |
| Project config files | 3 (manifest, registry, git-workflow) | 6 (+ orchestration, decisions, harness-facts) | +3 |
| Docs, `docs/**/*.md` | 6,365 | 14,524 | ×2.3 |
| Shipped templates | 55 files / 970 md lines | 107 files / 3,452 md lines + 32 model-profile files (3,759 lines) | ×3.5 |
| Non-merge commits touching `specy_road/` or `tests/` | — | 751 since v0.2.3 | — |
| Roadmap tasks | — | 232 (194 Complete, 38 Not Started) | — |
| Review records filed (`sr/work/reviews/M*`, including `history/`) | — | 1,441 across 204 nodes (mean 7.1 per node) | — |

The code more than doubled in about eight weeks. **Roughly two thirds of the new source lines are in areas the toolkit's own scope doc treats as secondary.** `docs/philosophy-and-scope.md` says specy-road "does not compete on" driving vendor coding-agent CLIs as workers. Even so, worker and harness brokering is now the largest capability, has been reworked most often, and uses the most review effort.

Method notes: modules and tests were mapped to capabilities with filename regexes (`work05/scripts/cap.py`), so the mapping is approximate to about ±10% per bucket. A leaf counts as touching a capability when any `.py` file in its `touch_zones` maps there. Its primary capability is the one it touches most. Review records were counted from the live `sr/work/reviews/` (REVIEW-* files plus `history/` files) and attributed to the leaf's primary capability. The "fix/review commits" column counts commits whose subject matches fix|review|round|address|block, so treat it as a rough indicator.

---

## 1. Feature inventory by capability

Core here means the four commitments in `philosophy-and-scope.md`: the repo-resident graph, separated roles, commit-bound reviews, and a surface made of tracked files plus one-shot commands. Validation, briefs, the registry/git workflow and the review gate serve those commitments directly.

### Core capabilities

| # | Capability | User-facing surface | Src / test lines (v0.2.3 src) | Built / patched by (examples) |
|---|---|---|---|---|
| A | **Graph model & validation** | `validate [--strict --generate-orchestration]`, `export`, schemas (`roadmap`, `manifest`, `registry`), `refresh-schemas`; node fields `node_key id parent_id type title codename execution_milestone status touch_zones dependencies parallel_tracks sibling_order sensitivity executor_eligibility notes planning_dir goal acceptance planned_test_changes risks decision rollup_status milestone_execution` | 3,184 / 2,518 (2,661) | 36 leaves touch it; M9.11, M11.46, M11.47, M11.69, M11.70, M13.4, M15.20 (open) |
| B | **Graph authoring** | `list-nodes show-node add-node edit-node set-gate-status archive-node list-dependencies set-dependencies add-dependency remove-dependency apply move-node rebalance-chunks`, `archive deepen-archive list-archives show-archive restore-archive` | 4,580 / 3,574 (3,707) | M3.3, M4.7, M4.8, M10.14, M11.10, M11.17 |
| C | **Planning sheets & briefs** | `brief`, `scaffold-planning`, `author-approach`, planning sync, `roadmap.md` export | 2,772 / 1,674 (2,052) | M3.1, M3.14, M11.15, M15.8, M9.9 (brief call sites) |
| D | **Query & context** | `digest [--check]`, `why-blocked`, `list-gates`, `history`, `search`, `impact`, `decisions add/list/close` | 4,618 / 3,154 (3,644) | M11.34, M11.65, M13.4, M12.4.x (open) |
| E1 | **Pickup / finish / registry (git workflow)** | `do-next-available-task`, `abort-task-pickup`, `finish-this-task`, `reconcile-branch`, `registry-prune`, `sync`, `start-milestone-session`, `open-milestone-pr`, `reconcile-milestone-status`; `git-workflow.yaml`: `integration_branch remote merge_request_requires_manual_approval require_implementation_review_before_finish require_implementation_before_finish cleanup_work_artifacts_on_finish on_complete prefer_agentic_pick_order baseline_cmd land_check_cmd verify_cmd` | 7,349 / 7,506 (5,133) | 46 leaves; M3.12, M3.13, M4.9, M4.10, M9.1, M11.5, M11.19, M11.25, M11.50, M11.52, M11.53, M11.63, M11.74, M15.4 |
| F1 | **Review gate** | `ready`, `review record / list`, `handoff status`, `mark-implementation-reviewed`, `review-packet`; policy `reviewers_required reviewers_distinct_families reviewer_fresh_session signed_reviews reviewer_reruns_required milestone_full_review`; review-record and handoff schemas | 4,487 / 3,639 (1,301) | 71 leaves touch it (2nd highest); 11 of the 38 open leaves |
| M | **File limits** | `file-limits`, `constraints/file-limits.yaml`, TS/JS function caps | 1,028 / 542 (420) | M4.12, M4.18, M3.16, M3.18, M11.55, M15.7 (open) |
| K1 | **Install / init / upgrade** | `init project`, `specyrd init`, `upgrade [--dry-run --prune]`, `update`, `refresh-stubs`, `refresh-schemas`, `refresh-profiles`, `--version`, `scaffold-constitution` | 3,726 / 4,447 (2,068) | M3.8, M11.29, M11.43, M11.44, M11.66, M13.1–M13.3, M13.5, M13.6, M13.10, M15.1, M15.15; open M13.11, M13.13 |

### Peripheral or support capabilities

| # | Capability | User-facing surface | Src / test lines (v0.2.3 src) | Classification |
|---|---|---|---|---|
| F2 | **Review hardening add-ons** | `integrity`, `review red-green`, `review check-pre-existing`, `review defer`, `lessons add/list`, RCA escalation, delta and resumed-delta review, strong review on high-risk zones, signed reviews; policy `integrity_gate red_green delta_review reviewer_resumed_delta strong_review escalate_review_rounds escalate_same_acceptance_blocks max_fix_rounds ratchet_paths`; land check | 3,465 / **8,167** (430) | Core-adjacent and opt-in. It has the highest test-to-source ratio (2.4×) |
| E2 | **Worktrees, branches, doctor** | `doctor`, `worktree prune`, `branches prune`, worktree `env_setup` (cmd/copy) | 1,577 / 2,529 (0) | Support for the git workflow |
| E3 | **Sessions / presence / milestone session** | `session start/touch/end/list/check/guard/name`, milestone lock, `on_complete` session | 1,401 / 1,083 (526) | Peripheral (guards for shared checkouts) |
| G1 | **Worker & harness brokering** | `worker delegate list status events sync message resume interrupt handoff reclaim reconcile open timeline usage adopt hook terminate`, `review delegate`, `orchestrate plan`, `prompt --role`, harness adapters (claude-code, codex, cursor, generic), harness-facts fixture, post-run check; roster `harness harness_model routing billing_route channels{cli,cli_resume,paste,subagent} may_process subagent_family_lock class preflight`; policy `max_workers stall_after_seconds`; git-workflow `track_worker_logs` | **8,825 / 7,106** (262) | Peripheral. Largest capability |
| G2 | **Model profiles & roster tooling** | `models list/show/stale/roster`, `refresh-profiles`, 32 shipped profile files, roster `profile pinned available paused_until unavailable_until public_key`, `substitutions` | 1,316 / 1,543 (0) | Peripheral |
| G3 | **Tool-call guard hooks** | `orchestration` guard CLI, `session guard`, per-harness hook adapters | 1,235 / 733 (0) | Peripheral |
| G4 | **Usage / cost metrics** | `worker usage`, `review usage`, `worker timeline`, throughput study, per-route pricing | 753 / 1,130 (465) | Peripheral |
| H | **Grind session** | `grind-session [--plan]`, `grind_session_*` keys (5), `grind.shared_zones` | 2,584 / 2,543 (2,060) | Peripheral |
| I | **Brainstorm** | `brainstorm` with 17 subcommands (`add-idea list sessions revise promote accept reject close add-evidence cluster decide evidence frame merge next-round park verify`) | 4,983 / 4,525 (2,271) | Peripheral |
| J | **PM GUI** | `gui`, PM publish/integration, settings; plus 16,540 TS/TSX lines | 3,601 / 3,389 (3,385) | Peripheral, already behind the `[gui]` extra |
| K2 | **Agent-file hygiene** | stale-command scan, context meter per harness, behaviour-change catalogue, managed AGENTS.md block variants, skills, ignore reports, validate notices | 1,947 / 1,713 (214) | Peripheral |
| L | **Chore mode** | `chore start/close/garden` | 481 / 505 (0) | Peripheral (a second lightweight work loop) |
| N | **Nested sibling repos** | `nested_repos` config, nested landing, nested review packet | 643 / 836 (0) | Peripheral; affects gate correctness (M14.1) |
| — | Advisory LLM review | `review-node` (`[review]` extra, the named exception to principle 4) | in F1 | Peripheral |

Core total (A, B, C, E1, F1, M, K1, plus D's digest): about 30–33k source lines, close to the size of all of v0.2.3. **Peripheral total (G1–G4, H, I, J, K2, L, N, E3): 27.8k source lines (42%) and 25.1k test lines (38%), plus 16.5k GUI TypeScript lines.**

---

## 2. Overlap and churn

### 2.1 Where the work went (since v0.2.3)

| Capability | Leaves touching | Primary leaves | Review records (primary) | Commits | Fix/review-subject commits |
|---|---|---|---|---|---|
| G1 workers/harness | **106** | **70** | **479** | **247** | 168 |
| F1 review gate | 71 | 37 | 185 | 146 | 117 |
| E1 pickup/finish/registry | 46 | 19 | 109 | 113 | 67 |
| F2 review hardening | 29 | 6 | 57 | 126 | 100 |
| K1 install/upgrade | 26 | 12 | 83 | 99 | 66 |
| K2 agent-file hygiene | 25 | 8 | 51 | 91 | 65 |
| A graph validation | 36 | 3 | 17 | 71 | 41 |
| E2 worktrees/doctor | 14 | 6 | 69 | 56 | 37 |
| G2 models/roster | 17 | 6 | 43 | 61 | 39 |
| I brainstorm | 14 | 11 | 63 | 52 | 31 |
| G4 usage | 17 | 1 | 11 | 48 | 18 |
| B graph authoring | 14 | 9 | 44 | 38 | 13 |
| H grind | 15 | 6 | 34 | 25 | 8 |
| (docs-only leaves) | — | 14 | 56 | — | — |

The worker family (G1–G4) accounts for **542 of 1,441 review records (38%)** and 70 or more of the 232 leaves. The review gate (F1 and F2) accounts for 242 (17%). The graph and planning core (A–D) accounts for 111 (8%).

Most-edited files, by leaves listing them in touch zones / non-merge commits: `review_cli.py` 31/47, `role_prompt.py` 27/48, `review_gate.py` 23/35, `worker_ops.py` 23/36, `worker_cli.py` 22/29, `cli.py` 22/33, `validate_roadmap.py` 22/32, `review_packet.py` 21/30, `orchestration.schema.json` 21, `orchestration_config.py` 20/20, `worker_runner.py` 17/37, `worker_adapters.py` 17/24, `worker_reconcile.py` 15/23. Four docs are each touched by 17–28 leaves (`orchestration-workers.md`, `orchestration-review.md`, `orchestration.md`, `orchestration-models.md`).

### 2.2 Features rebuilt or patched repeatedly (same behaviour, three or more leaves)

| Behaviour | Leaves | Note |
|---|---|---|
| Model id ↔ harness id ↔ profile matching | M3.11, M11.26, M11.35, M11.76, M13.5, M15.10, M15.11, M15.19 | 8 leaves, with 13, 13 and 8 review records on some. A naming layer that keeps drifting |
| Upgrade reporting and preview | M3.8, M13.1, M13.2, M13.3, M13.10, M15.15, M15.1, M15.6-docs; open M13.11, M13.13, M15.7 | 11 leaves on one command's output |
| Worker slot accounting (`max_workers`) | M11.4 (20 records), M11.57 (12), open M15.26 | Third attempt at the same leak |
| Reviewer run with no record / failed run reporting | M11.72, M11.77, M11.62, open M15.29, open M8.3 (58 records, still open) | M8.3 alone has the most review records of any node |
| Worker reconcile / post-run check | M3.10, M8.2 (22), M11.6, M11.40, open M14.4.3 | |
| Rework / fix-round prompts and RCA | M4.17, M11.68, M11.71, M12.1, M14.11, M15.6; open M14.9, M14.10, M15.28 | 9 leaves on loop-control prompts |
| Stale-command scan of agent files | M5.2, M5.8, M11.45, open M12.6 | |
| Delta review and approval carry-over | M11.8 (12), M11.16 (11), M11.36; open M15.30, M14.1 | Each relaxation needed a later guard to close the hole it opened |
| Worktree / branch / registry cleanup | M4.10, M4.13, M4.16, M11.31 (21), M14.2, M14.3 (22); open M12.5 | 7 leaves; four separate prune commands |
| Session end / presence lookup | M11.42, M14.7 | |
| Cursor usage pricing | M11.67, M15.19; open M15.27 | |
| Validate notices noise | M3.8, M13.7 (18), open M13.12 | |
| Pre-existing verifier failures | M3.17, M9.8 | |
| Module splits forced by the file cap | M3.16, M3.18, M11.55, M11.59 | They show up as `brainstorm_cli_args_v2.py`, `worker_ops_{launch,lifecycle,message,slots}.py` and similar fragmentation |

### 2.3 Features that exist mainly to work around other features

- **Delta review → full-leaf checklist (M15.30) → resumed delta (M11.36) → planning-only commits keep approvals (M11.16) → sibling-repo carry-over hole (M14.1).** Each one relaxes commit-bound review for cost reasons and then needs a guard against the gap it opened.
- **Two review-gate switches (M11.41).** `git-workflow.yaml:require_implementation_review_before_finish` and the orchestration policy had to be kept from disagreeing. The fix was a consistency check instead of a single source of truth.
- **Four verification-command concepts.** `baseline_cmd`, `land_check_cmd`, `verify_cmd` and `ratchet_paths` exist, and open M15.23 adds per-zone CI gates as a fifth. Open M15.24 then guards `ready` against false evidence from those commands.
- **File-cap splits (M3.16, M3.18, M11.55, M11.59).** The line cap that keeps modules small has produced many 100–300-line modules that only make sense together, such as `do_next_task_*` (11 files) and `review_packet_*` (4 files). The cap now creates navigation cost.
- **Runtime directories vs clean-tree checks (M11.3, M11.19, M15.25).** The toolkit writes state under `work/` (`.sessions`, `.worktrees`, worker logs) and then needs exceptions so its own checks ignore it.
- **Chore parity (open M15.14).** This rebuilds worktree/branch/env_setup/review-record handling for chores, which leaves already have. It is a second work loop being brought up to the first.
- **`REPLACED_COMMANDS` shims, `archive-node` "legacy hard-remove", `brainstorm_cli_*_v2`.** v1 and v2 surfaces are kept side by side.
- **Host effects policy (open M15.5) and tool-call guard (G3).** These exist because headless workers launched by specy-road act on the host. If specy-road did not launch workers, the guard would be the harness's job.

### 2.4 Commands with overlapping purpose

| Purpose | Commands today |
|---|---|
| "Is this leaf ready / what's blocking / what's the review state" | `ready`, `handoff status`, `review list`, `why-blocked`, `list-gates`, `worker status`, `digest` |
| "What can run next" | `do-next-available-task`, `orchestrate plan`, `grind-session --plan` (M11.11 had to unify their readiness rule) |
| "Launch an agent on a leaf" | `prompt --role`, `worker delegate`, `review delegate`, `review-node` (direct LLM API), `grind-session`, `chore start --model` |
| "Clean up after the loop" | `doctor`, `worktree prune`, `branches prune`, `registry-prune`, `abort-task-pickup`, `reconcile-branch`, `worker terminate --orphaned` (and open M12.5) |
| "Bring the repo up to the new version" | `upgrade`, `update`, `refresh-schemas`, `refresh-profiles`, `refresh-stubs`, `specyrd init` |
| "Milestone delivery" | `start-milestone-session`, `open-milestone-pr`, `reconcile-milestone-status`, plus finish's milestone rollout and `milestone_full_review` |
| "Recorded human judgements" | `decisions`, `lessons`, `brainstorm decide`/policies, `review defer` |
| "Find context" | `digest`, `search`, `history`, `impact`, `brief` |
| "Who is working where" | `session *`, `worker list`, registry claims, milestone lock |
| "Archive" | `archive`, `deepen-archive`, `archive-node` (legacy) |

---

## 3. Value vs cost ranking

Cost is source plus test lines, leaf count and review records. Centrality is judged against `constitution/purpose.md`: "canonical graph, contracts, and planning narrative … a review contract and role separation … leaving the choice of IDE, agent, and model to the team."

| Rank (worst value/cost first) | Capability | Cost (src+test; leaves; reviews) | Centrality | Verdict |
|---|---|---|---|---|
| 1 | **G1 worker & harness brokering** | 15.9k; 106; 479 | Low. Purpose leaves agent choice to the team, and the scope doc says specy-road does not compete on driving CLIs | Highest cost and highest churn. Move behind an extra |
| 2 | **G2+G3+G4 profiles, guard hooks, usage** | 6.7k; 38; 63 | Low. Only `id`, `family` and `roles` are needed for the distinct-family rule | Move with G1 |
| 3 | **I brainstorm** | 9.5k; 14; 63 | Low to medium. Idea capture only matters to the graph through `promote` | Extra |
| 4 | **H grind session** | 5.1k; 15; 34 | Low. Batch automation of the loop | Extra (with workers) |
| 5 | **F2 review hardening** | 11.6k; 29; 57 | Medium. Strengthens the review contract, but 9+ policy knobs, most opt-in | Keep integrity and land check; evaluate the rest by evidence |
| 6 | **K2 agent-file hygiene** | 3.7k; 25; 51 | Low to medium | Keep the stale-command check, fold the rest into `upgrade`/`validate --notices` |
| 7 | **J PM GUI** | 7.0k Python + 16.5k TS; 2; 19 | Medium for PMs | Already an extra; freeze |
| 8 | **E2/E3 worktrees, doctor, sessions** | 6.6k; 24; 85 | Medium (support) | Merge cleanup into `doctor`, demote presence |
| 9 | **K1 install/upgrade** | 8.2k; 26; 83 | High for `init`; medium for the refresh-* layering | Collapse refresh-* into `upgrade` |
| 10 | **D query/context** | 7.8k; 10; 27 | High for `digest`/`why-blocked`; medium for `history`/`search`/`impact` | Keep digest/why-blocked core; history/search/impact optional |
| 11 | **E1 pickup/finish/registry** | 14.9k; 46; 109 | High | Core; consolidate milestone trio |
| 12 | **F1 review gate** | 8.1k; 71; 185 | Highest. It is the review contract | Core; simplify status commands |
| 13 | **A/B/C graph, authoring, briefs** | 18.3k; ~60; 84 | Highest | Core; stable, low churn, best value per line |

The pattern: the core grew about 10–20% since v0.2.3 and churned little. The new costs come from bringing worker brokering in-house. Each adopter-feedback batch (M11, M13, M15) then mostly patched worker, harness and review-loop mechanics that the harness would otherwise own.

---

## 4. Consolidation map

### 4.1 Minimal core (`pip install specy-road`)

Everything needed for the four commitments. Parity means today's behaviour is preserved for these commands, with aliases kept for one release.

| Group | Kept commands (target names) | Absorbs |
|---|---|---|
| Graph | `validate`, `export`, `digest`, `brief`, `node list/show/add/edit/move/apply`, `deps …`, `archive …` | `archive-node` (deprecate), `deepen-archive` → `archive --deep`, `rebalance-chunks` → `validate --fix-chunks` (or automatic on write), `set-gate-status` → `node edit` |
| Planning | `planning scaffold`, `planning approach` | `scaffold-planning`, `author-approach` |
| Work loop | `pickup` (`do-next-available-task` alias), `abort`, `finish`, `reconcile-branch`, `sync`, `milestone start/pr/status` | `start-milestone-session`, `open-milestone-pr`, `reconcile-milestone-status` |
| Review gate | `ready`, `review record`, `review status`, `review packet`, `mark-implementation-reviewed`, `integrity` | `handoff status` + `review list` → `review status`; `why-blocked`/`list-gates` stay as graph queries |
| Hygiene | `doctor [--prune worktrees|branches|registry]`, `file-limits [--baseline]`, `upgrade [--dry-run]`, `init project` | `worktree prune`, `branches prune`, `registry-prune`, `refresh-schemas`, `refresh-stubs`, `update` (deprecate: git-clone fast-forward), part of `refresh-profiles` |
| Records | `decisions` | `lessons` → `decisions --kind lesson` |

Core config:
- **`git-workflow.yaml`**: `integration_branch remote on_complete merge_request_requires_manual_approval require_implementation_before_finish cleanup_work_artifacts_on_finish prefer_agentic_pick_order env_setup`. Add one `checks:` block that replaces `baseline_cmd`/`land_check_cmd`/`verify_cmd` (and absorbs M15.23 per-zone CI gates): named commands, each with `when: [pickup, ready, land]` and optional `zones`.
- **`orchestration.yaml` core**: roster `id family roles available` plus policy `reviewers_required reviewers_distinct_families reviewer_fresh_session signed_reviews milestone_full_review integrity_gate ratchet_paths`. Make `require_implementation_review_before_finish` derive from policy only, which removes the M11.41 disagreement check.

Estimated core size: about 30–35k source lines, 45–50 user-facing command names (today 68), 2 config files with core keys.

### 4.2 Optional extras or plugins

The pattern already exists for `[gui]`, and `tests/test_cli_imports_without_gui_extra.py` already checks it.

| Extra | Contents | Src lines moved |
|---|---|---|
| `specy-road[workers]` | G1–G4 + H: `worker *`, `review delegate`, `orchestrate plan`, `prompt`, `grind-session`, `orchestration` guard, `session guard`, `models *`, `refresh-profiles`, shipped model profiles, harness-facts fixture, usage/pricing, `chore` (if kept). Roster fields `harness harness_model routing billing_route channels may_process subagent_family_lock class preflight profile pinned paused_until unavailable_until public_key`; policy `max_workers stall_after_seconds`; `track_worker_logs`; `grind_*` keys | ≈14.7k (+≈13k tests) |
| `specy-road[brainstorm]` | `brainstorm *`, brainstorm GUI routes | ≈5.0k |
| `specy-road[gui]` (exists) | PM GUI, `pm_publish`, PM integration registry | ≈3.6k + TS |
| `specy-road[insight]` | `history`, `search`, `impact`, quality scores (if ever built) | ≈3–4k |
| `specy-road[review]` (exists) | `review-node` advisory LLM review | small |
| `specy-road[review-plus]` or policy module | red-green, pre-existing reproduction, delta/resumed-delta, deferral, RCA escalation, strong review | ≈2.5k |
| `specy-road[nested]` | nested sibling repos | ≈0.6k |

Core exposes a small extension seam: entry points for (a) "launch an executor/reviewer for this leaf" (default: print the prompt, which is today's `prompt`), (b) a post-`ready` hook, and (c) extra `validate` checks and `doctor` probes. Workers then plug in without core importing `worker_*`.

### 4.3 Deprecate (one-release alias, then delete)

`archive-node`, `update`, `refresh-schemas`/`refresh-stubs` as separate commands, `handoff status`, `registry-prune`/`branches prune`/`worktree prune` as separate commands, `start-milestone-session`/`open-milestone-pr`/`reconcile-milestone-status` names, `lessons`, `set-gate-status`, the `REPLACED_COMMANDS` entries, and `chore` (prefer `node add --kind chore` under the normal leaf loop, or drop it). Also: the `session` presence commands other than `guard` (worktrees per leaf made shared-checkout presence largely redundant; confirm with a parity check), the `brainstorm_*_v2` split (merge back into one argparse), and the M2 "Outcome record pilot" phase (empty placeholder milestones, no tasks).

### 4.4 The 38 open leaves

| Disposition | Leaves | Rationale |
|---|---|---|
| **Finish before slimming** (correctness in core) | M14.1 (approval carry across sibling repos: a gate hole), M15.24 (`ready` records false evidence), M15.21 (linked worktrees resolve the root), M15.7 (file-limits baseline: small, core constraint) | Gate-integrity or core path bugs; keep them small |
| **Fold into M16 consolidation leaves** | M12.6 (command parser registry: becomes the M16 surface inventory), M12.5 → `doctor --prune` consolidation, M15.23 + M15.24's `--run-argv` → `checks:` block, M13.11 + M13.12 + M13.9 → one `upgrade` report / `validate --notices` pass, M15.20 → validate check, M14.5 + M15.16 + M15.17 → review-record rules in core, M15.22 PR footer → finish option (drop the other preferences) | Each is a symptom of the overlaps in §2.4 |
| **Move to the workers extra backlog** (do not finish in core) | M8.3, M15.2, M15.3, M15.5, M15.9, M15.13, M15.25, M15.26, M15.27, M15.28, M15.29, M14.4.3, M14.9, M14.10, M12.4.3 | Worker, harness and review-loop mechanics. Of these, M15.26 (slot leak) is the only bug worth fixing before extraction. M8.3 has used 58 review records without landing and should be re-scoped or dropped |
| **Move to the nested extra or defer** | M14.4.2, M14.8 | Only matter with `nested_repos` |
| **Drop or park** | M12.4.1 (per-area quality scores: 19 records spent, still open), M12.4.2 (tech-debt ledger), M13.13 (upgrade `--prompt` templating), M13.14 (validate flags agent text: "best-effort hint"), M15.14 (chores at parity), M15.30 (patch on delta review; moot if delta review is demoted), M2.1/M2.2 (empty) | Metrics, prompts and parity work on peripheral features |

---

## 5. Slimming programme (proposed milestones)

Guiding rule: **every M16 leaf is behaviour-preserving for core commands and net-negative or neutral in lines.** New adopter feedback goes to an intake list (for example a future M17 milestone), not into M16.

### M16.0 — Freeze and baseline (gate for everything after)
1. Finish the four correctness leaves in §4.4 (M14.1, M15.24, M15.21, M15.7) and M15.26.
2. Write down a feature freeze: no new feature leaves under M12–M15. Re-home open leaves per §4.4 by editing their parents and statuses. This is human-owned triage.
3. Build the **parity harness** (a test-only addition):
   - golden `--help` transcripts for every command (built on M12.6's parser registry);
   - an end-to-end scripted loop in a temp repo: `init project → node add → planning scaffold → pickup → ready → review record ×2 → review status → finish` (merge and PR modes), plus `upgrade --dry-run` on a 0.3.1-shaped repo;
   - a review-gate decision table: a fixture set of review records and commits mapped to the expected gate verdict for every kept policy;
   - the dogfood fixture `validate`/`export --check`/`digest --check` outputs.
4. Record baseline metrics: src/test lines per capability (reuse `work05/scripts/cap.py`), command count, config-key count, suite wall time.

**Gate:** parity harness green on current HEAD; baseline committed.

### M16.1 — Surface consolidation (aliases, no removals)
Leaves: `doctor --prune` absorbs the three prune commands and M12.5. `review status` absorbs `handoff status` and `review list`. A `milestone` group. `upgrade` absorbs refresh-* and `update`. `archive --deep`. `planning` group. `decisions --kind lesson`. Each old name prints a one-line deprecation pointer. Update `suggested_prompts/`, templates and docs in the same leaf (per CLAUDE.md maintainer hygiene).
**Gate:** parity transcripts identical apart from the deprecation line; stale-command check passes on shipped templates.

### M16.2 — Config consolidation
Leaves: the `checks:` block (migrating `baseline_cmd`/`land_check_cmd`/`verify_cmd`, which closes M15.23); a single source for the review-before-finish switch; `grind_*` keys moved under `grind:`; roster schema split into core fields and an extension namespace. `upgrade` migrates old configs and `validate` accepts both forms for one release.
**Gate:** `upgrade --dry-run` on the 0.3.1 sample repo and the toolkit's own `sr/` produces semantically equal configs; gate decision table unchanged.

### M16.3 — Workers extraction (largest pass; split by sub-area)
Order: (a) define the core extension seam and make core import nothing from `worker_*`, `harness_*`, `orchestrat*`, `model_*`, `roster_*`, `tool_call_guard*`, enforced by an import-boundary test like the GUI one; (b) move G1 and G4; (c) move G2 and profiles; (d) move G3 guards; (e) move grind-session. Keep the package layout in this repo as `specy_road_workers` (or `specy_road/ext/workers`) with an extra, so it ships together but is optional.
**Gate:** the core test subset passes with the extra uninstalled; full suite and parity harness pass with it installed; `init project` without the extra writes no worker config.

### M16.4 — Other extras
Brainstorm, insight (history/search/impact), nested repos, review-plus. Same import-boundary gate per extra.

### M16.5 — Review-gate simplification
Use evidence already on disk: for each optional policy (delta, resumed delta, red-green, pre-existing, deferral, RCA escalation, strong review), count in `sr/work/reviews` how often it changed a gate outcome. Keep what changed outcomes; deprecate the rest. Merge the four `review_packet_*` and the `review_gate*` files where the cap allows.
**Gate:** decision table unchanged for kept policies; deprecated policies produce a validate notice, not an error.

### M16.6 — Deletion and recombination
Remove aliases deprecated in M16.1 after the next release. Delete dead code (coverage plus a dead-code scan). Recombine cap-driven fragments where a combined module stays under the cap or warrants a recorded exception. Shrink docs: one orchestration doc per extra, and archive design notes over 800 lines (two exceed it).
**Gate:** line targets met (core ≤ 35k src, ≤ 50 commands); suite wall time not worse than baseline; release candidate passes the release runbook.

### Keeping scope bounded
- **Line budget per leaf.** Each M16 leaf declares an expected net line delta. Reviewers block on unexplained growth.
- **No new knobs.** M16 leaves may not add policy keys, config keys or commands, except the `checks:` block and the extension seam.
- **Intake parking.** Adopter feedback during M16 is filed under an intake milestone and triaged after M16.6. The M11/M13/M15 pattern, where every feedback batch became a phase of patches, is the main growth driver.
- **Fix-round cap.** Mechanical moves should land in one or two rounds. If a leaf exceeds `max_fix_rounds`, split it rather than iterate (median today is about 7 review records per node, and the worst exceeds 20).
- **Version numbers stay human-owned.** The programme implies a minor or major bump for the extras split. The maintainer picks the number.

---

## Appendix — data files
- `scratchpad/analysis/work05/tasks.txt`: all 232 tasks (id, status, title, touch zones)
- `scratchpad/analysis/work05/task_cap.txt`: task → primary capability → review-record count
- `scratchpad/analysis/work05/cap_now.txt`, `cap_v023.txt`, `cap_files.txt`: capability line counts and module lists
- `scratchpad/analysis/work05/reviews.txt`: review records per node
- `scratchpad/analysis/work05/gitlog.txt`: non-merge commits v0.2.3..b216d799 with touched files
- `scratchpad/analysis/work05/scripts/cap.py`: classifier
