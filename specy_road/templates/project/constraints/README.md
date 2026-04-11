# Constraints

Operational rules that are **enforced** (or enforceable by CI), not aspirational prose.

| Rule | Where | Check |
|------|--------|--------|
| Max file / function length | [`file-limits.yaml`](file-limits.yaml) | `specy-road file-limits` |
| Roadmap graph | `roadmap/` JSON + `registry.yaml` | `specy-road validate` |

Tune `file-limits.yaml` globs for your repository layout (for example `src/`, `packages/`, `app/`).
