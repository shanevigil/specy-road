# Roadmap authoring: YAML and markdown views

## Source of truth

**Canonical:** the roadmap graph under [`roadmap/`](../roadmap/). The entry file is [`roadmap/roadmap.yaml`](../roadmap/roadmap.yaml): either the **full graph** (legacy) or a **manifest** that lists chunk files to merge in order.

All node IDs are **immutable**; gaps in numbering are allowed; **never renumber** existing IDs.

### Hierarchical YAML (preferred)

Keep the graph **logically split** across multiple files under `roadmap/` so each file stays reviewable:

- **`roadmap.yaml`** — `version` and `includes` (paths relative to `roadmap/`), **without** a top-level `nodes` key.
- **Chunk files** (for example `phases/M0.yaml`) — each file is a mapping with a single `nodes` list for that slice of the tree (typically a phase subtree or another coherent grouping).

Order matters: nodes are concatenated from chunks in **include order**. Duplicate IDs across files are rejected by validation when IDs collide (validator checks uniqueness on the merged list).

### Legacy single-file graph

If `roadmap.yaml` has **no** `includes` key, it may contain top-level `nodes` only. Do not use `includes` and `nodes` together.

### Line-count policy (400)

No YAML file under `roadmap/` (except [`registry.yaml`](../roadmap/registry.yaml)) may exceed **400 lines**, **unless** that file’s `nodes` array contains **exactly one** node—the smallest work-unit grain (e.g. one task with a very large `agentic_checklist`). The manifest should stay compact; move long prose to `docs/` or trim comments if needed.

Enforced by `scripts/validate_roadmap.py` (via [`scripts/roadmap_load.py`](../scripts/roadmap_load.py)). Keep the manifest short; if comments push it over 400 lines, move prose to `docs/` or trim.

**Generated (do not edit by hand):**

- [`roadmap.md`](../roadmap.md) — index table with **Gate** (execution milestone or sub-task).
- [`roadmap/phases/`](../roadmap/phases/) — one markdown file per top-level **phase** (`type: phase`, `parent_id: null`), listing that phase’s subtree.

Regenerate after editing the YAML:

```bash
python scripts/export_roadmap_md.py
```

Check that committed markdown matches the graph (e.g. in CI):

```bash
python scripts/export_roadmap_md.py --check
```

## Markdown → YAML

There is **no** automatic importer. Edits to the graph happen in YAML under `roadmap/`. Markdown exists for readability and review (dual YAML/markdown view).

## Registry and brief

Active work registration stays in [`roadmap/registry.yaml`](../roadmap/registry.yaml). Bounded context for a node:

```bash
python scripts/generate_brief.py <NODE_ID> -o work/brief-<NODE_ID>.md
```
