# Roadmap

- **`roadmap.yaml`** — Canonical node graph (immutable IDs `M`, `M1.2`, `M1.2.3`, …).
- **`registry.yaml`** — Active codename / branch / touch-zone claims for multi-agent coordination.

Validate with:

```bash
python scripts/validate_roadmap.py
```

Optional: maintain a human-edited `vision.md` / `roadmap.md` index at repo root and generate YAML, or treat YAML as source of truth and generate markdown (future work).
