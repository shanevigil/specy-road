## Intent

Make the harness around agents cheaper to run and harder to drift, using what the 0.3.1 line taught us while coordinating specy-road's own leaves: review loops that keep finding new input classes, refusals that say "no" without saying what to do next, docs and agent files that silently fall behind the code, and no shared view of which areas of a project keep failing review or carry known debt. Each child turns one of those into a mechanical, tested rule rather than a coordinator's judgement call.

## Approach

- Children are independent: M12.1 (fix-round budget and deferral), M12.2 (refusals name their fix), M12.3 (gardening scans) and M12.4 (quality signals: per-area scores, then a debt ledger) can run in parallel; only M12.4.2 waits for M12.4.1.
- Everything is opt-in or additive: a project that sets no new policy key sees today's behaviour, and `digest --check` stays deterministic.
- Reuse before adding: review/RCA records (`specy_road/review_rca.py`, `specy_road/review_gate.py`), the decisions ledger (`specy_road/decisions.py`), chores (`specy_road/bundled_scripts/chore_cli.py`), the digest (`specy_road/digest.py`) and the add-node write. New commands hang off existing CLI modules where they can.
- Done when every child is Complete and its docs section exists; the phase adds no new top-level design note beyond updates to `docs/design-notes/review-loop-rca.md`.

## Tasks / checklist

- [ ] M12.1 — fix-round budget; RCA `defer_findings`; human-only apply with an audit trail.
- [ ] M12.2 — the three rc3 refusals print a runnable next step; rule documented and tested.
- [ ] M12.3 — `chore garden` scans, idempotent `--open-chores`, cadence warning.
- [ ] M12.4 — quality signals milestone (M12.4.1 per-area scores, M12.4.2 debt ledger).
- [ ] M12.5 — automatic cleanup of landed leaves and stale worktrees, saving hand-off files first.
- [ ] M12.6 — (low priority) command parsers reachable; stale-flag scan.
- Out of scope: changing escalation thresholds or the review gate's approval rules beyond the deferral in M12.1; automatic code fixes from any scan; hosted dashboards.

## References

- Roadmap chunk for `M12` (`roadmap/phases/M12.json`)
- `work/coordinator-rough-edges.md` (maintainer notes, untracked) — source of the loop and refusal problems
- `docs/orchestration-review.md`, `docs/orchestration-chores.md`, `docs/design-notes/review-loop-rca.md`
- No `shared/` contract applies.
