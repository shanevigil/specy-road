## Intent

Stop regressions reaching the integration branch.

## Approach

The leaves added a land check on the merge commit, a fixture-pollution guard, test-integrity reports with a gate and waivers, suppression and ratchet findings, verified pre-existing failures, tests-at-risk, red-green evidence, `blocked_on` for executors, and nested-layout tests with zone-path fixes.

## Tasks / checklist

- [ ] …

## References

- Roadmap chunk for `M9`
- Add one line per contract this node conforms to, naming its path under
  `shared/`. `specy-road brief` inlines exactly the ones named here and lists
  the rest as paths, so a bare `shared/` cites nothing. Find one with
  `specy-road search "<query>" --kind shared`. Do not leave an example path in
  this section — anything matching a real file under `shared/` counts as a
  citation, including inside a comment or a code fence.
