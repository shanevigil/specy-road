# Prompt: Align AGENTS.md and agent tooling with specy-road

Copy everything below the line into your agentic coding tool. Replace `[REPO_ROOT]` with your repository root if you use absolute paths.

---

You are helping adopt **specy-road** coding paradigms in an **existing** project. The repo may already have `.cursor/`, `CLAUDE.md`, `.claude/`, or other agent configuration. Your job is to produce a clear **AGENTS.md** entrypoint and **merge** specy-road expectations into existing files without discarding valuable team rules.

## Authoritative references

1. **Consumer AGENTS template:** Same content as `specy-road init project` → `AGENTS.md` (load order + `specy-road brief` example).
2. **Optional CLUDE.md style** for consumer repos: the package ships `specy_road/templates/specyrd/CLAUDE.md.template`—use it as a **merge** pattern, not as a wholesale replace of this repo’s unique `CLAUDE.md` if one exists.
3. **Branching and registry:** `docs/git-workflow.md` (first-commit registration on `feature/rm-<codename>`, touch zones).

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
5. `planning/<node-id>/` for **phase** and **milestone** nodes (`overview.md`, `plan.md`, optional tasks)  
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

Do **not** invent a parallel roadmap format (e.g. YAML merge file) in agent rules—the graph is JSON chunks + manifest.

## Phase 4 — `CLAUDE.md` (if present)

If `CLAUDE.md` exists, **merge** specy-road guidance:

- Roadmap model: merged graph = `manifest.json` + chunks; `registry.yaml` = claims overlay, not a graph chunk.
- Commands: `specy-road validate`, `specy-road export --check`, `specy-road file-limits`, `specy-road brief <NODE_ID> -o work/brief-...`.
- Pointer to `AGENTS.md` as the canonical load order.

Do **not** delete existing sections (team stack, build commands, etc.) unless the user asked for a full replacement.

## Phase 5 — Optional: `specyrd` slash-command stubs

Mention that the repo can run (from `[REPO_ROOT]`):

```bash
specyrd init --here --ai cursor
# or
specyrd init --here --ai claude-code
```

These install **stub** markdown commands that delegate to **`specy-road`** CLI—they do not redefine validation logic. See project `README.md` for `specyrd` options (`--dry-run`, `--force`, `--role`, generic `--ai-commands-dir`).

If stubs already exist under `.cursor/commands/` or `.claude/commands/`, do not duplicate; ensure they still point at the same CLI workflows.

## Phase 6 — Verification

- There is no validator for `AGENTS.md`; do a consistency pass against `constitution/`, `constraints/README.md`, and `roadmap/` if present.
- If `roadmap/manifest.json` exists, run:

```bash
specy-road validate
specy-road export --check
```

Fix any issues caused by conflicting instructions in edited files.
