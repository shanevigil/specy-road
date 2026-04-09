# Roadmap

- **`manifest.json`** — Entry point: `version` and ordered `includes` (chunk paths relative to `roadmap/`). See [`../docs/roadmap-authoring.md`](../docs/roadmap-authoring.md).
- **Chunk files** — JSON under e.g. `phases/M0.json`, usually `{"nodes": [...] }`. Long narrative can live in each node’s `notes` (markdown string) and/or optional `planning/<node-id>/` markdown.
- **`registry.yaml`** — Active codename / branch / touch-zone claims for multi-agent coordination.

Validate with:

```bash
python scripts/validate_roadmap.py
```

Regenerate the root index after edits:

```bash
python scripts/export_roadmap_md.py
```
