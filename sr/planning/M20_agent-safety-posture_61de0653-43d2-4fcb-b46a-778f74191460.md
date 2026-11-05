## Intent

Theme: **agent safety and governance posture.** A project records how much protection it needs as data, an advisor prompt helps the team's own agent propose that posture from the project's governance docs, and a human confirms it. `doctor` then reports the gaps between the posture and what the repo, the roster and the harness settings actually provide. The theme also covers destructive-operation protections and isolation of workers and reviewers. Fixes are not filed here. The phase starts after the 0.3.1 tag: it depends on gate M16.66, so nothing here is picked up before then.

## Approach

- One theme (maintainer rule, 2026-11-05): milestones M2–M15 take no new leaves; new agent-safety and governance features go here. Orchestration and review-loop features go to M18, adopter-project features to M19, and fixes for the 0.3.1 line to M16.65's feedback-and-fix intake.
- Parts of the theme:
  - posture recorded as data (a posture block in `roadmap/orchestration.yaml`, levels such as prototype, internal, production, sensitive);
  - an advisor prompt that the team's own agent runs over the project's governance docs and repo signals (specy-road makes no model calls);
  - human confirmation of the posture (TTY-only, recorded identity);
  - `doctor` posture-gap reports;
  - destructive-operation protections (a speed bump in the guard, not a boundary);
  - isolation of workers and reviewers, including evidence that a "fresh" reviewer really is fresh.
- Real leaves are planned after the maintainer reads the two agent-safety research reports (the Claude report `sr/docs/research/agent-safety-posture-2026-11-05.md` and a pending Codex report) and a deep-research v2 prompt runs. M20.1 is that planning step. Until then the only other leaf is the reviewer instruction-leak probe, which has its own evidence (EGM issue #237).

## Tasks / checklist

- [ ] M20.1: plan the M20 leaves from the research.
- [ ] Re-scope each leaf against the M16 end state before its pickup.

## References

- `sr/docs/research/agent-safety-posture-2026-11-05.md` (section 6.6, candidate leaves)
- `sr/docs/research/elephant-goldfish-2026-11-05.md` (section 4, item 2: instruction-file leakage)
- The pending Codex agent-safety report (not yet filed)
- No `shared/` contract applies.
