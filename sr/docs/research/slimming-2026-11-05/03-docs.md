# 03 - Governing-docs consistency review (WIP b216d799 vs v0.2.3)

Read-only. Paths are relative to the snapshot root. "docs" counts include `docs/design-notes/` (about 6.0k lines of the 14.7k).

## Headline numbers

| Measure | v0.2.3 | WIP | Note |
|---|---|---|---|
| `docs/` top-level files / lines | 22 / 5,139 | 35 / 8,524 | design-notes adds 26 files / ~6,000 lines (v0.2.3 had 1) |
| CLI commands (`_SCRIPTS` table) | 27 | ~47 + CRUD/archive/init/gui (~65) | python modules 82 -> 192 |
| `constitution/purpose.md` / `principles.md` | 5 / 3 items | 5 / 9 items | principles tripled; purpose gained one sentence |
| Shipped templates | 55 files / 1.5k lines | 107 files / 6.3k lines | model-profiles = 3.5k lines, of which harness-captures = 1.1k |
| AGENTS.md / README.md | 46 / 107 | 60 / 132 | |
| Docs hitting the 400-line cap | 2 (runbook 871, dev-workflow 400) | 9 at exactly 400, grind-session 500, runbook 898 | docs are split by `file-limits.yaml` cap, not by topic |

## 1. Vision/purpose vs reality

**Purpose (WIP)**: "a roadmap-first coordination **kit** (Python package + validators + optional PM UI) that product teams install so a canonical graph, contracts, and planning narrative live alongside their code. It prescribes a review contract and role separation ... while leaving the choice of IDE, agent, and model to the team."
**v0.2.3 purpose**: "...without prescribing a specific IDE or agent workflow."

The purpose was amended once (good: review contract added), and principles 4-9 were added for 0.3.1. So the constitution did follow the product, which is better than I expected. The remaining drift is in what is *not* covered:

- **Scope is open-ended.** Nothing says what specy-road is not. Product shipped since 0.2.3: worker brokers (`worker delegate|sync|message|reclaim|terminate`), reviewer rosters + family-distinct counting, model profiles for ~25 vendor models, billing routes/usage, `chore` workers, `session guard` hooks, `worktree`/`branches`/`doctor`, `grind-session`, harness-facts research + captured vendor `--help` output, context-regression replay, a "recurring research" milestone (M7), harness-compat research (M8), agent-loop performance (M10). The roadmap titles M7-M15 are mostly "harness engineering, cheaper gates, agent-loop performance, adopter friction": the toolkit's centre of gravity moved from roadmap validation to agent-runtime operations.
- **"leaving the choice of IDE, agent, and model to the team"** (purpose) vs the shipped catalogue `templates/project/model-profiles/` (named vendor models with per-model prompting rules, effort defaults, `harness-facts.yaml` 439 lines, captured CLI help text) and `orchestrate plan` which decides "which model should implement, which should review" (whats-new). The team keeps the choice, but the kit now maintains a dated market catalogue; that is a maintenance product, not a roadmap kit.
- **Principle 8** "Use the harness's tools and augment them ... does not reinvent generic agent tooling" and philosophy-and-scope "does not ship generic agent tooling of its own" vs shipped: session presence + destructive-git guard hooks for three harnesses, a worker supervisor with leases/ops outbox/resume, `chore` (ad-hoc worker work with no roadmap node: docs/orchestration-chores.md says "worker-run work outside the roadmap"), `grind-session` loop, `ready --run` verifier capture. These are generic agent-runtime features. The "roadmap-specific" qualifier is the only thing holding the principle up, and `chore` explicitly has no roadmap node.
- **Principle 5** "no daemon and no MCP server" vs `specy-road gui` (a uvicorn server) and workers that are "detached" processes that "return at once". orchestration-workers.md has to say "there is no daemon - a detached ..." to square it; philosophy lists the GUI only inside principle 4's exceptions. The principle is true for the coordination CLI but is phrased for the whole kit.
- **Principle 4** "The coordination CLI never calls a model or search API" has three named exceptions (`review-node`, `brainstorm verify`, GUI providers); the GUI also has chat/brainstorm/LLM-review. Exceptions are accurate but the list is the kind that grows; `[gui]` and `[review]` extras both pull `openai` + `anthropic`.
- **Principle 9** "Docs win, smallest change" vs reality: docs grew 2.8x and 9 files sit pinned at exactly the 400-line cap; the rule "smallest change" is applied to code (AGENTS.md "Lean changes") but not to documentation.
- **Principles 1-3 are about this repo's engineering, 4-9 are product invariants.** Mixed audiences in one file. Consumers get a different 3-line `principles.md` (roadmap-first, contracts, separation of concerns) and never see the 4-9 rules except via `.specyrd/AGENTS.md`.
- **Purpose vs vision**: `sr/vision.md` (toolkit's own product vision) says "coding agents pick real leaves ... hand off to independent reviewers, finish through a deterministic gate, while the humans decide". That is the real product statement for 0.3.x and it is more accurate than root `constitution/purpose.md`, yet it lives on the WIP-only `sr/` line that is stripped before main. So the shipped (main) constitution lags the dogfood vision.
- **Positioning section** in philosophy-and-scope.md ("Where specy-road sits") names three third-party products with dated quotes ("read 2026-10-30"). It is marketing/competitive analysis inside a governing doc, will go stale, and is repeated in README ("Governance, not another agent runner") and orchestration.md. Move or cut.

## 2. Contradictions, stale statements, duplicated guidance

Contradictions
1. **Toolkit roadmap exists vs "intentionally not defined".** CLAUDE.md: "Toolkit product roadmap: nested under `sr/` on the `WIP/improvements-0-3-1` line only". AGENTS.md ("A first-class roadmap for the toolkit itself is intentionally not defined here yet") and docs/toolkit-development.md ("a first-class toolkit roadmap is intentionally not defined here yet") say the opposite. Also AGENTS load order (steps 5-7) points only at the dogfood fixture; an agent doing sr/ work is never told to read `sr/vision.md`, `sr/constitution/*` (which duplicate the root ones), or `sr/planning/`.
2. **Version/RC state.** pyproject is `0.3.1rc2`; whats-new says "Release candidate `v0.3.1-rc1`, 2026-10-28" and "Known limitations in this release candidate" (rc1's); install-release-candidates.md and upgrading.md pin `0.3.1rc1` wheels; release notes rc3 draft is only in untracked `sr/work/`. AGENTS.md examples were bumped to 0.3.1 and CLAUDE.md says "name a WIP branch only if user states the number" while the branch is already `WIP/improvements-0-3-1`. Four places carry the "current RC" and will drift every RC.
3. **specyrd stubs.** README step 7 "Optional IDE commands - `specyrd` installs stubs that invoke the CLI", contributor-guide "IDE command stubs (`specyrd`) ... thin slash-command stubs into your IDE's command directory", vs AGENTS.md "skills under `.agents/skills/...`; `.cursor/commands/` and `.claude/commands/` only in repos initialised before 0.3.0" and philosophy ("installs thin skills"). `templates/specyrd/commands/` still holds 26 `specyrd-*.md` files. README and contributor-guide are pre-0.3 descriptions.
4. **Load order.** AGENTS.md and the consumer `agents-rules.md` both require `docs/supply-chain-security.md` (188 lines, +33 since 0.2.3) for every task, including a one-line doc fix. It is a dependency-policy doc, relevant only for dependency changes; for consumers it is a generic shipped doc (one of only two `docs/` files init ships).
5. **Load order vs AGENTS.md "keep context small".** See section 3: ~550-830 lines before any task work, plus the auto-loaded CLAUDE.md duplicate.
6. **CLAUDE.md duplicates AGENTS.md rather than pointing at it.** CLAUDE.md (113 lines) restates the load order, brief command, version-numbers rule, git workflow and branching model that AGENTS.md also states ("The same policy is spelled out in toolkit-development.md, CLAUDE.md, and .cursor/rules/030"). The branch policy is stated in four places (CLAUDE.md, AGENTS.md, toolkit-development.md, contributor-guide.md#branching) plus a Cursor rule; the version-number rule in three (CLAUDE.md, AGENTS.md, .cursor rule 027).
7. **"Docs win" vs. design-notes.** Principle 9 and the shipped `agents-rules.md` say tracked docs beat chat; docs/design-notes/README.md says historical triage "must not be read as current instructions" and, on conflict, "the doc and the code win". philosophy-and-scope.md links a design note (`v0-3-1-worker-orchestration.md`) as the source for principles 4/5/8. So a governing principle is justified by a "live design" note whose precedence is "below docs". Principles should be self-contained or cite a stable doc.
8. **Consumer-facing docs reference toolkit-only docs.** Template `work/README.md` ends "See `docs/orchestration.md` in the specy-road repository"; `model-profiles/README.md`, `agents-rules.md` comments cite `docs/design-notes/...` and `CHANGELOG`. A consumer repo has none of those (init ships 2 docs). These `<!-- ref: -->` comments are unresolvable for consumers.
9. **`[gui]` vs `[gui-next]` extras** are byte-identical in pyproject yet README describes only `[gui-next]` as "PM Gantt UI deps" while install-release-candidates.md and whats-new reference `[gui]`.
10. **Constraints README scope.** It says it applies to this repo only, and lists file-limit checks; but `docs/**/*.md` is under `applies_to_globs` (400 lines) with five override entries (runbook 900, grind 500, two verbatim research files 900-1100). The "constraint" is shaping docs structure (see 3) and its comments narrate history ("a consumer evaluation asked for", "raised to 900 when footgun 9 was added"), which belongs in CHANGELOG.

CLI spot-check (argparse / `cli.py`): I extracted every `specy-road <word>` in docs, README, AGENTS, CLAUDE and templates and checked against `_SCRIPTS`, `_FORWARDED`, `_CRUD_COMMANDS`, `_ARCHIVE_COMMANDS` and init/gui/update/upgrade: **no stale command names found** (all non-matches were prose). `REPLACED_COMMANDS` (`grind`, `pm-sync`, `backfill-activity`) are not referenced by current docs. Flags checked and present: `worker delegate --model/--harness/--rework/--worktree`, `upgrade --prune`, `worker sync/message --fix-round`, `session guard --format --print-config`. Conclusion: command drift is under control (a validate check seems to guard agent files); the stale things are version/RC statements and structural descriptions (items 2, 3), not command names.

Duplicated guidance likely to drift (statement -> places)
- "Executor never reviews its own leaf / review bound to commit": principles 6, purpose, philosophy (2 bullets + positioning #2/#3), README, orchestration.md (3x), orchestration-review.md, agents-rules.md, work/README, whats-new.
- "No model call / no daemon / no MCP": principles 4+5, philosophy (bullet + positioning #4), orchestration-workers.md, design note.
- Review order "review-packet -> review record -> mark-implementation-reviewed -> finish-this-task": orchestration.md quickstart + flow, dev-workflow.md quickstart, work/README, README, git-workflow.md, whats-new, grind-session, agents-rules.
- Agent load order: philosophy-and-scope, architecture, AGENTS.md, CLAUDE.md, README table, `agents-rules.md`.
- "What's new" content duplicated in whats-new.md, CHANGELOG.md (2.8k lines), upgrading.md "Upgrading from 0.2.x", install-and-usage "Upgrading from 0.2.x", orchestration.md "Upgrading from 0.2.x".
- Quickstart blocks ("Use this doc when / Not for / Must know / Read further for") are a good pattern but each file's "Must know" re-states other files' rules, so each is a copy to maintain.
- Flow diagram: architecture.md's mermaid and philosophy's mermaid are two partial copies; neither shows the orchestration/review lane that is now most of the product.
- `agents-rules.md` embeds `<!-- prevents | enforced | ref -->` comments for each rule (95 lines, ~half comments). Useful for maintainers, but they ship to every consumer repo and are loaded by every agent (agents read HTML comments).

## 3. Doc heft and reading paths

Layers currently mixed in `docs/` (classification by content)
- Reference (stable): roadmap-authoring (400), git-workflow (384), orchestration (400), orchestration-review (400), orchestration-workers (399), orchestration-models (360), orchestration-roster (146), orchestration-chores (124), grind-session (500), archiving (274), agent-search (220), roadmap-history (205), acceptance-evidence (67), file-limits (12), pm-gui (59), upgrading (65).
- Tutorial / workflow guides: install-and-usage (375), pm-workflow (400), dev-workflow (395), brainstorming (391), pm-gui-brainstorm (190), pm-llm-review (161), optional-ai-tooling-patterns (260), install-release-candidates (84).
- Maintainer-only (not for adopters but live in the same dir): release-runbook (898), contributor-guide (400), toolkit-development (58), agentic-sandbox-runbook (400), supply-chain-security (188), git-workflow-parallel-prs (48), context-regressions.yaml (200), pm-gui-brainstorm (partly).
- Design/history: design-notes/ (26 files, ~6,000 lines; its own README admits 13 of ~25 are "historical triage" and two are verbatim external proposals of 858 and 1,089 lines); whats-new (129, release notes).
- Overlap clusters: (a) five orchestration docs (1,429 lines) + grind-session (500) + dev-workflow (395) + git-workflow (384) all describe the leaf lifecycle; (b) whats-new / upgrading / install-and-usage upgrade sections / CHANGELOG; (c) toolkit-development / contributor-guide / CLAUDE.md / AGENTS.md / git-workflow-parallel-prs / release-runbook for maintainer flow; (d) philosophy / architecture / README "what it is" / purpose.

Reading path for an **agent starting a toolkit task** (AGENTS.md load order, plus what the harness auto-loads)
- Auto-loaded: CLAUDE.md 113 + AGENTS.md 60 = 173 lines (the two overlap).
- Load order: purpose 5 + principles 11 + constraints/README 17 + supply-chain 188 + fixture manifest 7 + fixture phases 107 (merged graph; "your node plus parents only" in theory) + fixture planning README 21 + fixture sheets (7 files / 279 lines; ancestors + node maybe ~80-150) + fixture shared/README 23 = about 380 minimum, ~660 if sheets read in full.
- Total start-of-task: roughly **550-830 lines**, of which 188 (supply chain) is irrelevant to most tasks and the fixture graph is explicitly "not the toolkit's roadmap". v0.2.3 same path: AGENTS 46 + CLAUDE 113 + 5 + 5 + 17 + 155 + 7 + 107 + fixture planning/shared, i.e. roughly 450-700. The toolkit path grew only ~15% because the heft moved elsewhere: the *task-specific* docs an agent then needs are now 400-line files; e.g. any review-gate change needs orchestration.md (400) + orchestration-review (400) + a design note (287) before editing.
- Real work on the product roadmap (`sr/`) is not covered by the load order at all; an agent reads `sr/vision.md` and `sr/constitution/` only if it finds them, and these differ from root `constitution/`.

Reading path for a **consumer agent** (shipped `.specyrd/AGENTS.md`): agents-rules 95 + stub 23 + team 11 + CLAUDE block 11 + load-order items 1-3 (shipped, short) + supply-chain doc (188, shipped in every consumer) + `roadmap-context.md` digest (grows with roadmap) = ~330 lines + digest, with the rules file itself being ~50% HTML comments. Reasonable. But the consumer's *reference* docs (orchestration, workers, models...) are only in the toolkit repo / PyPI-less; adopters hit "see docs/orchestration.md in the specy-road repository" with no pinned link.

Reading path for a **new adopter** (README -> install-and-usage -> pm/dev/git/orchestration): README 132 + install 375 + roadmap-authoring 400 + dev-workflow 395 + git-workflow 384 + pm-workflow 400 = ~2.1k lines to be productive with 0.2.x features; adding the 0.3.1 lane (orchestration 400 + review 400 + workers 399 + models 360 + roster 146 + chores 124 + grind 500 = 2.3k) = **~4.4k lines**. v0.2.3: README 107 + install 332 + authoring 396 + dev 400 + git 173 + pm 399 + grind 425 = ~2.2k. README's "Where to read next" is a 24-row table with no tiering; the only "start here" hint is the getting-started section which links 14 docs.

Symptoms that docs are shaped by the cap rather than by topic: 9 files at exactly 400 lines; `grind-session.md` had a "sat one line under the 400 cap" override comment; release-runbook override raised to 900 after each incident (footgun accretion); the verbatim research files needed their own overrides (the constraint was relaxed to hold material that should be outside `docs/`).

## 4. Recommended lean doc architecture

Principle: one canonical home per topic, tier by audience, keep history out of `docs/`. Target: adopter docs ~3.5k lines, agent start-of-task <= ~250 lines, maintainer docs separate.

A. Constitution (amend; see C)
- `constitution/purpose.md`: keep, add a "Scope" paragraph and a "Not" list.
- `constitution/principles.md`: split into "Product invariants" (4-8) and "Engineering rules for this repo" (1-3, 9). Make each principle self-contained (no dependency on a design note).

B. Agent entry (single source)
- Make `AGENTS.md` the only agent entry; reduce CLAUDE.md to a 10-line shim ("Read AGENTS.md; Claude-specific: ...") and move the git-workflow/branching text to `docs/toolkit-development.md` once. Make the version-numbers rule one section, linked from the rest.
- Rewrite the load order into task-conditional: always: purpose, principles, constraints (33 lines). Then by task type: orchestration/review -> `docs/orchestration.md`; roadmap data -> `roadmap-authoring.md`; dependencies/release -> supply-chain/runbook. Drop supply-chain from the default order (saves 188 lines) in both AGENTS.md and the consumer `agents-rules.md`. Drop fixture reading from the default order unless the task is about the fixture; add `sr/` vision/planning for roadmap work on the WIP line.
- Strip the `<!-- prevents|enforced|ref -->` comments from the shipped `agents-rules.md` (keep them in a maintainer-only provenance file or `docs/design-notes/`).

C. Scope amendment: **yes, amend the constitution to bound scope.** Suggested text for purpose.md/principles:
"specy-road governs a repo's plan and its review trail. It is not an agent runtime, model catalogue, CI system, ticket tracker, or IDE integration: it launches an agent only to record who ran which leaf at which commit, and it ships no capability that would exist without a roadmap node (or a recorded review) to attach it to. Features that fail that test (e.g., `chore` workers with no node, vendor `--help` captures, per-model prompting guides, usage/billing accounting) go to a clearly marked optional extra or out of the repo." Add admission test: "Does this feature need a roadmap node, a claim, or a recorded review to make sense?" and a rule for the vendor-facts layer (shipped as data refreshed independently of the wheel, with an expiry date). Also reword principle 5 to "the coordination CLI and workers run no daemon"; list `gui` as an explicit optional server; decide whether principle 8 permits `chore` and `session guard` or amend to name them as the sole exceptions.

D. Single source of truth by topic (what each file owns; others link, never restate)
| Topic | Owner doc | Others |
|---|---|---|
| Purpose, scope, non-goals | constitution/purpose.md | philosophy-and-scope.md shrinks to "what is opinionated / what is not" (about 40 lines), delete positioning section or move to design-notes |
| Roadmap data model | roadmap-authoring.md | architecture.md merged in (one layer table + one flow diagram incl. review lane) |
| Leaf lifecycle (pickup -> finish) | dev-workflow.md | git-workflow.md keeps only `git-workflow.yaml` field reference + registry rules; orchestration.md quickstart drops its copy of the flow |
| Review gate + policy | orchestration.md (+ orchestration-review.md as appendix: file shapes, signing) | philosophy/README link only |
| Workers, models, roster, chores | merge orchestration-workers + -roster + -chores into one "workers" reference; keep orchestration-models separate | README one row |
| Loop | grind-session.md (reference only; plan/exit codes/events) | |
| Upgrades | upgrading.md only; whats-new = one-screen-per-release; install-and-usage links in | CHANGELOG remains complete list |
| Install + RC | install-and-usage.md; install-release-candidates folded as a section; no pinned rc number in docs (use `X.Y.ZrcN` placeholder) | |
| Maintainer flow | one `docs/maintainers/` folder: toolkit-development (absorbing CLAUDE.md git policy), contributor-guide, release-runbook, supply-chain-security, agentic-sandbox-runbook, git-workflow-parallel-prs, context-regressions.yaml | |

E. Cut / move / archive
- Move `docs/design-notes/*` (6.0k lines) out of `docs/` into `design-notes/` at repo root (or `sr/`), un-capped; keep only the 6-7 "live design" notes where the code still follows them (v0-3-0 slices, worker orchestration, brainstorm v2, regression-prevention, agent-guidance, 3 PM-GUI notes). Move the 13 "historical triage" notes and the two verbatim research files (858 + 1,089 lines) to `sr/` or an archive branch; delete the file-limits overrides for them.
- Move `release-runbook.md` (898) to maintainers/ and split: procedure vs "footgun" reference.
- Fold: architecture.md -> roadmap-authoring.md; install-release-candidates.md -> install-and-usage.md; acceptance-evidence (67) and file-limits (12) into the docs that cite them; pm-gui-brainstorm + pm-llm-review into pm-gui.md as sections or one `pm-gui.md` reference; git-workflow-parallel-prs into git-workflow or maintainers.
- Cut `optional-ai-tooling-patterns.md` (260): by its own text these patterns are "not part of specy-road's contract"; keep a 40-line pointer or move to `suggested_prompts/`.
- Templates: ship model-profiles and `harness-captures` as data via `specy-road refresh-profiles` from the wheel, not scaffolded into each consumer repo (consumer tree gains ~4.6k lines it will never edit; `docs/model-profiles-research-notes.md` 253 lines too). Keep `roadmap/orchestration.yaml` + a minimal roster; scaffold profiles only on `orchestrate`/`models init`. Date-stamp every profile (they name models that will be retired; v0.2.3 shipped none).
- Reduce `specyrd/commands/` (26 stubs) to what the hook/skill model still uses; delete the pre-0.3 command stubs after one release; update README step 7 and contributor-guide section accordingly.
- Remove the duplicated `sr/constitution/` (a copy of the root one) or make root the only copy.

F. Governance for docs themselves (add to constraints)
- A budget: total adopter docs <= N lines; "one owner per topic" checked by a small script (grep for `executor never reviews`-type duplicated paragraphs is overkill; instead require every doc to start with `Owns:` and `Does not own:` lines, which the quickstart blocks nearly provide already).
- Do not pin the RC number outside CHANGELOG, pyproject and one install doc; add a `validate`/CI check that whats-new's top version equals pyproject's base version.
- Extend the docs cap rationale: replace line cap on `docs/**/*.md` with a per-file soft cap (warn) so the split follows topics, not the 400 boundary.

## Priority fixes (small, high-value)
1. Fix the contradiction on "toolkit roadmap not defined" (AGENTS.md, toolkit-development.md) - 2 lines.
2. Drop supply-chain-security from the default load order (AGENTS.md + `agents-rules.md`).
3. Update whats-new / install-release-candidates / upgrading from rc1 to a placeholder or rc3.
4. Update README step 7 and contributor-guide IDE-stub section to the skills model.
5. Amend purpose.md with the scope/not list and split principles.
6. Strip provenance comments from shipped `agents-rules.md`; fix consumer-unresolvable refs (`docs/design-notes/...`, "see docs/orchestration.md in the specy-road repository").
