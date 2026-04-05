# Constraints

Operational rules that are **enforced** (or enforceable by CI), not aspirational prose.

## Checkable rules

| Rule | Where | Check |
|------|--------|--------|
| Max source file length | [`file-limits.yaml`](file-limits.yaml) | `python scripts/validate_file_limits.py` (CI) |
| Roadmap graph validity + YAML chunk line policy (400 lines; exception: single-node file) | `scripts/validate_roadmap.py` | CI + local |

Add machine-readable rules here as the project grows; keep **purpose** and **principles** free of duplicate enforcement text.
