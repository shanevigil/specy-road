# API contract (outline)

**Document version:** 0.1 (stub)  
**Scope:** Stack-agnostic JSON-over-HTTP conventions for any HTTP API this coordination kit integrates with or exposes. Concrete paths, auth, and OpenAPI definitions belong in product ADRs and feature specs when they exist.

## Purpose

- Give a single place for **envelope**, **error shape**, and **code vocabulary** so roadmap tasks and agent briefs can cite stable names.
- This file is an **outline**: resource rows may use `TBD` until implementation locks behavior.

## Resource list (logical)

| Resource / operation | Method (typical) | Role |
|----------------------|------------------|------|
| `RoadmapGraph` | `GET` | Read canonical roadmap nodes and edges. |
| `RoadmapValidation` | `POST` | Submit graph snapshot or path for validation (e.g. CI). |
| `Brief` | `GET` | Resolve a slice (node id) to a brief payload for agents. |
| `Registry` | `GET` / `PATCH` | In-progress claims (touch zones, branch) for coordination. |
| `Health` | `GET` | Liveness for gateways and hosted surfaces. |

Operations may be local CLI today and HTTP later; the **payload shapes** below stay stable.

## HTTP JSON envelope

### Request

Clients send JSON with `Content-Type: application/json` unless a sub-resource defines otherwise.

```json
{
  "meta": {
    "request_id": "uuid-or-opaque-string",
    "client": "optional-name-or-version"
  },
  "data": {}
}
```

- `meta` is optional for simple reads; servers should accept requests with only `data` or a bare body where documented.
- `data` holds domain input (filters, ids, patches).

### Success response

```json
{
  "meta": {
    "request_id": "same-as-request-when-present"
  },
  "data": {}
}
```

- `data` is the successful result (object, array, or null).

## Error model

Failures use HTTP **4xx/5xx** and a JSON body:

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Human-readable summary.",
    "details": null
  }
}
```

- `details` is optional; when present it is an object or array of structured hints (field paths, limits), not raw stack traces in production.

### Error codes (enum)

| Code | Typical HTTP | Meaning |
|------|--------------|---------|
| `VALIDATION_FAILED` | 400 | Input failed schema or business rules. |
| `UNAUTHORIZED` | 401 | Missing or invalid credentials. |
| `FORBIDDEN` | 403 | Authenticated but not allowed. |
| `NOT_FOUND` | 404 | Resource or node id does not exist. |
| `CONFLICT` | 409 | State conflict (e.g. duplicate id, registry collision). |
| `RATE_LIMITED` | 429 | Too many requests. |
| `INTERNAL_ERROR` | 500 | Unexpected server failure. |

## Constraints

- **No secrets** in repository artifacts: do not embed API keys, tokens, or connection strings in this contract or in example payloads checked into git.
- **PII:** Not applicable to this stub document; future fields that carry personal data must be named in data-model specs and handled per policy ADRs.
- **Versioning:** Bump the **document version** at the top when breaking JSON shapes or error codes; reference that version from ADRs.
