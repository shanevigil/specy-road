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

## Decisions and notes
- 2026-11-05 (D6): M5–M11 were recorded Complete without policy.milestone_full_review. The maintainer waived it: the themes were fulfilled long ago, and sr/work/milestone-audit-2026-11-05.md confirms all seven, with the M5, M8 and M11 gaps filed as M18.2–M18.5 and M19.3–M19.4.
- D6: waive: M5–M11 recorded Complete without policy.milestone_full_review; themes fulfilled per sr/work/milestone-audit-2026-11-05.md, gaps filed as M18.2–M18.5 and M19.3–M19.4 (maintainer, 2026-11-05)
