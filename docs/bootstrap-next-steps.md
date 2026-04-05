# Bootstrap next steps (transient)

**Status:** Bootstrap **tooling** checklist below is complete. This file remains a **scratch pad** for handoff until you archive it under `docs/archive/` or delete it.

- **Tooling backlog** — Sections 1–6: finished for the current scope.
- **Roadmap-driven work** — Tracked in [`roadmap/roadmap.yaml`](../roadmap/roadmap.yaml); see “Roadmap-driven work (product graph)” below.

Scratch backlog for finishing **specy-road’s own tooling** lives in sections 1–6. Product contracts and milestones are **not** duplicated here except as a short pointer.

---

## Bootstrap (tooling) — complete

### 1. Dual authoring / YAML ↔ markdown

- [x] Root `vision.md` (or agreed name) and phase-oriented markdown exist where the design says they should.
- [x] `roadmap.md` index includes a **Gate** column (or documented equivalent).
- [x] Generation path between YAML and markdown is defined; **immutable IDs** are never silently renumbered; **source of truth** (YAML vs markdown) is documented.

### 2. Constraints enforcement (file limits)

- [x] Script reads [`constraints/file-limits.yaml`](../constraints/file-limits.yaml), applies `applies_to_globs`, reports file path + line count + limit on failure.
- [x] [`.github/workflows/validate.yml`](../.github/workflows/validate.yml) runs the script (same Python env as the roadmap validator).

### 3. Agentic task completeness

- [x] Agentic leaves are enforceable via **schema fields** and/or a **checklist linter** aligned with [`templates/roadmap/agentic-task-checklist.md`](../templates/roadmap/agentic-task-checklist.md) (five required elements).
- [x] Approach avoids brittle full-prose parsing unless explicitly chosen.

### 4. Automated tests

- [x] Tests cover [`scripts/validate_roadmap.py`](../scripts/validate_roadmap.py) (valid/invalid fixtures: ids, parents, deps, cycles, registry).
- [x] Tests cover [`scripts/generate_brief.py`](../scripts/generate_brief.py) (unknown id, known node output shape).
- [x] CI runs the test command after installing [`requirements.txt`](../requirements.txt).

### 5. Packaging

- [x] Optional `pyproject.toml` with metadata and dev dependencies.
- [x] Optional console entrypoint (e.g. `specy-road validate` / `specy-road brief`) wrapping existing scripts.
- [x] Optional pre-commit hook calling the roadmap validator.

### 6. Polish

- [x] Optional [`docs/architecture.md`](architecture.md) (layers, validate → brief → CI).
- [x] Optional snippet or template for `docs/roadmap-status.md` in **consuming** app repos (YAML/markdown status parity).

---

## Roadmap-driven work (product graph)

**Done (recent):**

- [x] **M0.1.1** — [`shared/api-contract.md`](../shared/api-contract.md) added (outline: resources, JSON envelope, error codes). [`shared/README.md`](../shared/README.md) **Contracts** section cites it.

**Next (suggested):**

- [ ] **M0.1** — ADR skeleton: add `docs/adr/README.md` plus a short template, and link from [`shared/README.md`](../shared/README.md) (milestone title: “Establish shared contracts and ADR skeleton”).
- [ ] **M0.1 / M0** — Update phase or milestone status when M0.1 is fully satisfied.
- [ ] **M1.1** — Reconcile roadmap text (“Roadmap validator in CI”) with the repo: CI already runs validation; either mark the node complete or narrow the title to match any remaining scope.

---

## Do not

- Edit the external Cursor plan `specy-road_architecture` unless a maintainer asks.
- Mix multiple slices in one PR when it can be avoided.

## Coordination

Follow [`docs/git-workflow.md`](git-workflow.md): branch `feature/rm-<codename>`, register in [`roadmap/registry.yaml`](../roadmap/registry.yaml) when work is roadmap-linked, run `python scripts/validate_roadmap.py` before push.
