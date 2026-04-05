# Optional structured planning (`specify/<node-id>/`)

Use **lightweight** planning by default (roadmap node + contracts + session notes in [`work/`](../work/)).

For cross-cutting or high-risk work, copy templates from [`templates/specify-node/`](../templates/specify-node/) into:

```text
specify/<node-id>/
  spec.md
  plan.md
  tasks.md
```

Example: `specify/M1.1/` for milestone `M1.1`. This is **not** required by CI; it complements the roadmap, which remains canonical.
