# Architecture (specy-road)

## Scope and non-goals

This repository provides **roadmap-first coordination** (YAML graph, validation, briefs, registry) and separates **constitution / principles / constraints / shared contracts**. It does **not** mandate a particular coding agent, IDE, or in-session implementation workflow—see [`philosophy-and-scope.md`](philosophy-and-scope.md).

End-to-end flow for this repository:

```mermaid
flowchart TD
  subgraph author [Authoring]
    Y[roadmap/roadmap.yaml]
    V[vision.md]
    Y --> E[scripts/export_roadmap_md.py]
    E --> I[roadmap.md index]
    E --> P[roadmap/phases/*.md]
  end
  subgraph validate [Validation]
    Y --> VR[scripts/validate_roadmap.py]
    R[roadmap/registry.yaml] --> VR
    FL[constraints/file-limits.yaml] --> VF[scripts/validate_file_limits.py]
  end
  subgraph agent [Agent slice]
    VR --> OK[OK or exit 1]
    GB[scripts/generate_brief.py NODE_ID]
    Y --> GB
    GB --> B[work/brief-*.md]
  end
```

| Layer | Role |
|-------|------|
| `constitution/` | Purpose and principles (human norms, not machine-enforced) |
| `constraints/` | Machine-readable limits; `file-limits.yaml` enforced by `validate_file_limits.py` |
| `roadmap/` | Canonical `roadmap.yaml` + `registry.yaml` |
| `schemas/` | JSON Schema for roadmap and registry |
| `shared/` | Contracts cited from tasks |
| `scripts/` | Validators, brief helper, markdown export |
| `specy_road/` | Package + `specy-road` CLI entrypoint |

**Source of truth:** [`roadmap/roadmap.yaml`](../roadmap/roadmap.yaml). Markdown views are generated; see [`roadmap-authoring.md`](roadmap-authoring.md).
