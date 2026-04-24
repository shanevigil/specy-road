# Roadmap

This directory is the dogfood **test-fixture roadmap** for the toolkit repository. It is sample data for validation and CLI/GUI tests, not the canonical product roadmap for `specy-road`.

- **`manifest.json`** — Entry point: `version` and ordered `includes` (chunk paths relative to `roadmap/`). See [`docs/roadmap-authoring.md`](../../../../docs/roadmap-authoring.md).
- **Chunk files** — JSON under e.g. `phases/M0.json`, usually `{"nodes": [...] }`. Nodes with **`planning_dir`** point at a single feature sheet in [`../planning/`](../planning/README.md). Short notes may still use the `notes` field on a node.
- **`registry.yaml`** — Active codename / branch / touch-zone claims for multi-agent coordination.

Validate with:

```bash
specy-road validate
```

Regenerate the root index after edits:

```bash
specy-road export
```
