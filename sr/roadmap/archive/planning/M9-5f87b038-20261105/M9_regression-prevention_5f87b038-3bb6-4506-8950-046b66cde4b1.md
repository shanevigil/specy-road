## Intent

Stop regressions reaching the integration branch.

## Approach

The leaves added a land check on the merge commit, a fixture-pollution guard, test-integrity reports with a gate and waivers, suppression and ratchet findings, verified pre-existing failures, tests-at-risk, red-green evidence, `blocked_on` for executors, and nested-layout tests with zone-path fixes.

## Tasks / checklist

- [ ] …

## Decisions and notes

Settled (recorded 2026-11-15 by M16.6.1; the design note `docs/design-notes/regression-prevention.md` that held both as open was untracked by M22.55):

- **What "green" means:** settled. M9.1 landed (e19e4005) running a configured command on the merge commit, and M16.4.5 then replaced `baseline_cmd`, `land_check_cmd` and `verify_cmd` with one `checks:` block in `roadmap/git-workflow.yaml`. Green at a point is every `checks:` entry for that point (`when: baseline`, `land` or `prompt`) passing.
- **"M9.10 stays proposed":** settled. M9.10 (red-green evidence) was approved and landed (1b2a3d1f).

## References

- Roadmap chunk for `M9`
- Add one line per contract this node conforms to, naming its path under
  `shared/`. `specy-road brief` inlines exactly the ones named here and lists
  the rest as paths, so a bare `shared/` cites nothing. Find one with
  `specy-road search "<query>" --kind shared`. Do not leave an example path in
  this section — anything matching a real file under `shared/` counts as a
  citation, including inside a comment or a code fence.
