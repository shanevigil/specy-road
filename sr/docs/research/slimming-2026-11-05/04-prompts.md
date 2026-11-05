# 04 - Suggested prompts applied to specy-road itself (read-only)

Method: snapshot at WIP b216d799 was copied to a scratch dir; only `validate`, `init project --dry-run` (run in an empty dir) and `-h` were executed. Nothing under the live repo was touched. The copy is not a git repo, so a root-level `validate` printed `missing roadmap/registry.yaml` instead of following `.specyrd/manifest.json` `project_root: sr`; `validate --repo-root sr` gave "OK: roadmap and registry validate" plus overlap warnings and M5/M6 milestone-review notices. That is an artefact of the copy, but it shows the nested-layout auto-resolution depends on a git root.

## 1. bootstrap-governance, applied to this repo

What the prompt would produce:
- `vision.md`: a short paragraph on the future state.
- `constitution/purpose.md`: why the kit exists, in plain language, with no enforceable limits.
- `constitution/principles.md`: how the team decides (roadmap-first, contracts over tribal knowledge).
- `constraints/README.md`: a table of rules, each with where it lives and the command that checks it.
- `constraints/file-limits.yaml`: globs tuned to `specy_road/`, `tests/`, `gui/`.
- `shared/README.md`: an index of contracts.
- A verification run of validate, export --check, digest --check and file-limits.

Compared with the real files:
- `constitution/purpose.md` is 5 lines and close to what the prompt asks for.
- `constitution/principles.md` has 9 items. 1-3 and 9 are what the prompt expects (consumer-first, dogfood, small changes, docs win). 4-8 are product design commitments:
  - the CLI never calls a model;
  - harness-native, no daemon and no MCP server;
  - separated roles with recorded review;
  - the agent advises and the human decides;
  - augment the harness's tools.
  They are architectural and policy rules, not "how the team decides". The prompt would not generate them. That is probably fine, since they are the actual product constitution, but it means principles are doing the work of a design doc.
- `constraints/README.md` matches the prompt's table shape, but the repo has also grown `clone-baseline.json` and `test-private-imports-baseline.txt` (about 190 lines of baselines) that the table does not list. The root README is a toolkit-only variant. The scaffold also has `constraints/review-lessons.md`, which neither the prompt nor the repo's constraints mention.
- `sr/vision.md` (a single long sentence) covers the product plus "the toolkit is run this way... each release candidate is judged by what adopters report back". The root repo has no `vision.md` at all.

What this says about scope drift:
- The prompt's governance model is small: purpose, principles, enforceable limits and contracts. The repo's real governance is that plus three more layers.
- The first extra layer is behavioural rules baked into the managed AGENTS block and `.specyrd/AGENTS.md`, about 2,200 words of agents-rules plus a 560-word block. These cover shared checkouts, git writes, lean-change and test rules, review roles, and version numbers.
- The second is a runbook and policy layer (release-runbook, orchestration, supply-chain).
- The third is the baselines.
- Governance has migrated from "constitution" into agent-instruction prose. The constitution itself stays small, but an agent must read far more than the constitution to behave correctly.
- Principles 4-8 plus the `sr/` roadmap show the product's identity has widened from "roadmap-first graph + validators" (Purpose) to "multi-agent orchestration with workers, reviewers, rosters, hooks and guards". Purpose.md says "prescribes a review contract", but it does not mention workers, grinding, chores, rosters or model profiles, which dominate the roadmap (see section 3). Purpose is stale relative to scope, or scope has outgrown purpose.

## 2. bootstrap-agents-md, applied to this repo

What the prompt would produce: a consumer-style `AGENTS.md`, meaning a short managed block between markers that points at `.specyrd/AGENTS.md`, with seven floor rules and no restated load order. Project-specific text goes outside the block or in `.specyrd/AGENTS.team.md`. `CLAUDE.md` gets the `@.specyrd/AGENTS.md` and `@.specyrd/AGENTS.team.md` imports plus a "specy-road (consumer)" section. The prompt is explicitly for an application repo and says not to patch the `specy-road/` clone.

Applied to this repo it does not fit:
- The prompt's consumer/toolkit boundary is inverted here. This repo is the toolkit.
- The repo's own root `AGENTS.md` says as much ("for contributors working on the package").
- The nested `sr/AGENTS.md` (19 lines) is the only one that matches the prompt's output: a managed block, "written by specy-road 0.3.1rc2".
- So the prompt's output exists only for `sr/`, which is stripped before `main`. The root toolkit docs are hand-written.

Comparison, by size and read burden:
- Prompt output: about 560 words (managed block) plus the pointer to `.specyrd/AGENTS.md` (about 2,200 words) plus `AGENTS.team.md`. That is roughly 2,800 words, 3 files.
- Root `AGENTS.md`: 60 lines, 796 words, with a 7-item "load order" of which items 5-7 are about a fixture, not the product.
- Root `CLAUDE.md`: 113 lines, 940 words. It says "Read AGENTS.md first", then repeats the load order, the roadmap model, commands, the git workflow policy and release rules.
- Combined, an agent that follows both reads about 1,740 words directly. It also fetches 3 constitution/constraint files, `docs/supply-chain-security.md`, and the fixture roadmap and planning README, so about 8 or more files before work starts. The sr/ product roadmap is not in the required order at all. Real toolkit work lands in `sr/`, so an agent following the load order reads fixture data, not the real roadmap.
- Duplication: the load order appears in both `AGENTS.md` and `CLAUDE.md`, which is the exact "two load orders drift" failure the prompt warns about. The branch policy appears in `AGENTS.md`, `CLAUDE.md` and `docs/toolkit-development.md`. The version-number rule appears in `AGENTS.md`, `CLAUDE.md` and a Cursor rule.
- The root CLAUDE.md describes `sr/` roadmap commands in prose only, and the "Roadmap model" bullets contradict `AGENTS.md`'s last line ("A first-class roadmap for the toolkit itself is intentionally not defined here yet") because `sr/` exists on WIP.
- The sr/ side is clean: the block is short, the floor rules are explicit, and `AGENTS.team.md` and `AGENTS.local.md` are named.

## 3. bootstrap-roadmap and brainstorm-roadmap applied to `sr/roadmap` + `sr/planning`

Shape: 251 nodes, 232 tasks, 15 phases, 4 milestones, 252 planning sheets (about 432 KB), `validate --repo-root sr` passes. Only M12, M13, M14, M15, M2 and M8 have open work. Counts are leaves per phase.

Classification (my reading of titles):
- Core purpose (roadmap graph, validators, context, brainstorm, outcomes): M1 Adopt (1), M4 Brainstorm and roadmap editing (18), M5 Agent context and outcomes (8), M2 Outcome record pilot (2 empty milestones, 0 leaves), M9 Regression prevention (11, partly). About 40 leaves, roughly 17 percent.
- Orchestration and harness plumbing (workers, rosters, models, hooks, usage, harness facts, performance): M8 Harness compatibility (7), M10 Agent loop performance (20), M12 Harness engineering (8), M6 rc release (2), M7 recurring research (2). About 39 leaves.
- Fixes for findings from prior rounds: M3 rc1 feedback (18), M11 rc2 field feedback (80), M13 rc3 upgrade friction (14), M14 nested repos and review-gate integrity (13), M15 rc3 install safety, multi-harness reviewers, parallel-grind friction (30). About 155 leaves, roughly two thirds of all tasks. Phases are named by the feedback round that produced them, not by capability.

Coherence observations:
- The graph is valid and fully linked, but it is a changelog-shaped backlog, not a plan. The roadmap structure is "rc round N" buckets.
- Titles in M13-M15 are long sentences (80-200 chars) that read like acceptance criteria or release notes, and are not goal names. Several (M15.13, M15.14, M15.17, M15.22, M15.25-30) bundle several behaviours.
- The only phases with goal fields filled in are M2 and M5. Most nodes lack goals.
- Status inconsistencies: phases M10, M11, M12, M13, M14, M15 and M5-M9 all show "Not Started" with every child Complete, while M3 and M4 are "Complete". The rollup works, but the stored `status` is inconsistent in use.
- Only 3 of the 4 milestones' (M2.1, M2.2, M12.4, M14.4) children exist, and M2.1/M2.2 are unstaffed.
- M11 is 80 leaves from one feedback round. M11.1-M11.47 include many "one readiness rule", "ready command", "profile aliases", "small CLI fixes" items.
- Claiming from the real purpose: the vision is "roadmap-first coordination". Only about one sixth of leaves touch the roadmap graph, brief, digest or brainstorm.

Where a brainstorm would suggest consolidating or cutting:
1. Fold M13 + M14 + M15 (57 leaves) into capability-named milestones: `upgrade`/refresh (M13.1-M13.14), nested repos (M14.1-M14.4), review gate integrity (M14.5-M14.11, M15.16-M15.30), worker loop (M15.13, M15.14, M15.25-M15.27). Many leaves overlap: M13.12 and M15.22 (notices on untracked/ignored files), M14.10/M12.4.1 (findings trends and quality scores), M14.8 and M15.20 (zone checks before review/plan time), M15.17 and M15.29 (review packet and RUN record).
2. Cut or park: M12.4.1 to M12.4.3 (quality scores, tech-debt ledger, per-model evidence) and M12.6 are speculative signals with no adopter evidence. M15.19 (Cursor cost estimate display name) and M15.27 (worker usage counting) are narrow. M13.14 (best-effort hint) and M13.13 (`upgrade --prompt`) overlap with M13.8 and M13.11.
3. Merge: M10 (20 leaves of timing/usage events) is performance plumbing for a feature the Purpose does not name. M10.20 Terra pilot, M10.6 reviewer-effort measurement and M8.7 runtime facts verification could be one measurement milestone.
4. M2 has two goals and no leaves. Either promote them to actual leaves or remove them; they are the only items about "whether it mattered", which the vision cites.
5. Gap a brainstorm would flag (the prompts ask "which part got no ideas"): authoring and onboarding. For example the `init project` to first merged leaf path, graph editing UX, and cutting the prompt and rules reading cost have few leaves relative to review/worker internals.

## 4. The prompts themselves: alignment and problems when followed

Verified OK (every named command exists): `init project --dry-run`, `refresh-stubs`, `refresh-schemas`, `refresh-profiles`, `upgrade`, `scaffold-planning`, `search`, `history`, `session`, `review-packet`, `worker`, `doctor`, `list-gates`, `why-blocked`, `grind-session`, `do-next-available-task`, `finish-this-task`, `abort-task-pickup`, `archive`, `restore-archive`, `digest`, `export`, `file-limits`, `add-node`. Brainstorm flags used (`start --topic --under --count`, `frame --answer --allocation`, `add-idea --title --rationale --kind --effort --origin`, `revise --cluster --overlap --critic --recommendation --why`, `add-evidence --url --quote --supports --stance --tool`, `promote --dry-run`, `next-round --count`) all exist. The scaffold files named (`vision.md`, `constitution/`, `constraints/`, `shared/README.md`, schemas, `planning/README.md`, `roadmap/git-workflow.yaml`, `registry.yaml`, `orchestration.yaml`, M1/M1.1 sheets, `work/` templates) all exist in `templates/project/` and in the dry-run listing (66 paths). `git-workflow.yaml` keys named (`on_complete: pr`, `require_implementation_review_before_finish`, `require_implementation_before_finish`, `track_worker_logs`) are in the template.

Problems and ambiguities:
1. Docs are referenced that adopters do not get. All four prompts cite `docs/roadmap-authoring.md`, `docs/git-workflow.md`, `docs/orchestration.md`, `docs/brainstorming.md`, `docs/dev-workflow.md` and `docs/pm-workflow.md`. The scaffold only ships `docs/supply-chain-security.md` and `docs/model-profiles-research-notes.md`. The governance prompt calls them "maintainer documentation (read if available)", but bootstrap-roadmap makes `roadmap-authoring.md` the authority for chunk shapes and immutability, and brainstorm's reference list names `docs/brainstorming.md` as "the full command surface". Following the prompt in an adopter repo, the agent has nothing to read unless it finds the toolkit clone or the installed package. The prompts never say where to find them, or that `upgrade` copies only docs named in the load order.
2. Governance deliverables list is incomplete versus the scaffold. The dry-run writes `constraints/review-lessons.md`, `model-profiles/*`, `research/README.md`, `docs/*`, `work/*.template.md`, `roadmap/orchestration.yaml` and `.specyrd/*`. The prompt's table covers only 6 paths, and says "match the structure from init project", so an agent has to guess whether to touch the rest.
3. Governance prompt Phase 2 leaves `AGENTS.md`, `CLAUDE.md` and `.specyrd/` out, correctly, but the "scaffold missing" fallback ("take the file list from `--dry-run`") is not workable. A dry-run lists paths, not content. The only real path is to run `init project`.
4. Ordering conflict: the README says governance first "after `init project`", but governance also says to run `init project` if the scaffold is missing, and bootstrap-agents-md says it is last. `AGENTS.md` is created by `init project` in step 1 anyway, so step 3's "create or update AGENTS.md" is really "merge".
5. The roadmap prompt asks the agent to hand-author JSON chunks with UUID `node_key`s and filename-bound planning sheets. It never mentions `specy-road add-node`, `edit-node` or `scaffold-planning` as the way to create nodes (only `scaffold-planning` appears, optionally). The brainstorm prompt's "through the same path as `add-node`" is the only mention. Hand-authoring risks invalid UUIDs, id/filename mismatches and unsorted chunks. The `add-node` CLI exists and should be primary.
6. Density. bootstrap-agents-md (142 lines) is a single-page dump of rules that `.specyrd/AGENTS.md` already holds. Phase 3 reproduces the shared-checkout and lean-change rules "so a hand merge does not lose them" while Phase 2 tells the agent never to restate them. That is internally contradictory (and creates a third copy that drifts). The git-workflow.yaml bullet in bootstrap-roadmap is one 400-word paragraph.
7. bootstrap-agents-md assumes a consumer app with an optional `specy-road/` clone. For specy-road itself (or any repo that is the toolkit) the "do not patch specy-road/**" merge would be wrong, and nothing in the prompt says so.
8. Brainstorm prompt: "Run this before reading anything else ... even if AGENTS.md says to read the digest first" conflicts with the load order the other prompt installs. It is deliberate, but an agent with the `CLAUDE.md` import loads rules saying the opposite before it ever sees the prompt. `--count 30` differs from the CLI default of 20 without saying why. `--rounds`, `--profile`, `--panel`, `park`, `decide`, `merge` and `cluster` exist but are not mentioned. Brainstorm expects `[ANCHOR]`; if the roadmap is nested (`sr/`), the agent must run commands from the git root and rely on auto-resolution.
9. Nested layout is mentioned only in the agents prompt. The governance and roadmap prompts use bare `roadmap/`, `constitution/` paths and `[REPO_ROOT]`, which in the nested layout is the wrong directory (my copy-without-git run showed what happens: the CLI looked in the root and reported a missing registry).
10. bootstrap-roadmap says validate may warn about schema skew and to use `upgrade`, but gives no instruction for the common first-run case where `validate` after init reports notices (this repo's own `validate` prints overlap warnings and milestone-review notices); the prompt says "resolve all errors", not warnings.

Overall: formats and command names are in good shape (no stale flags found). The risk is not drift in names but (a) docs adopters cannot reach, (b) hand-authoring where a CLI exists, (c) rule text copied into prompts that the rules file owns, and (d) the prompts' consumer-only framing, which fits neither this repo nor nested layouts.
