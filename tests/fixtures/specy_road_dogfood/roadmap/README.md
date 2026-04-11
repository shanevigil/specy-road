# Roadmap

- **`manifest.json`** — Entry point: `version` and ordered `includes` (chunk paths relative to `roadmap/`). See [`docs/roadmap-authoring.md`](../../../../docs/roadmap-authoring.md).
- **Chunk files** — JSON under e.g. `phases/M0.json`, usually `{"nodes": [...] }`. **Phase and milestone** nodes must set **`planning_dir`**; feature narrative (overview, plan, tasks) lives in [`../planning/`](../planning/README.md) Markdown. Short notes may still use the `notes` field on a node.
- **`registry.yaml`** — Active codename / branch / touch-zone claims for multi-agent coordination.

Validate with:

```bash
specy-road validate
```

Regenerate the root index after edits:

```bash
specy-road export
```
