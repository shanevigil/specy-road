# Prompt: Align AGENTS.md and agent tooling with specy-road

Copy everything below the line into your agentic coding tool. Replace `[REPO_ROOT]` with your repository root if you use absolute paths.

**See also:** For governance-only adoption (vision, constitution, constraints, shared), use [`bootstrap-governance.md`](bootstrap-governance.md). This prompt focuses on **agent entrypoints** (`AGENTS.md`, `CLAUDE.md`, Cursor rules) and consumer/toolkit boundaries.

---

You are helping adopt **specy-road** coding paradigms in an **existing** project. The repo may already have `.cursor/`, `CLAUDE.md`, `.claude/`, or other agent configuration. Your job is to produce a clear **AGENTS.md** entrypoint and **merge** specy-road expectations into existing files without discarding valuable team rules.

## Consumer vs toolkit

- **This application repository** owns `roadmap/`, `planning/`, root **`AGENTS.md`**, **`CLAUDE.md`**, **`.cursor/`**, **`scripts`** (as used by the project), and environment such as **`SPECY_ROAD_REPO_ROOT`** (repo root discovery for CLI/GUI; see the toolkit’s `docs/pm-workflow.md` and package `README.md`).
- A root-level **`specy-road/`** directory is often a **local, gitignored clone** of the upstream toolkit for reference—not application source for this project.
- **Do not** merge agent rules that encourage editing **`specy-road/**`** to fix CLI, GUI, or validation behavior. Those fixes belong in the **upstream specy-road repository** or by **upgrading the installed package** (for example `pip install --upgrade specy-road`).

Framing matters: later phases merge into `CLAUDE.md` / `.cursor` for **this repo**—not to normalize patching a nested toolkit clone.

## Authoritative references

1. **Consumer AGENTS template:** Same content as `specy-road init project` → `AGENTS.md` (load order + `specy-road brief` example).
2. **Optional CLAUDE.md style** for consumer repos: the package ships `specy_road/templates/specyrd/CLAUDE.md.template`—use it as a **merge** pattern, not as a wholesale replace of this repo’s unique `CLAUDE.md` if one exists.
3. **Branching and registry:** `docs/git-workflow.md` (first-commit registration on `feature/rm-<codename>`, touch zones).
4. **Consumer boundary (copy-paste snippets):** Align with shipped stubs under `specy_road/templates/adoption/` in the package (`specy-road-consumer-claude-snippet.md`, `004-specy-road-consumer.mdc`) when merging the **specy-road (consumer)** section and optional Cursor rule—edit the consumer repo’s own files; do not treat those paths as the app’s source tree.

## Phase 1 — Discovery

Inventory:

- `.cursor/rules/**`, `.cursor/commands/**`
- `CLAUDE.md` at repo root (if any)
- `.claude/commands/**` or other IDE agent command folders
- Optional: GitHub Copilot or other `*instructions*` files
- Existing `AGENTS.md` (if any)

Note conflicts between existing rules and specy-road (prefer **tracked docs** over chat; **roadmap graph** in `roadmap/*.json` + manifest; **registry** separate from graph).

## Phase 2 — Primary deliverable: `AGENTS.md`

Create or update **`AGENTS.md`** at `[REPO_ROOT]` with this **required load order** (keep headings readable; wording can match the project tone):

1. `constitution/purpose.md` — why this exists  
2. `constitution/principles.md` — how we decide  
3. `constraints/README.md` — enforced rules  
4. **Merged roadmap:** `roadmap/manifest.json` + JSON chunk files listed in `includes` — your task’s node, parents, and `dependencies`  
5. `planning/<id>_<slug>_<node_key>.md` feature sheets for nodes with `planning_dir` (read ancestor sheets for context)  
6. `shared/README.md`, then **only** contract files cited for the task  

Include a **focused brief** example:

```bash
specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md
```

Use the real repo’s node IDs when you know them.

## Phase 3 — Merge strategy for existing rules

- **Preserve** project-specific instructions that do not contradict specy-road.
- **Add** a dedicated subsection for specy-road **invariants**, for example:
  - Docs win over chat when instructions conflict.
  - Smallest change that satisfies the task; no drive-by refactors.
  - Roadmap-linked work: follow `docs/git-workflow.md` and `roadmap/registry.yaml` (register on first commit of `feature/rm-<codename>`; remove registry entry before merge).

### specy-road consumer invariants (merge into `AGENTS.md` and/or optional Cursor rule)

Copy or adapt the following into **`AGENTS.md`** (and optionally into `.cursor/rules/`—see Phase 4b):

- **Consumer boundary:** Do not patch **`specy-road/`** in this repo to fix toolkit bugs. Instead produce an **upstream handoff**: repro steps, installed `specy-road` version (`pip show specy-road` or equivalent), relevant logs, suspected upstream area, and proposed upstream change or issue text.
- **Integration fixes** belong in **this** repository only: wrapper scripts, environment variables, and corrections under **`roadmap/`**, **`planning/`**, and **`roadmap/registry.yaml`** per `docs/git-workflow.md`.

Do **not** invent a parallel roadmap format (e.g. YAML merge file) in agent rules—the graph is JSON chunks + manifest.

## Phase 4 — `CLAUDE.md` (if present)

If `CLAUDE.md` exists, **merge** specy-road guidance:

- Roadmap model: merged graph = `manifest.json` + chunks; `git-workflow.yaml` = CLI/PM git defaults; `registry.yaml` = claims overlay, not a graph chunk.
- Commands: `specy-road validate`, `specy-road export --check`, `specy-road file-limits`, `specy-road brief <NODE_ID> -o work/brief-...`.
- Pointer to `AGENTS.md` as the canonical load order.

**Required mini-section — `specy-road (consumer)`:** Add a short section (merge, don’t replace the rest of the file) so agents don’t confuse this app repo with a nested toolkit tree. Use the package stub as a starting point (`specy_road/templates/adoption/specy-road-consumer-claude-snippet.md`) or this template:

```markdown
## specy-road (consumer)

**Relationship:** This repository is the application. An optional root-level `specy-road/` directory is often a local clone of the upstream toolkit for reference—not the place to patch CLI, GUI, or validator behavior.

**Troubleshooting:** Separate **integration** issues (this repo’s `roadmap/`, `planning/`, env vars, wrappers) from suspected **toolkit** bugs. For toolkit bugs, produce an **upstream handoff** (repro, package version, logs)—do not edit `specy-road/**` here to “fix” the kit.

**Pointers:** CLI load order and invariants → `AGENTS.md`. GUI, repo root, and `SPECY_ROAD_REPO_ROOT` → toolkit `docs/pm-workflow.md` and package `README.md`, or optional project-specific notes (e.g. `docs/commands.md` if your team adds that file).
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

These install **stub** markdown commands that delegate to **`specy-road`** CLI—they do not redefine validation logic. See project `README.md` for `specyrd` options (`--dry-run`, `--force`, `--role`, generic `--ai-commands-dir`).

If stubs already exist under `.cursor/commands/` or `.claude/commands/`, do not duplicate; ensure they still point at the same CLI workflows.

### Optional indexing (`.cursorignore`)

If a **`specy-road/`** clone exists at the repo root, consider adding **`specy-road/`** to **`.cursorignore`**: less automatic indexing of toolkit sources in the IDE context; **explicitly opened files** still work.

## Phase 6 — Verification

- There is no validator for `AGENTS.md`; do a consistency pass against `constitution/`, `constraints/README.md`, and `roadmap/` if present.
- If `roadmap/manifest.json` exists, run:

```bash
specy-road validate
specy-road export --check
```

- When validation or export fails, **first distinguish**:
  - **Bad consumer data** — fix under `roadmap/` (manifest, JSON chunks), `roadmap/registry.yaml`, `planning/`, and related project docs; or
  - **Suspected toolkit behavior** — installed `specy-road` package or a **nested `specy-road/` clone** is the wrong place to “fix” product behavior for the upstream kit. **Stop** and document an **upstream handoff** instead of editing `specy-road/**` or vendored toolkit files.
- Then fix any issues caused by **conflicting instructions** in the files you were asked to edit (consumer repo only).
