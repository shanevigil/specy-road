## Intent

Field feedback on the 0.3.1 release candidates that does not block 0.3.1, handled after it ships (maintainer decision 2026-11-06). Findings are written as specy-road behaviour only. Leaves are added here during triage.

## Approach

Constraints, major steps, and how you will verify done.

## Tasks / checklist

Write each acceptance criterion on the node to the acceptance criteria checklist (see `planning/README.md`): state what is out of scope, bound concurrency and input classes, and name the observable check.

- [ ] …

## References

- Roadmap chunk for `M23`
- Add one line per contract this node conforms to, naming its path under
  `shared/`. `specy-road brief` inlines exactly the ones named here and lists
  the rest as paths, so a bare `shared/` cites nothing. Find one with
  `specy-road search "<query>" --kind shared`. Do not leave an example path in
  this section — anything matching a real file under `shared/` counts as a
  citation, including inside a comment or a code fence.
