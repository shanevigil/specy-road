# Roadmap

- **`roadmap.yaml`** — Entry point: either a **manifest** (`includes:` listing chunk files) or a **legacy** single-file graph (`nodes:` only). See [`../docs/roadmap-authoring.md`](../docs/roadmap-authoring.md).
- **Chunk files** — e.g. `phases/M0.yaml`, `phases/M1.yaml`: each contributes a `nodes` list; merged in include order.
- **`registry.yaml`** — Active codename / branch / touch-zone claims for multi-agent coordination.

Validate with:

```bash
python scripts/validate_roadmap.py
```

Optional: maintain a human-edited `vision.md` / `roadmap.md` index at repo root and generate YAML, or treat YAML as source of truth and generate markdown (current behavior).
