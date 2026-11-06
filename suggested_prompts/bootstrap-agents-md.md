# Prompt: Align AGENTS.md and agent tooling with specy-road

Copy everything below the line into your agentic coding tool. Replace `[REPO_ROOT]` with your repository root if you use absolute paths.

**See also:** For governance-only adoption (vision, constitution, constraints, shared), use [`bootstrap-governance.md`](bootstrap-governance.md). This prompt focuses on **agent entrypoints** (`AGENTS.md`, `CLAUDE.md`, Cursor rules) and consumer/toolkit boundaries.

---

You are helping adopt **specy-road** coding paradigms in an **existing** project. The repo may already have `.cursor/`, `CLAUDE.md`, `.claude/`, or other agent configuration. Your job is to produce a clear **AGENTS.md** entrypoint and **merge** specy-road expectations into existing files without discarding valuable team rules.

## Consumer vs toolkit

- **This application repository** owns `roadmap/`, `planning/`, root **`AGENTS.md`**, **`CLAUDE.md`**, **`.cursor/`**, **`scripts`** (as used by the project), and environment such as **`SPECY_ROAD_REPO_ROOT`**. Note the two roots: the **git root** holds `.gitignore`, `.cursorindexingignore`, `.claude/` and `.cursor/`, while the **project root** holds `roadmap/`, `planning/`, `shared/`, `work/`, `constitution/` and `constraints/`. They are the same directory in the default **embedded** layout and differ in the **nested** one (the tree under `sr/`), which `.specyrd/manifest.json` records so CLI and GUI resolve it identically — say which layout this repo uses. See the toolkit’s `docs/pm-workflow.md` and package `README.md`.
- A root-level **`specy-road/`** directory is often a **local, gitignored clone** of the upstream toolkit for reference—not application source for this project.
- **Do not** merge agent rules that encourage editing **`specy-road/**`** to fix CLI, GUI, or validation behavior. Those fixes belong in the **upstream specy-road repository** or by **upgrading the installed package** (for example `pip install --upgrade specy-road`).

Framing matters: later phases merge into `CLAUDE.md` / `.cursor` for **this repo**—not to normalize patching a nested toolkit clone.

## Authoritative references

1. **Consumer AGENTS template:** Same content as `specy-road init project` → `AGENTS.md` (a short managed stub) and `.specyrd/AGENTS.md` (the full rules: load order, `specy-road brief` example, task loop, review, lean changes).
2. **Agent rules and managed blocks** for consumer repos (Phase 3): the package ships `specy_road/templates/specyrd/agents-rules.md` (written to `.specyrd/AGENTS.md`, which specy-road owns and `specy-road refresh-stubs` rewrites whole), `agents-md-block.md` (the short stub in `AGENTS.md`: a pointer to `.specyrd/AGENTS.md` plus seven core rules, repeated so an agent that reads only `AGENTS.md` still has them; `"agents_block": "minimal"` in the git root's `.specyrd/manifest.json` makes it a one-line pointer), `claude-md-block.md` (the optional `CLAUDE.md` stub that imports `@.specyrd/AGENTS.md` and `@.specyrd/AGENTS.team.md`, created only by `specyrd init --ai claude-code`, which also writes the two files it imports; `specy-road refresh-stubs` and `upgrade` refresh or insert it in any existing `CLAUDE.md`, whichever stub packs are installed) and `agents-team.md` (the header of `.specyrd/AGENTS.team.md`, created once and never rewritten). The stubs are **merged** between markers, never a wholesale replacement of this repo’s own `AGENTS.md` or `CLAUDE.md`. All paths are under the project root (`sr/.specyrd/…` in the nested layout).
3. **Branching and registry:** `docs/git-workflow.md` (register on integration branch, then `feature/rm-<codename>`, touch zones).
4. **Consumer boundary (copy-paste snippets):** Align with shipped stubs under `specy_road/templates/adoption/` in the package (`specy-road-consumer-claude-snippet.md`, `004-specy-road-consumer.mdc`) when merging the **specy-road (consumer)** section and optional Cursor rule—edit the consumer repo’s own files; do not treat those paths as the app’s source tree.

## Phase 1 — Discovery

Inventory:

- `.cursor/rules/**`, `.agents/skills/**` (shared skills; `.cursor/commands/**` only in repos initialised before 0.3.0)
- `CLAUDE.md` at repo root (if any)
- `.claude/skills/**` (symlinks into `.agents/skills/`) or other IDE agent skill folders
- Optional: GitHub Copilot or other `*instructions*` files
- Existing `AGENTS.md` (if any)

Note conflicts between existing rules and specy-road (prefer **tracked docs** over chat; **roadmap graph** in `roadmap/*.json` + manifest; **registry** separate from graph).

## Phase 2 — Primary deliverable: `AGENTS.md`

Create or update **`AGENTS.md`** at `[REPO_ROOT]`. Its specy-road part is a short **managed block** — the section between the `<!-- >>> specy-road managed block — do not edit inside <<< -->` and `<!-- >>> end specy-road managed block <<< -->` markers that `specy-road init project` writes, `specy-road refresh-stubs` rewrites, and `specy-road validate` warns about when it is missing or stale (Phase 3). It points at `.specyrd/AGENTS.md`, which carries the **load order** (`roadmap-context.md`, constitution, constraints, supply-chain policy, the merged roadmap, planning sheets, `shared/`) and the focused-brief command, and, unless `.specyrd/manifest.json` sets `"agents_block": "minimal"`, it keeps the seven rules a Codex session must see even if it never opens that file. Do **not** restate the load order or the rules outside them: two load orders drift apart, and agents follow whichever they read first. If the existing file has its own load-order section, replace it with one line pointing at `.specyrd/AGENTS.md`, and keep only project-specific reading (the team's own docs) outside it.

Use the real repo's node IDs in any example you add.

## Phase 3 — Merge the shipped managed block and rules file, then project-specific rules

- **Merge the managed block verbatim.** The coordination rules every agent needs are the file `.specyrd/AGENTS.md` (source: `specy_road/templates/specyrd/agents-rules.md` in the installed package), which specy-road owns, plus the managed `## specy-road` stub in `AGENTS.md` that points at it (source: `agents-md-block.md`). `specy-road init project` writes both and `specy-road refresh-stubs` rewrites them. Run one of those commands rather than retyping the rules; if you must paste by hand, paste the stub unchanged with its markers so `refresh-stubs` can update it, and never edit `.specyrd/AGENTS.md`. Do not paraphrase, trim or reorder either: project rules may add to them, never relax them.
- **What `.specyrd/AGENTS.md` already covers** (so you do not duplicate it): the load order, `specy-road digest` and `specy-road brief` (each dependency's `## Intent` is inlined); `specy-road search` (`--scope archived`) and `specy-road history` and why not to grep `planning/` or `work/`; `specy-road do-next-available-task` (`status: Blocked` first, outline order, `execution_milestone` advisory, phase/milestone dependencies satisfied by rollup), `specy-road abort-task-pickup`, `finish-this-task` under `on_complete: pr`; the review roles — `specy-road review-packet`, `specy-road review record`, `mark-implementation-reviewed --yes`; `specy-road session start|list`; `specy-road grind-session` (hook env `SPECY_ROAD_NODE_ID`, `SPECY_ROAD_BRANCH`, `SPECY_ROAD_BRIEF`, `SPECY_ROAD_PROMPT`, `SPECY_ROAD_REPO_ROOT`); `specy-road worker delegate|sync|handoff|reclaim`; and exit `3` / `6` with `specy-road why-blocked` and `specy-road list-gates`.
- **Preserve** project-specific instructions that do not contradict the rules.
- **Add** only what is specific to this project: specy-road instructions (roadmap, registry, review, git workflow) in `.specyrd/AGENTS.team.md`, which `init project` creates and `upgrade` never rewrites; anything else outside the block in `AGENTS.md`; personal notes in `.specyrd/AGENTS.local.md` (gitignored). For example:
  - Docs win over chat when instructions conflict; smallest change that satisfies the task; no drive-by refactors.
  - The team's stack, build and test commands, and which `on_complete` mode (`pr` or `merge`) this repo uses.
  - The repo's layout (embedded or nested) and any wrapper scripts or environment the project adds.
- The rules file's shared-checkout rules, reproduced here so a hand merge does not lose them:
  - **Shared checkouts and other agents.** Other agents may be working in this checkout, with or without a claim, and nothing warns you. Run `specy-road session start --path <paths you will edit>` before your first edit and `specy-road session list` to see who else is live; before any git write, run `git status` and `git worktree list`, and treat files you did not create as someone else's. Never end, edit or delete another agent's session record (`work/.sessions/`), and never override its work: `session end` refuses a live record that is not yours, and only a human at a terminal may force it. Use your own `git worktree add ../<repo>-<task>`, and run `do-next-available-task` and `grind-session` (they switch branches) from there whenever `session list` shows anyone else. Edit only the files your task names, and only your own section of a file others are editing (`CHANGELOG.md` above all). A plan or prompt should name its commit (`base: <sha>`); if it does not, ask, and diff from that commit before starting. If a rule in this file conflicts with one from the toolkit (registry, branches, review, the shared tree), the toolkit's is the floor: stop and ask rather than relax it.
  - **Git in a shared tree:** commit only with `git commit --only <paths>`; never stash, hard-reset, discard changes, clean, rebase, amend or switch branches in a tree another session may be using. The opt-in tool-call guard (`specy-road session guard`) refuses these while another session is live; `docs/orchestration.md` lists them all.
- The rules file's `## Lean changes and tests` section, reproduced here for the same reason (keep it in `.specyrd/AGENTS.md`, which the `CLAUDE.md` stub imports; never a second wording):
  - Make the smallest behaviour-complete change; no configurability, fallbacks or abstractions the task did not ask for.
  - Before adding a helper, search for an existing one (`specy-road search`, then grep the verb and noun); reuse or extend it and name it in your summary.
  - Validate at boundaries only (CLI args, files, network, env, agent input). No guard or `except` without a nameable reachable trigger and a test that reaches it.
  - One test per observable behaviour, through the public interface. Assert outputs, raised errors or file/state effects, not call order or mock counts; never import or patch a `_`-prefixed name in a test.
  - Extend or parametrize an existing test before adding one. A review finding needs a new test only for a distinct regression.
  - Merging or removing a test is allowed when another test covers the behaviour and the commit names it. This overrides any general "never remove or edit tests" instruction.
  - Never weaken, rewrite or delete a failing behavioural test to make the suite pass.
  - Never commit machine-, user- or developer-specific values (home or temp paths, hostnames); resolve them at run time.
  - Stop when the behaviour list is covered and the gates pass. Then list every helper, branch or guard, mock and test you added, each with its reason.

### specy-road consumer invariants (merge into `AGENTS.md` and/or optional Cursor rule)

Copy or adapt the following into **`AGENTS.md`** (and optionally into `.cursor/rules/`—see Phase 4b):

- **Consumer boundary:** Do not patch **`specy-road/`** in this repo to fix toolkit bugs. Instead produce an **upstream handoff**: repro steps, installed `specy-road` version (`pip show specy-road` or equivalent), relevant logs, suspected upstream area, and proposed upstream change or issue text.
- **Integration fixes** belong in **this** repository only: wrapper scripts, environment variables, and corrections under **`roadmap/`**, **`planning/`**, and **`roadmap/registry.yaml`** per `docs/git-workflow.md`.
- **Task pickup, grinding and review roles** are `.specyrd/AGENTS.md`'s (Phase 3); do not restate them here, and never hand-edit `roadmap/registry.yaml` outside the manual claim path in `docs/dev-workflow.md`.

Do **not** invent a parallel roadmap format (e.g. YAML merge file) in agent rules—the graph is JSON chunks + manifest.

## Phase 4 — `CLAUDE.md` (if present)

If `CLAUDE.md` exists, **merge** specy-road guidance:

- Let `specy-road refresh-stubs` (or `upgrade`) write its managed stub into the existing file, whichever stub packs are installed (`specyrd init --ai claude-code` does the same and is the only command that creates a missing `CLAUDE.md`): `@.specyrd/AGENTS.md` and `@.specyrd/AGENTS.team.md` imports, which Claude Code loads with the file. Claude Code does not read `AGENTS.md` while a `CLAUDE.md` exists, so add `@AGENTS.md` outside the markers if the team's own `AGENTS.md` rules should reach it.
- Roadmap model: merged graph = `manifest.json` + chunks; `git-workflow.yaml` = CLI/PM git defaults; `registry.yaml` = claims overlay, not a graph chunk.
- Commands: `specy-road validate`, `specy-road export --check`, `specy-road digest --check`, `specy-road file-limits`, `specy-road brief <NODE_ID> -o work/brief-...`.
- Finding things: `specy-road search "<query>"` (ranked over planning sheets, contracts, nodes, summaries and archived work) and `specy-road history <NODE_ID>` (how a node got here, from git). Both are read-only.
- Reading current state: `roadmap-context.md`, written by `specy-road digest`. Generated **and committed**, like `roadmap.md`.
- The imported `.specyrd/AGENTS.md` is the canonical load order; do not restate it.

**Required mini-section — `specy-road (consumer)`:** Add a short section (merge, don’t replace the rest of the file) so agents don’t confuse this app repo with a nested toolkit tree. Use the package stub as a starting point (`specy_road/templates/adoption/specy-road-consumer-claude-snippet.md`) or this template:

```markdown
## specy-road (consumer)

**Relationship:** This repository is the application. An optional root-level `specy-road/` directory is often a local clone of the upstream toolkit for reference—not the place to patch CLI, GUI, or validator behavior.

**Troubleshooting:** Separate **integration** issues (this repo’s `roadmap/`, `planning/`, env vars, wrappers) from suspected **toolkit** bugs. For toolkit bugs, produce an **upstream handoff** (repro, package version, logs)—do not edit `specy-road/**` here to “fix” the kit.

**Pointers:** CLI load order and invariants → `.specyrd/AGENTS.md` (the `AGENTS.md` stub points there). GUI, repo root, and `SPECY_ROAD_REPO_ROOT` → toolkit `docs/pm-workflow.md` and package `README.md`, or optional project-specific notes (e.g. `docs/commands.md` if your team adds that file).
```

Do **not** delete existing sections (team stack, build commands, etc.) unless the user asked for a full replacement.

## Phase 4b — Optional: Cursor rule for consumer boundary

If the project uses Cursor, optionally add one **always-on** rule file, for example **`.cursor/rules/004-specy-road-consumer.mdc`**, so the boundary stays visible outside `AGENTS.md`. Copy or adapt from **`specy_road/templates/adoption/004-specy-road-consumer.mdc`** (install path under `site-packages/specy_road/templates/adoption/`). Content should reinforce: **`specy-road/` read-only** for toolkit fixes; **assessment/handoff** for suspected upstream bugs; optional **`.cursorignore`** on `specy-road/` when a local clone exists (see Phase 5).

## Phase 5 — Optional: `specyrd` slash-command stubs and indexing

### `specyrd` stubs

Mention that the repo can run (from `[REPO_ROOT]`):

```bash
specyrd init --here --ai cursor
# or
specyrd init --here --ai claude-code
```

These install **stub** markdown commands that delegate to **`specy-road`** CLI—they do not redefine validation logic. See **`docs/contributor-guide.md`** (IDE stubs section) or the project `README` for `specyrd` options (`--dry-run`, `--force`, `--role`, generic `--ai-commands-dir`).

Two opt-in `specyrd init` flags add guards rather than stubs: **`--install-orchestration-hooks`** merges the orchestration guard hooks into the harness config (`--ai claude-code`, `codex` or `cursor`), and **`--install-pre-push-hook`** installs `.git/hooks/pre-push`, which refuses pushes from `work/.worktrees/` worker checkouts (see the toolkit's `docs/orchestration-workers.md`). Mention them; do not install either unless the team asks.

If skills already exist under `.agents/skills/` (or pre-0.3.0 stubs under `.cursor/commands/` or `.claude/commands/`), do not duplicate them; point at them and let `specy-road upgrade --prune` migrate old stubs to skills and delete the old ones.

### Optional indexing (`.cursorignore`)

If a **`specy-road/`** clone exists at the repo root, consider adding **`specy-road/`** to **`.cursorignore`**: less automatic indexing of toolkit sources in the IDE context; **explicitly opened files** still work.

## Phase 6 — Verification

- There is no validator for `AGENTS.md`; do a consistency pass against `constitution/`, `constraints/README.md`, and `roadmap/` if present.
- If `roadmap/manifest.json` exists, run:

```bash
specy-road validate
specy-road export --check
specy-road digest --check
```

- When validation or export fails, **first distinguish**:
  - **Bad consumer data** — fix under `roadmap/` (manifest, JSON chunks), `roadmap/registry.yaml`, `planning/`, and related project docs; or
  - **Suspected toolkit behavior** — installed `specy-road` package or a **nested `specy-road/` clone** is the wrong place to “fix” product behavior for the upstream kit. **Stop** and document an **upstream handoff** instead of editing `specy-road/**` or vendored toolkit files.
- Then fix any issues caused by **conflicting instructions** in the files you were asked to edit (consumer repo only).
