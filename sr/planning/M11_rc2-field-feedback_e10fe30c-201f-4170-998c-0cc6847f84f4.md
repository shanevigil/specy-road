## Intent

Fixes for gaps found when an adopter ran 0.3.1rc2 with an overnight coordinator, worktree and clone lanes, and two reviewer families: path resolution in worktrees, worker lifecycle (resume, limits, reconcile, clean-tree checks), pickup's stale-claim advice, and review-loop cost and tooling. Each leaf states the behaviour as specy-road's, with no project details.

## Approach

Take the leaves in any order that keeps touch zones apart; M11.8 is Mixed because its policy defaults need the maintainer.

## Tasks / checklist

- [ ] …

## References

- Roadmap chunk for `M11`
- Add one line per contract this node conforms to, naming its path under
  `shared/`. `specy-road brief` inlines exactly the ones named here and lists
  the rest as paths, so a bare `shared/` cites nothing. Find one with
  `specy-road search "<query>" --kind shared`. Do not leave an example path in
  this section — anything matching a real file under `shared/` counts as a
  citation, including inside a comment or a code fence.
