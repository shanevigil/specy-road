# Design notes index

**Historical triage** and **verbatim reference** notes describe the past or an outside proposal and must not be read as current instructions.
When one disagrees with `docs/*.md` or the code, the doc and the code win; only **live design** notes still describe how the code works.

| File | Subject | Status |
| --- | --- | --- |
| [`v0-3-0-orchestration-slices.md`](v0-3-0-orchestration-slices.md) | Model-aware orchestration on the `0.3.0` line: decisions and what each of slices 1–7 settled | live design |
| [`v0-3-1-worker-orchestration.md`](v0-3-1-worker-orchestration.md) | Workers behind the coordinator (slice 7): CLI adapters, no daemon, no MCP, reconciled against the cross-harness research | live design |
| [`v0-3-1-brainstorm-v2.md`](v0-3-1-brainstorm-v2.md) | Brainstorm v2: rounds, allocation, panel shards, quote-anchored evidence, reconciled against the ideation research | live design |
| [`agent-guidance-and-shared-checkouts.md`](agent-guidance-and-shared-checkouts.md) | Guiding agents outside a roadmap claim: the managed `AGENTS.md` block and `specy-road session` presence | live design |
| [`sre-for-ai-triage.md`](sre-for-ai-triage.md) | "SRE for AI" report triaged into six review-evidence slices, with the standing list of what was rejected | live design |
| [`pm-gui-integration-branch-auto-ff.md`](pm-gui-integration-branch-auto-ff.md) | PM GUI optional `fetch` + `merge --ff-only` of the integration branch: controls and safety | live design |
| [`pm-gantt-registry-checkout.md`](pm-gantt-registry-checkout.md) | PM Gantt registry data flow, the green outline accent and the Dev column precedence | live design |
| [`registry-hydration-remote-refs.md`](registry-hydration-remote-refs.md) | PM GUI remote registry overlay from `refs/remotes/*/feature/rm-*`, local-first response | live design |
| [`v0-3-1-rc1-adopter-feedback-triage.md`](v0-3-1-rc1-adopter-feedback-triage.md) | `v0.3.1-rc1` adopter feedback: upgrade path, brainstorm and promote, roadmap editing, review hand-off; open | historical triage |
| [`lean-code-census.md`](lean-code-census.md) | 2026-10-27 measurement of the suite and source against the lean-code research: coupling, overlap, unexecuted guards, scoped mutation, duplication | historical triage |
| [`v0-2-1-consumer-report-triage.md`](v0-2-1-consumer-report-triage.md) | `v0.2.1-rc2` consumer report (mckee_ui): seven findings, all fixed in `v0.2.2` | historical triage |
| [`v0-2-1-rc1-adopter-feedback-triage.md`](v0-2-1-rc1-adopter-feedback-triage.md) | `v0.2.1-rc1` adopter feedback: defects fixed in `v0.2.1-rc2` | historical triage |
| [`v0-2-2-milestone-grind-triage.md`](v0-2-2-milestone-grind-triage.md) | `v0.2.2` milestone-grind report: findings 30–40, acted on in the `0.3.0` line | historical triage |
| [`v0-2-2-unattended-multi-lane-triage.md`](v0-2-2-unattended-multi-lane-triage.md) | `v0.2.2` unattended two-lane grind report: three findings fixed in `v0.2.3` | historical triage |
| [`rc2-adopter-feedback-triage.md`](rc2-adopter-feedback-triage.md) | `v0.1.4-rc2` adopter feedback: 14 findings, fixed in `v0.1.4-rc3` | historical triage |
| [`model-aware-orchestration-proposal.md`](model-aware-orchestration-proposal.md) | External 2026-10-19 proposal for model-aware orchestration, kept byte-for-byte; decisions live in the slices note | verbatim reference |
| [`model-research-2026-10-26-claude.md`](model-research-2026-10-26-claude.md) | Claude run of the proposal's §7.2 model-research prompt, kept byte-for-byte; canonical profiles live in `model-profiles/` | verbatim reference |
