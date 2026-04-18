# Constraints

Operational rules that are **enforced** (or enforceable by CI), not aspirational prose.

## Checkable rules

| Rule | Where | Check |
|------|--------|--------|
| Max source file length | [`file-limits.yaml`](file-limits.yaml) | `specy-road file-limits` (CI) |
| Roadmap graph validity + chunk line policy (`manifest.json` + JSON chunks; oversized multi-node chunks fail unless split) | `specy-road validate` | CI + local |

Add machine-readable rules here as the project grows; keep **purpose** and **principles** free of duplicate enforcement text.
