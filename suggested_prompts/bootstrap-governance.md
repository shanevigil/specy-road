# Prompt: Bootstrap specy-road governance (vision, constitution, constraints, shared)

Copy everything below the line into your agentic coding tool. Replace `[REPO_ROOT]` with your repository root if you use absolute paths.

---

You are helping adopt **specy-road** in an **existing** project. The project already has code and documentation; we need **governance artifacts** that match specy-road’s layout and semantics—not a generic “best practices” doc set.

## Authoritative references (read if available)

1. **Installed scaffold:** From `[REPO_ROOT]`, run `specy-road init project --dry-run` and treat every listed path as the canonical file set. To inspect templates without installing, the same tree ships in the `specy-road` package as `templates/project/` (e.g. under `site-packages/specy_road/templates/project/`).
2. **Maintainer documentation** (for exact rules): `docs/roadmap-authoring.md`, `docs/git-workflow.md`, **`docs/install-and-usage.md`** (install from source, `init project`), and **`docs/contributor-guide.md`** (`specyrd`, pre-commit); the project `README` summarizes the kit.

## Concepts you must not confuse

- **`vision.md` (repo root)** — One Markdown file for the product/program vision. Human narrative; not validated as JSON.
- **Roadmap node `type: "vision"`** — An optional **node in the roadmap graph** (JSON under `roadmap/`). Different from the root `vision.md` file.
- **Merged graph** — `roadmap/manifest.json` plus ordered **JSON chunk files** listed in `includes`. There is **no** single merged YAML file for the roadmap graph.
- **`roadmap/registry.yaml`** — Active work registration (codename, branch, touch zones). **Not** a chunk of the merged graph.

## Phase 1 — Discovery

Scan the repository and infer content:

- Root `README.md`, `docs/`, ADRs, contributing guides, architecture overviews.
- Top-level directory layout (where source, tests, and packages live) for tuning file-limit globs.

Classify statements as:

- **Purpose / principles** (judgment, strategy) → `constitution/`
- **Enforceable or CI-checkable rules** → `constraints/` and `constraints/file-limits.yaml`
- **Specs, APIs, policies to cite from work** → `shared/` (and list them in `shared/README.md`)

## Phase 2 — Deliverables (exact paths)

Create or **replace placeholder content** at these paths (match the structure from `specy-road init project`):

| Path | Purpose |
|------|---------|
| `vision.md` | Short paragraph on desired future state; link to deeper strategy docs if they exist. |
| `constitution/purpose.md` | Why the effort exists and what success looks like (plain language). Keep enforceable limits out of here—they belong under `constraints/`. |
| `constitution/principles.md` | How the team decides (values, roadmap-first, contracts over tribal knowledge, etc.). |
| `constraints/README.md` | Table of **enforced** rules: what is checked, **where** it lives, **which command** validates it (e.g. `specy-road validate`, `specy-road file-limits`). |
| `constraints/file-limits.yaml` | Tune `applies_to_globs` to this repo’s real paths (examples: `src/`, `packages/`, `app/`). `max_lines_per_file` applies to every matched path. `max_lines_per_function` and `hard_alerts.max_lines_per_function` are enforced for **Python (`.py`)** only by `specy-road file-limits`; optional `exclude_path_globs` (merged with `exclude_globs`), `override_limits`, and `hard_alerts` shape rollout policy. Roadmap caps: `roadmap_manifest_max_lines`, `roadmap_json_chunk_max_lines` (also read by `specy-road validate`). |
| `shared/README.md` | Explain that contracts live here; roadmap nodes should **cite** paths under `shared/` in `agentic_checklist.contract_citation` when applicable—not duplicate specs in chat. |

### If the scaffold is missing entirely

Either:

- Run **`specy-road init project`** at `[REPO_ROOT]`** once** (use `--dry-run` first; use `--force` only if intentionally replacing an existing scaffold), **then** edit the governance files above; or  
- Copy the full `templates/project` tree so you include: `schemas/*.json`, `work/README.md`, `AGENTS.md`, `docs/supply-chain-security.md`, and a **minimal valid** `roadmap/` (`manifest.json`, `git-workflow.yaml`, `registry.yaml`, at least one JSON chunk under e.g. `roadmap/phases/`) so `specy-road validate` passes.

If the user will run a **separate** prompt to build the full roadmap from existing notes, **do not** deeply author roadmap nodes here—keep a **minimal** graph that validates, or rely on `init project` and governance-only edits.

## Phase 3 — Verification

From `[REPO_ROOT]`:

```bash
specy-road validate
specy-road export --check
specy-road file-limits
```

Fix any failures. Do not hand-author `roadmap.md` as source of truth; it is produced by `specy-road export`.

## Non-goals

- Rewriting unrelated application code.
- Replacing the entire roadmap narrative if a dedicated roadmap migration prompt will follow—keep roadmap **minimal** or defer to `init project` + governance edits only.
