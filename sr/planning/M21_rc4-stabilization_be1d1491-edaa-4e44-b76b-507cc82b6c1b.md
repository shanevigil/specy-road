## Intent

Holds every rc4 fix filed after the maintainer's 2026-11-05 rule that new work never goes into an old milestone. It closes when rc4 ships, like M15. Listed right after M15 (sibling order) even though its number is higher: ids are identity, not sequence.

## Contents

- Roadmap tooling (moved from M16's fix intake): chosen-id moves and GUI subtree-only renumbering, CLI indent/outdent/group, prose id rewrite, remove-node, batch apply, inherited-dependency cycle checks.
- Steering-file protection (rc4 fix, maintainer 2026-11-05).
- After they land: M21.13 (move-node subtree-only), M21.14 (finish inherited roadmap conflicts) and M21.15 (Cursor workers sandboxed) are re-homed here.
- rc4 pre-release check fixes (sr/work/release-reviews/rc4/SUMMARY.md FAILs F1 to F4 and the fix-rc4 warnings, plus the rc4 sandbox rehearsal): M21.16 upgrade scratch git and regeneration (F1), M21.17 writers refuse links out (F2, review W3), M21.18 deferral bound to its decision (F3, review W4), M21.19 apply dry-run rebases links (F4, roadmap W1), M21.20 GUI Publish regenerates and needs a remote (sandbox), M21.21 review delegate validation and model check (review W1, W2), M21.22 small code fixes, M21.23 doc corrections.
- rc4 real-harness check fixes (pre-release evidence 2026-11-05, three apps plus the agentic runbook on Claude Code, Codex and Cursor): M21.24 Claude Code reviewer schema and failure reason (D1), M21.25 reviewer answer after narration (D2, Cursor), M21.26 gate excludes READY authors (D3, security), M21.27 filings take the review lock (D4), M21.28 finish validates before bookkeeping (D5), M21.29 terminate ends escaped descendants (D6). D7 to D14 are rc5 fixes (M22.12 to M22.15).
- rc4 context-regression fixes (§9 replay 2026-11-05, Cursor guidance regressions and two case-design problems): M21.30 review policy pinned at claim (CR1, security), M21.31 review record files only as the caller (CR1, security), M21.32 session end only your own (CR3, security), M21.33 brainstorm start first and alone (CR5), M21.34 CR2 case fits the todo app.
- rc4 re-test fixes (review delegate and §6 brainstorm re-test 2026-11-06): M21.35 a refused reviewer answer gets one repair turn with the refusal text, and the prompt ends with the notes rules (D15); M21.36 brainstorm verify normalizes real page text (D16). D15c, D16b, D17 and D18 are rc5 fixes (M22.16, M22.17).
- rc4 final review fixes (§3.2 2026-11-06, sr/work/release-reviews/rc4-final/): M21.37 one safe-write rule plus the setup and upgrade writers (prior-F2 class); M21.38 review writers and the review lock; M21.39 Publish, finish land and reviews copy, pickup hint; M21.40 upgrade scratch git drops every GIT_ variable (F1 remainder); M21.41 notes rules name every clause break, small code and test fixes; M21.42 parse failures get the repair turn (final harness re-test). Deferred items are rc5 fixes (M22.19 to M22.21).

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
