# Prompt: Bootstrap specy-road governance (vision, constitution, constraints, shared)

Copy everything below the line into your agentic coding tool. Replace `[REPO_ROOT]` with your git root if you use absolute paths.

---

You are helping adopt **specy-road** in an **existing** project. The project already has code and documentation; we need **governance artifacts** that match specy-road’s layout and semantics—not a generic “best practices” doc set.

Adoption order, stated the same way in every suggested prompt: `specy-road init project`, then this prompt, then the roadmap (`bootstrap-roadmap.md`), then agent entrypoints (`bootstrap-agents-md.md`, a merge — init already wrote `AGENTS.md`), then brainstorm (`brainstorm-roadmap.md`) any time after the roadmap exists.

Paths below (`vision.md`, `constitution/`, `constraints/`, `shared/`, `roadmap/`) are relative to the **project root**. In the embedded layout that root is the git root. In the nested layout (the tree under `sr/`) it is the directory `.specyrd/manifest.json` records as `project_root`. Run every `specy-road` command from the **git root**; the CLI resolves the project root. Do not create a second `constitution/` or `roadmap/` at the git root of a nested repo. `specy-road init project sr` scaffolds the nested layout.

## Authoritative references

1. **Installed scaffold:** From the git root, run `specy-road init project --dry-run` and treat every listed path as the canonical file set. The same tree ships in the installed package as `specy_road/templates/project/` (under `site-packages/`).
2. **Toolkit docs are not in an adopter repo** unless this prompt says `init project` ships them. `specy-road init project` ships only `docs/supply-chain-security.md` and `docs/model-profiles-research-notes.md`. This prompt's `docs/roadmap-authoring.md`, `docs/git-workflow.md`, `docs/install-and-usage.md` and `docs/contributor-guide.md` are in the toolkit repository, https://github.com/shanevigil/specy-road/tree/main/docs . `specy-road upgrade` copies a `docs/` file only when `.specyrd/AGENTS.md`'s load order names it and the repo lacks it. The toolkit repository's `README.md` summarizes the kit.

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
| `constraints/file-limits.yaml` | Tune `applies_to_globs` to this repo’s real paths (examples: `src/`, `packages/`, `app/`). `max_lines_per_file` applies to every matched path. `max_lines_per_function` and `hard_alerts.max_lines_per_function` are enforced by `specy-road file-limits` for **Python (`.py`)** and **JavaScript/TypeScript (`.js`, `.jsx`, `.mjs`, `.ts`, `.tsx`)** functions; other file types get only the per-file cap; optional `exclude_path_globs` (merged with `exclude_globs`), `override_limits`, and `hard_alerts` shape rollout policy. Git-ignored files and the toolkit's own `work/` session artifacts are skipped before your globs apply, so do not re-declare them. Roadmap caps: `roadmap_manifest_max_lines`, `roadmap_json_chunk_max_lines` (also read by `specy-road validate`). |
| `shared/README.md` | Explain that contracts live here, and keep it a real index — `specy-road brief` always inlines this file, then only the contracts a node cites by filename in its planning sheet's `## References`. Everything else under `shared/` is listed as a path, so nodes should **cite** rather than duplicate specs in chat. |
| `roadmap/orchestration.yaml` | Who may execute and review. `init project` writes the default (one human reviewer). Add a roster entry only for a model the team will use. Keys: the scaffolded `schemas/orchestration.schema.json`. |
| `model-profiles/` | One profile per roster model. `init project` ships the directory. `specy-road upgrade --only profiles` adds files that are missing and does not overwrite. |
| `constraints/review-lessons.md` | Defect classes reviewers check. `init project` writes the file. The same lessons are listed by `specy-road decisions list --kind lesson`. |

`init project` also writes `research/README.md`, `docs/supply-chain-security.md`, `docs/model-profiles-research-notes.md`, `work/*.template.md` and `.specyrd/`. Leave those in place unless this project's own content replaces a placeholder. Do not hand-edit `.specyrd/AGENTS.md`.

### If the scaffold is missing entirely

Run **`specy-road init project`** once from the git root (use `specy-road init project --dry-run` first; use `--force` only when intentionally replacing an existing scaffold), **then** edit the governance files above. A dry-run lists paths and not contents, so it is the checklist, not a source to copy. Do not hand-write `AGENTS.md`'s managed block or `.specyrd/AGENTS.md`: `specy-road init project` and `specy-road upgrade` write both.

If the user will run a **separate** prompt to build the full roadmap from existing notes, **do not** deeply author roadmap nodes here—keep a **minimal** graph that validates, or rely on `init project` and governance-only edits.

## Phase 3 — Verification

From `[REPO_ROOT]`:

```bash
specy-road validate
specy-road export --check
specy-road digest --check
specy-road file-limits
```

Resolve every error and every warning before finishing, not errors alone. A run that exits 0 can still print touch-zone overlap warnings and milestone-review notices; fix those too. Do not hand-author `roadmap.md` as source of truth; it is produced by `specy-road export`.

## Non-goals

- Rewriting unrelated application code.
- Replacing the entire roadmap narrative if a dedicated roadmap migration prompt will follow—keep roadmap **minimal** or defer to `init project` + governance edits only.
