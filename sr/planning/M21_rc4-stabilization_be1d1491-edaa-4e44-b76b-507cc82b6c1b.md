## Intent

Holds every rc4 fix filed after the maintainer's 2026-11-05 rule that new work never goes into an old milestone. It closes when rc4 ships, like M15. Listed right after M15 (sibling order) even though its number is higher: ids are identity, not sequence.

## Contents

- Roadmap tooling (moved from M16's fix intake): chosen-id moves and GUI subtree-only renumbering, CLI indent/outdent/group, prose id rewrite, remove-node, batch apply, inherited-dependency cycle checks.
- Steering-file protection (rc4 fix, maintainer 2026-11-05).
- After they land: M21.13 (move-node subtree-only), M21.14 (finish inherited roadmap conflicts) and M21.15 (Cursor workers sandboxed) are re-homed here.
- rc4 pre-release check fixes (sr/work/release-reviews/rc4/SUMMARY.md FAILs F1 to F4 and the fix-rc4 warnings, plus the rc4 sandbox rehearsal): M21.16 upgrade scratch git and regeneration (F1), M21.17 writers refuse links out (F2, review W3), M21.18 deferral bound to its decision (F3, review W4), M21.19 apply dry-run rebases links (F4, roadmap W1), M21.20 GUI Publish regenerates and needs a remote (sandbox), M21.21 review delegate validation and model check (review W1, W2), M21.22 small code fixes, M21.23 doc corrections.

## Release map

| Release | What it contains |
| --- | --- |
| rc4 | M21 (rc4 stabilization) |
| rc5 | M16 (lean core) + M22 (rc5 fixes) |
| 0.3.1 | the M16.8.9 "ready to tag 0.3.1" gate + M17 (PM GUI orchestration view, built in parallel with M16) + the rc5 fixes; then the maintainer's tag (gate M16.8.10) |
| after 0.3.1 | M18, M19, M20 (each depends on gate M16.8.10, "0.3.1 tagged") |

Milestone numbers are not release order; dependencies are. (Maintainer ruling, 2026-11-05 evening.)

## References

- M16.8.9 (0.3.1 tag gate) depends on these fixes.
