# specy-road slimming recommendation (2026-11-05)

Coordinator synthesis of five read-only analyses run on a snapshot of `WIP/improvements-0-3-1` at b216d799. Baseline is
`v0.2.3` (2026-09-09), the last release before 0.3.1 work began. The detailed reports are in this folder:

| File | Scope |
|---|---|
| `00-growth.txt` | Line, file and function counts per release tag |
| `01-code.md` | Code size, efficiency and coherence: module map, fragmentation, duplication, dead code, layering, top 15 opportunities |
| `02-tests.md` | Test suite: inventory, per-test branch coverage (subprocesses included), redundancy classes, gaps, target shape |
| `03-docs.md` | Governing docs: vision vs reality, contradictions, doc size, lean doc layout |
| `04-prompts.md` | `suggested_prompts/` followed read-only against this repo |
| `05-roadmap.md` | Feature inventory, churn, value vs cost, consolidation map, M16 programme |

## 1. Growth since 0.3.1 work began

| Measure | v0.2.3 | rc1 (10-28) | rc2 (10-29) | rc3 (11-04) | WIP now | Growth |
|---|---|---|---|---|---|---|
| Package Python lines / files | 31.3k / 172 | 40.4k / 217 | 45.8k / 233 | 60.4k / 305 | 65.4k / 338 | 2.1× |
| Same, at v0.2.3's line width | | | | | about 77.6k | 2.5× |
| Test Python lines / files | 25.2k / 150 | 34.0k / 201 | 39.5k / 223 | 58.9k / 327 | 65.3k / 367 | 2.6× |
| Test functions (items collected) | 1,310 | 1,794 | 2,048 | 3,028 | 3,326 (about 4,400) | 2.5× |
| CLI subparsers / top-level commands | 28 / 45 | 66 | 73 | 93 | 99 / 68 | 3.5× / 1.5× |
| docs/ lines (+ design notes) | 6.4k | 11.2k | 11.9k | 14.0k | 14.5k (+ about 6k) | 2.3× |
| Shipped templates lines | 1.5k | 3.3k | 3.4k | 6.3k | 6.3k | 4.2× |
| Full suite wall time (16 workers, loaded host) | 59 s | | | | 111 s | 1.9× |
| Commits since v0.2.3 | 0 | 286 | 761 | 2,212 | 2,681 | |

Roadmap: 232 leaves, 195 complete; 1,441 review records across 204 nodes (about 7 per node, worst case 58).

## 2. Diagnosis

*Maintainer ruling (2026-11-05): workers and orchestration are canonical specy-road; they are not candidates for removal or for an optional extra. Read "peripheral" below as "outside the governing docs as currently written", which is a docs gap to fix, not a cut list.*

**The core did not bloat. Most growth is the orchestration capability, which the governing docs never caught up with.** The roadmap core (graph,
validate, brief/digest/export, pickup/finish/registry, archive, PM GUI) barely grew or churned. The growth is:

- **Worker, harness and orchestration plumbing:** 0.3k → 12.2k source lines, with about 7k test lines, 106 leaves and 247 commits.
- **Review, hand-off and gate machinery:** 1.1k → 8.1k source lines.

Those two areas are 53% of all source growth and about 38% of all review records. With model profiles, guard hooks,
usage metrics, grind session and agent-file management added, about 42% of source and 38% of test lines are outside
the stated purpose. `docs/philosophy-and-scope.md` itself says specy-road does not compete on driving agent CLIs.

**How it grew matters as much as how much.** About two thirds of leaves (about 155 of 232) respond to the previous
feedback or review round: each adopter batch became a phase of narrow patches, and each patch carried narrow regression
tests. The marks are visible in the code:

| Symptom | Evidence |
|---|---|
| Fragmentation from the cap | 93 modules have one importer; 49 say in their docstring they were split for the 400-line cap; 38 files sit within 20 lines of it; one module swaps its own module class so test patches reach its split parts |
| Cap dodged by width | Lines over 100 characters went 78 → 3,068 |
| Defensive accretion | Functions at radon C or worse 94 → 313; 22 new `noqa: C901`; end-of-line comments 51 → 611 |
| Rules written several times | Dependency readiness ×4, roster eligibility ×5, `now()` ×9, atomic write ×6 |
| Layering | 102 library modules live in `bundled_scripts/`; import cycles of 45 and 25 modules; `validate` imports 110 modules (was 31); every command runs in a second Python process (about 400 ms for `--help`) |
| Repeated rebuilds | Model-id matching patched by 8 leaves, upgrade reporting by 11, `max_workers` slot counting on its 3rd attempt, four overlapping prune commands, 4–5 "verification command" concepts |

**What is not the problem:** literal copy-paste (about 330 lines), dead code (about 440 lines), undocumented flags
(17 of 237), and stale command names in docs or prompts (none found).

### Tests: bloated, and they have gaps

- **Coverage:** 89% overall (91.2% of lines, 83.7% of branches), up from 79% at v0.2.3.
- **Removable without losing coverage:** about 30–35% of test functions, which would leave about 2,100–2,300. The candidates, by class:
  - (a) exact duplicates, about 300–400, mostly the same check repeated in another file;
  - (b) single-input regressions, about 500–700, which would fold into roughly 150 table-driven tests;
  - (c) tests tied to private names, about 150–200 (100 patches of private functions across 25 files).
- **Coverage alone is not a deletion list.** 1,385 items reproduce 100% of the coverage, but narrow unit tests always look redundant next to big end-to-end tests.
- **Review-round files are not the outliers:** files named after review rounds are no more redundant than the rest (78% vs 76%). Duplication is spread across the whole suite, so deleting the per-leaf files would miss most of it.
- **Cost drivers:** 464 tests spawn the CLI as a separate process and use 32% of CPU time. Tests that build git repos are next.
- **Gaps that matter, mostly in milestone code:**
  - `start_milestone_session` 29%, `milestone_chunk_io` 53%;
  - `reconcile_milestone_status` 64%, milestone rollup 71%;
  - outline indent/outdent 66%, `roadmap_edit_fields` 74%;
  - `migrate_stable_node_keys` 0%.
- **Structure:**
  - 98 test files import helpers from other test files;
  - a `repo` fixture is defined in 40 files, and 53 helper functions have byte-identical copies;
  - 41 files write `manifest.json` by hand;
  - 1,496 assertions check message substrings;
  - 16 files use `time.sleep`.

### Docs and governance: scope has no stated limit

- **The constitution followed 0.3.1 but never bounded it.** Principles grew from 3 to 9, and several now conflict with the product:
  - "leave model choice to the team" vs a shipped, dated catalogue of about 25 vendor model profiles;
  - "no daemon" vs a GUI server and detached worker processes;
  - "does not reinvent generic agent tooling" vs chore workers that bypass the roadmap.
- **The real vision lives only in `sr/vision.md`,** which is stripped before main.
- **Contradictions:**
  - `AGENTS.md` and `toolkit-development.md` say the toolkit roadmap is "intentionally not defined", while `CLAUDE.md` says `sr/`.
  - Branch policy is stated in 4 places and the version rule in 3.
  - Release-candidate pins are stale: `pyproject.toml` declares rc2, and several docs still say rc1.
  - README describes slash-command stubs that skills replaced.
  - The `[gui]` and `[gui-next]` extras are identical.
  - Shipped templates cite docs that adopters can't resolve.
- **Reading load:**
  - An agent reads about 550–830 lines before starting a task, including the 188-line supply-chain doc for every task.
  - A new adopter reads about 4.4k lines to learn the full 0.3.1 feature set, about twice v0.2.3.
  - Nine docs sit at exactly 400 lines, so they were split at the cap rather than by topic.
- **Suggested prompts:** every command and flag they name exists, but they have gaps:
  - All four cite docs that `init project` doesn't ship.
  - `bootstrap-roadmap` hand-writes UUID JSON instead of using `add-node`.
  - `bootstrap-agents-md` says not to restate rules, then restates them.
  - The governance deliverables table omits `orchestration.yaml`, `model-profiles/` and `review-lessons.md`.

## 3. Recommendation

**Yes, a slimming programme is warranted, but as a separate, bounded milestone after a release, not by continuing the
grind.** The grind as configured turns every feedback batch into more leaves, code and tests, which is the main growth
driver. Mechanical clean-up alone saves only about 4–4.5k lines (6–7%). The real reduction comes from one product
decision: **what specy-road is, and what is an optional extra.**

### 3.1 Decisions for the maintainer (in order)

| # | Decision | Recommendation |
|---|---|---|
| D1 | **Scope.** *Settled by the maintainer (2026-11-05): workers and orchestration are canonical specy-road and stay in core; making them optional is not an option. 0.3.2 will extend the PM GUI to show orchestration and worktree state.* | Update the governing docs to say so: `purpose.md` and `docs/philosophy-and-scope.md` name multi-agent orchestration (workers, roster, review delegation, grind) as part of the product, and the principles that now contradict it ("no daemon", "leave model choice to the team", "does not reinvent agent tooling") are reworded to what is actually true. Still add a short "specy-road is not" list for the edges that remain out of scope (for example: not a CI system, not a hosted service). Slimming then comes from structure, consolidation, tests and docs, **not** from removing capabilities. Give orchestration a clean internal subpackage (`specy_road/orchestration/`: workers, harness adapters, roster, profiles, guards, grind) with one documented interface to the gate and the PM GUI. That boundary is also what the 0.3.2 GUI work should read from. |
| D2 | **Freeze.** When do new feature leaves stop? | Now, except the "finish" list in 3.2. In-flight leaves finish if they are within a round or two. All further adopter feedback goes to an intake list, triaged after the programme. |
| D3 | **Release sequencing.** | Ship 0.3.1 from WIP once the finish list lands (version numbers are yours), then run slimming as the next line. Slimming on top of an unreleased, moving WIP compounds risk. |
| D4 | **File-size rule.** | Replace "400 lines per file" with an 800-line cap plus a 100-character line-width rule (ruff `E501` at 100). That removes the incentive to split by line count and allows folding about 88 cap-driven siblings. |
| D5 | **Test policy.** | Adopt the review-finding test rule in 3.4 and a target of about 2,200 test functions with an 89% coverage floor that may not drop. |
| D6 | **Review policy evidence.** | Before removing any optional review policy (delta, resumed delta, red-green, pre-existing, deferral, RCA escalation, strong review), count from `sr/work/reviews` how often each actually changed a gate outcome. Keep what mattered. |

### 3.2 What to do with the current grind

These are my recommendations, not decisions. The six held leaves stay held until you decide.

| Disposition | Leaves |
|---|---|
| **Finish** (in flight and close, or core correctness) | M14.10, M15.13, M15.20, M15.22, M15.24, M15.25, M15.7, M8.3, M12.5 and M13.12 (both just started), M15.27 (just started), plus unclaimed **M14.1** (a live hole in the review gate) and **M15.26** (orphaned claims and slot leak) |
| **Keep grinding** (orchestration is core, per D1) | Orchestration and review-loop leaves: M15.2, M15.3, M15.5, M15.9, M15.16, M15.17, M15.28, M15.29, M14.4.3, M14.9. Prefer acceptance that consolidates (one function or one state model) over acceptance that adds a branch. |
| **Held** (maintainer, 2026-11-05) | M12.4.2, M12.4.3, M13.13, M13.14, M15.14, M15.30; plus M13.9 (coordinator: it needs the hook in `validate_roadmap.py` that held M13.14 owns) |
| **Decide at triage** | M12.6, M13.11, M14.4.2, M14.5, M14.8, M15.23. Each overlaps a planned consolidation (command inventory, the `upgrade` report, nested repos, the `checks:` block). |
| **Fold into M16 consolidation leaves** (per `05-roadmap.md` §4.4) | M12.6 (becomes the command inventory), M15.23 (becomes the `checks:` block), M13.9/M13.11 (become one `upgrade` report), M14.5/M15.16/M15.17 (become review-record rules) |

M8.3 has used 58 review records. If its current round blocks again, I recommend landing its rescoped core and
re-filing the rest under the workers extra rather than iterating further.

### 3.3 The programme: M16 "lean core"

The proposal from `05-roadmap.md` §5, refined with the code, test and docs findings. **Rule: every M16 leaf preserves
core behaviour and is line-neutral or line-negative.**

| Pass | Content | Gate |
|---|---|---|
| **M16.0 Freeze and baseline** | Feature freeze written down; the open leaves re-homed (your triage). **Parity harness:** golden `--help` transcripts per command; an end-to-end loop in a temp repo (init → add → scaffold → pickup → ready → review ×2 → status → finish, merge and PR modes); a review-gate decision table (fixture records mapped to expected verdicts); dogfood validate, export and digest outputs. Baseline metrics committed. Coverage floor of 89% in CI. | Harness green on HEAD |
| **M16.1 Mechanical clean-up** (no behaviour change) | Delete dead code (about 440 lines, with care for `behaviour_changes.py` if M13.14 is kept). Shared helpers for time, atomic write and git (150–200 lines). One roadmap index for graph queries, replacing the four dependency-readiness copies (250–400). Move library modules out of `bundled_scripts/` and break the two import cycles. Lazy imports so `--help` and `validate` stop loading 110 modules. Adopt the D4 cap and fold the cap-driven siblings (1,000–1,300 lines and about 88 files). | Harness identical; ruff and import-cycle check clean |
| **M16.2 Surface consolidation** (aliases kept for one release) | `doctor --prune` absorbs the three prune commands and the M12.5 cleanup. `review status` absorbs `handoff status` and `review list`. `upgrade` absorbs `refresh-*` and `update`. Groups for `milestone`, `planning` and `archive --deep`. `decisions --kind lesson`. Update suggested prompts, templates and docs in the same leaf. | Transcripts identical apart from a deprecation line |
| **M16.3 Config consolidation** | One `checks:` block replaces `baseline_cmd`, `land_check_cmd` and `verify_cmd`, and carries the per-zone CI gates (M15.23's purpose). The review-before-finish switch derives from policy alone. Roster schema split into core fields and an extension namespace. `upgrade` migrates and `validate` accepts both forms for one release. | `upgrade --dry-run` on a 0.3.1-shaped repo and on `sr/` gives equivalent config; decision table unchanged |
| **M16.4 Restructure orchestration in place** (largest pass, split by sub-area; workers stay core) | Move worker, harness adapter, roster, profile, guard, grind and chore modules into one `specy_road/orchestration/` subpackage, with a small public interface. The gate, CLI and PM GUI call that interface, never the internals. Collapse the five roster-eligibility and four dependency-readiness copies into it. Fold the cap-driven `worker_ops_*` and `review_packet_*` fragments, and remove the module-class swap in `worker_ops.py`. A single state model (claims, workers, worktrees, reviews), read through one interface, also serves the 0.3.2 PM GUI's orchestration and worktree views and fixes the orphaned-claim class (M15.26). Enforce the layering with an import-direction test. | Parity harness identical; import-direction test green; orchestration lines down measurably, with no capability removed |
| **M16.5 Other extras and review-gate simplification** | Brainstorm, insight (history, search, impact), nested repos. Optional review policies kept or deprecated by D6 evidence; merge the `review_packet_*` and `review_gate*` fragments. | Decision table unchanged for kept policies |
| **M16.6 Tests** (can run alongside M16.1–M16.3) | Stages from `02-tests.md`: one shared roadmap-repo builder, plus git repos built once per session and copied per test. Per-module test files. Dedupe from the near-duplicate worklist, with no coverage drop allowed per change. Table-driven and property-based tests for parsers, the tool-call guard, outline operations and the managed block. Replace private-name patches with public seams. Fill the milestone-code gaps. A CLI smoke lane of 30–50 subprocess tests; the rest call in-process. | Coverage at or above the floor; about 2,200 functions; full suite under about 35 s |
| **M16.7 Docs and governance** | Amend purpose with scope and the "not" list. Split principles into product invariants and repo engineering rules. `AGENTS.md` becomes the only agent entry and `CLAUDE.md` a short pointer. Task-conditional load order with supply-chain off by default. Design notes move out of `docs/`. Merge the workers, roster and chores docs into one extra doc. Fix the release-candidate pins and the `[gui-next]` duplicate. Fix the four suggested-prompts gaps. | Agent start-up load at or under about 400 lines; prompts pass a follow-through check |
| **M16.8 Deletion** | Remove the deprecated aliases after the next release; final recombination; archive design notes over 800 lines. | Core ≤ about 35k source lines and ≤ 50 commands; suite time not worse than M16.0 |

**Expected end state** (revised after D1: no capability removed):
- **Source:** about 52–56k lines, down from 65k (77k at the old line width). That comes from mechanical clean-up (about 4–4.5k), command and config consolidation, and the orchestration restructure. 45–50 command names, down from 68.
- **Tests:** about 2,200 functions, at least 89% coverage, under 35 s.
- **Agent start-up reading:** at most about 400 lines.

Total functionality is unchanged, orchestration included. The win is coherence rather than raw line count: one place
for each rule, one state model, and a layering the 0.3.2 GUI can build on.

### 3.4 Stopping it from growing back

1. **Feedback intake parking.** Adopter feedback goes to an intake list and is triaged in batches against scope (D1). Not every finding becomes a leaf.
2. **Line budget per leaf.** Each leaf declares an expected net line delta, and reviewers block on unexplained growth.
3. **No new knobs without a removal.** A new config key, policy key or command must retire one, or have the maintainer's sign-off.
4. **Review-finding test rule.** A regression test is added only if all of these hold:
   - It fails before the fix and passes after.
   - It checks something no existing test checks. A new input to tested behaviour becomes a row in that behaviour's table, not a new test.
   - It is written at the cheapest level that reproduces the bug.
   - It lives in the module's test file and is named for the behaviour, not the round.
   - It asserts structured results, not message text.
5. **Bounded rules over open-ended detection.** When a reviewer keeps finding new input shapes (M13.8, M15.7, M15.20 tonight), stop patching. State the rule in the acceptance and accept documented misses, or split the leaf. Make this the planner's standard response after the second same-class block.
6. **Post-fix refactor** (maintainer, 2026-11-05). A fix may not leave worse structure behind. Before review, a leaf's diff must not raise any function above its merge-base complexity (ruff C901, waivers ignored), nor add `noqa: C901`. Fix rounds end with a consolidation step: one rule or table instead of a new branch per input class. The coordinator's dispatcher enforces this from 2026-11-05. M16 should make it a product gate: `ready` and the packet report the complexity delta, and the policy can block on growth.
7. **Fix-round cap.** If a leaf exceeds about 4 rounds, split or rescope it instead of iterating. Median review records per node are about 7, and the worst is 58.

### 3.5 Risks

- **The orchestration restructure is the riskiest pass.** It touches review delegation, which the gate uses, and it runs alongside the 0.3.2 GUI work. Mitigations: define the interface first, move code one sub-area at a time behind the parity harness, and sequence it before or with the GUI work, not after.
- **Test dedupe can quietly remove protection.** Mitigations: the coverage floor, a per-change coverage diff, and the a/b/c/d classification rather than deleting by coverage alone.
- **Adopters on 0.3.1 configs.** Mitigation: `upgrade` migrates, and validate accepts both forms for one release.
- **Scope creep inside the programme itself.** Mitigation: the M16 rules (behaviour-preserving, line-negative, no new knobs, intake parked).
