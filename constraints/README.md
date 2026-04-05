# Constraints

Operational rules that are **enforced** (or enforceable by CI), not aspirational prose.

## Checkable rules

| Rule | Where | Check |
|------|--------|--------|
| Max source file length | [`file-limits.yaml`](file-limits.yaml) | Manual / future linter |
| Roadmap graph validity | `scripts/validate_roadmap.py` | CI + local |

Add machine-readable rules here as the project grows; keep **purpose** and **principles** free of duplicate enforcement text.
