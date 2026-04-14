# Constraints

Operational rules that are **enforced** (or enforceable by CI), not aspirational prose.

| Rule | Where | Check |
|------|--------|--------|
| Max file / function length | [`file-limits.yaml`](file-limits.yaml) | `specy-road file-limits` |
| Roadmap graph | `roadmap/` JSON + `registry.yaml` | `specy-road validate` |

**Dependency and supply-chain policy** (Python/npm, advisory scans, review discipline) lives in [`docs/supply-chain-security.md`](../docs/supply-chain-security.md). Enforce it with your own CI jobs and lockfiles.

Tune `file-limits.yaml` globs for your repository layout (for example `src/`, `packages/`, `app/`).
