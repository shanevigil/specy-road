# Roadmap authoring: YAML and markdown views

## Source of truth

**Canonical:** [`roadmap/roadmap.yaml`](../roadmap/roadmap.yaml). All node IDs are **immutable**; gaps in numbering are allowed; **never renumber** existing IDs.

**Generated (do not edit by hand):**

- [`roadmap.md`](../roadmap.md) — index table with **Gate** (execution milestone or sub-task).
- [`roadmap/phases/`](../roadmap/phases/) — one markdown file per top-level **phase** (`type: phase`, `parent_id: null`), listing that phase’s subtree.

Regenerate after editing the YAML:

```bash
python scripts/export_roadmap_md.py
```

Check that committed markdown matches YAML (e.g. in CI):

```bash
python scripts/export_roadmap_md.py --check
```

## Markdown → YAML

There is **no** automatic importer. Edits to the graph happen in **`roadmap.yaml`**. Markdown exists for readability and review (dual YAML/markdown view).

## Registry and brief

Active work registration stays in [`roadmap/registry.yaml`](../roadmap/registry.yaml). Bounded context for a node:

```bash
python scripts/generate_brief.py <NODE_ID> -o work/brief-<NODE_ID>.md
```
