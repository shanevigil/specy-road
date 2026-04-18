# Structured planning (`planning/*.md`)

**Vision, phase, milestone, and task** roadmap nodes **must** set **`planning_dir`** to a repo-relative path to **one Markdown file** under `planning/`, for example `planning/M1.1_my-milestone_a1b2c3d4-e5f6-4789-a012-3456789abcde.md`. That file is the **feature sheet** for the node, alongside the canonical graph in `roadmap/` JSON.

Use `specy-road scaffold-planning <NODE_ID>` (templates ship inside the `specy-road` package) or copy from a project initialized with `specy-road init project`.

## Filename

`planning/<display_id>_<codename_slug>_<node_key>.md`

- **`node_key`** — stable UUID from the roadmap node (lowercase in the filename).
- **`codename_slug`** — kebab-case from `codename`, or `unnamed` if absent.

Validation (`specy-road validate`) checks the file exists and the name matches the node (display id, codename slug, and `node_key`). The Markdown body is not required to repeat those identifiers; feature sheets typically start with `## Intent`. Orphan `planning/*.md` files not referenced by any node fail validation.

## Relationship to the roadmap graph

- **`roadmap/`** — Canonical structure: IDs, status, dependencies, codenames, touch zones, and `planning_dir` pointer.
- **`planning/`** — Human-readable **feature sheets**; dev workflow should also read **ancestor** sheets (phase/milestone) for context together with cited `shared/` contracts.

CLI: `specy-road scaffold-planning <NODE_ID>` creates the file, templates, and sets `planning_dir`.
