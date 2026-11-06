## Intent

Holds every rc4 fix filed after the maintainer's 2026-11-05 rule that new work never goes into an old milestone. It closes when rc4 ships, like M15. Listed right after M15 (sibling order) even though its number is higher: ids are identity, not sequence.

## Contents

- Roadmap tooling (moved from M16's fix intake): chosen-id moves and GUI subtree-only renumbering, CLI indent/outdent/group, prose id rewrite, remove-node, batch apply, inherited-dependency cycle checks.
- Steering-file protection (rc4 fix, maintainer 2026-11-05).
- After they land: M21.13 (move-node subtree-only), M21.14 (finish inherited roadmap conflicts) and M21.15 (Cursor workers sandboxed) are re-homed here.

## References

- M16.8.9 (0.3.1 tag gate) depends on these fixes.
