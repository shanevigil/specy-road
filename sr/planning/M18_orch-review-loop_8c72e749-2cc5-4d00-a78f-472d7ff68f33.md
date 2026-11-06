## Intent

Theme: **orchestration and the review loop.** New behaviour for workers, reviewers and the coordinator — worker reconcile and post-run checks, review packets and review evidence, delegation, host effects, cleanup and scheduling. Fixes are not filed here. The phase starts after the 0.3.1 tag: it depends on gate M16.8.9, so nothing here is picked up before then.

## Approach

- One theme (maintainer rule, 2026-11-05): milestones M2–M15 take no new leaves; new orchestration and review-loop features go here. Fixes for the 0.3.1 line go to M16.8.4's feedback-and-fix intake.
- Not-started leaves assigned here by the themed-milestone restructure (2026-11-05), by their pre-move ids: M12.4.3, M14.4.2, M14.4.3, M14.8, M14.9, M15.5, M15.16, M15.20, M15.25, M15.28, M15.29, M15.30. Each moved leaf's sheet names its old id.
- M16 moves most orchestration code into one subpackage (M16.3.1) and replaces the verify and land keys with `checks:` (M16.4.5, M16.4.6). Before pickup, re-check each leaf's acceptance and touch zones against that end state; M15.20 and M15.25 keep their parked branches, which need a rebase onto the M16 layout.
- Coordinator-tools harvest (2026-11-05): M18.20-M18.27 turn the 0.3.1 grind's dispatcher, watchdog, review queue, account split, reviewer wrappers, zone edits and append-only CHANGELOG handling into product features; inventory and the tools judged coordinator-only in `sr/docs/research/coordinator-tools-2026-11-05.md`.

## Tasks / checklist

- [ ] Re-scope each leaf against the M16 end state before its pickup.

## References

- M16 phase sheet (Revision 3, themed-milestone restructure)
- No `shared/` contract applies.
