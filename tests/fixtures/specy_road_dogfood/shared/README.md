# Shared contracts

Place **stable, referenceable** documents here: API tables, data model outlines, RBAC matrix, policy summaries.

Roadmap items should **cite** these files (section or entity), not duplicate stack choices. **Feature sheets** belong in [`planning/`](../planning/README.md); keep contracts here focused and referenceable. Prefer one topic per file and load selectively.

## Contracts

- **[API contract (outline)](api-contract.md)** — JSON request/response envelope, error model, and error-code vocabulary. Cite section headings (e.g. “Error model”, a table row) from roadmap tasks and agent briefs.
- **ADRs** — Stack and integration decisions live in Architecture Decision Records under `docs/adr/` when that folder exists; link the relevant ADR from this README next to the contract it constrains.

## Spec crosswalk (examples)

| Kind | Example filename |
|------|------------------|
| Feature spec | `feature-<area>.md` |
| Data model | `data-model.md` |
| API contract | `api-contract.md` |
| Prompt / AI | `prompt-spec.md` |
| Policy | `redaction-policy.md` |
| RBAC | `rbac-matrix.md` |

Add files as the program grows; link from roadmap task text and from agent briefs.
