## Intent

Theme: **features for adopter projects** — upgrade, how the agent files layer (AGENTS.md, CLAUDE.md and the managed section), planning hygiene, and project tooling such as file limits and code-analysis checks. Fixes are not filed here. The phase starts after the 0.3.1 tag: it depends on gate M16.66, so nothing here is picked up before then.

## Approach

- One theme (maintainer rule, 2026-11-05): milestones M2–M15 take no new leaves; new adopter-project features go here. Fixes for the 0.3.1 line go to M16.65's feedback-and-fix intake.
- Not-started leaves assigned here by the themed-milestone restructure (2026-11-05), by their pre-move ids: M12.4.2, M12.5, M13.9, M13.11, M13.13, M15.7, M15.14. Each moved leaf's sheet names its old id.
- New leaf: configurable code-analysis tools (a project uses specy-road's built-in ruff checks from M16.8 or declares its own tools in `checks:`). Heavier analysis — mypy, radon, a duplication detector — is out of scope for M16 and is offered here only as tools a project declares, never as a specy-road dependency.
- M16 reshapes `upgrade` (M16.12), the agent entry (M16.30) and the config (M16.14, M16.52). Before pickup, re-check each leaf's acceptance and touch zones against that end state; M12.5, M13.9 and M15.7 keep their parked branches, which need a rebase onto the M16 layout.

## Tasks / checklist

- [ ] Re-scope each leaf against the M16 end state before its pickup.

## References

- M16 phase sheet (Revision 3, themed-milestone restructure)
- No `shared/` contract applies.
