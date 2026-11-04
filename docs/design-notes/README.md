# Design notes index

**Historical triage** and **verbatim reference** notes describe the past or an outside proposal and must not be read as current instructions.
When one disagrees with `docs/*.md` or the code, the doc and the code win; only **live design** notes still describe how the code works.

| File | Subject | Status |
| --- | --- | --- |
| [`v0-3-0-orchestration-slices.md`](v0-3-0-orchestration-slices.md) | Model-aware orchestration on the `0.3.0` line: decisions and what each of slices 1–7 settled | live design |
| [`v0-3-1-worker-orchestration.md`](v0-3-1-worker-orchestration.md) | Workers behind the coordinator (slice 7): CLI adapters, no daemon, no MCP, reconciled against the cross-harness research | live design |
| [`v0-3-1-brainstorm-v2.md`](v0-3-1-brainstorm-v2.md) | Brainstorm v2: rounds, allocation, panel shards, quote-anchored evidence, reconciled against the ideation research | live design |
| [`regression-prevention.md`](regression-prevention.md) | Keeping the integration branch green when many agents land: land check on the merge commit, test-integrity findings, escalation channel, declared test changes (milestone `M9`) | live design |
| [`context-feedback-pilot.md`](context-feedback-pilot.md) | The opt-in `prompt --context-feedback` block, its triage rule, and the 2026-11-02 pilot's hit rate; shipping it by default is undecided | live design |
| [`agent-guidance-and-shared-checkouts.md`](agent-guidance-and-shared-checkouts.md) | Guiding agents outside a roadmap claim: the managed `AGENTS.md` block and `specy-road session` presence | live design |
| [`sre-for-ai-triage.md`](sre-for-ai-triage.md) | "SRE for AI" report triaged into six review-evidence slices, with the standing list of what was rejected | live design |
| [`pm-gui-integration-branch-auto-ff.md`](pm-gui-integration-branch-auto-ff.md) | PM GUI optional `fetch` + `merge --ff-only` of the integration branch: controls and safety | live design |
| [`pm-gantt-registry-checkout.md`](pm-gantt-registry-checkout.md) | PM Gantt registry data flow, the green outline accent and the Dev column precedence | live design |
| [`registry-hydration-remote-refs.md`](registry-hydration-remote-refs.md) | PM GUI remote registry overlay from `refs/remotes/*/feature/rm-*`, local-first response | live design |
| [`reviewer-effort-study.md`](reviewer-effort-study.md) | Does a lower reviewer effort change review verdicts? The 2026-11-02 study (`M10.6`) that the shipped `effort_by_role` reviewer defaults in the model profiles cite | live design |
| [`v0-3-1-rc1-adopter-feedback-triage.md`](v0-3-1-rc1-adopter-feedback-triage.md) | `v0.3.1-rc1` adopter feedback: upgrade path, brainstorm and promote, roadmap editing, review hand-off; open | historical triage |
| [`context-regressions-2026-11-04-triage.md`](context-regressions-2026-11-04-triage.md) | First context-regression replay (0.3.1rc3 candidate): cause per failing case and harness, what `fix/pre-release-context-regressions` changed (CR5, CR9), what was documented (CR1, CR10), the Cursor hook finding (CR3) and proposed case changes | historical triage |
| [`harness-facts-2026-11-02-triage.md`](harness-facts-2026-11-02-triage.md) | 2026-11-02 harness-capabilities research triaged into fixture rows F1-F22 (vendor-sourced), the Codex 0.166.0 capture and runtime checks K7, K8 and K13, and the new workflow words (M11.60) | historical triage |
| [`M8.7-runtime-verification-harness-facts.md`](M8.7-runtime-verification-harness-facts.md) | 2026-11-02 runtime checks of the harness facts (Claude Code 2.1.312, Codex CLI 0.165.0, Cursor agent) in a scratch repository and sibling worktrees; the `runtime:` citations in the model profiles point here | historical triage |
| [`agent-performance-research-triage.md`](agent-performance-research-triage.md) | 2026-10-30 agent-performance and orchestration research: what each report is worth, which claims about specy-road were checked, and the maintainer decisions it left (became phase `M10`) | historical triage |
| [`managed-section-ablation.md`](managed-section-ablation.md) | 2026-11-02 reduced study of the managed `AGENTS.md`/`CLAUDE.md` section on and off (1 app × 3 harnesses × 2 runs): turns, tokens, cost, first-round review; verdict test further | historical triage |
| [`lean-code-census.md`](lean-code-census.md) | 2026-10-27 measurement of the suite and source against the lean-code research: coupling, overlap, unexecuted guards, scoped mutation, duplication | historical triage |
| [`v0-2-1-consumer-report-triage.md`](v0-2-1-consumer-report-triage.md) | `v0.2.1-rc2` consumer report (mckee_ui): seven findings, all fixed in `v0.2.2` | historical triage |
| [`v0-2-1-rc1-adopter-feedback-triage.md`](v0-2-1-rc1-adopter-feedback-triage.md) | `v0.2.1-rc1` adopter feedback: defects fixed in `v0.2.1-rc2` | historical triage |
| [`v0-2-2-milestone-grind-triage.md`](v0-2-2-milestone-grind-triage.md) | `v0.2.2` milestone-grind report: findings 30–40, acted on in the `0.3.0` line | historical triage |
| [`v0-2-2-unattended-multi-lane-triage.md`](v0-2-2-unattended-multi-lane-triage.md) | `v0.2.2` unattended two-lane grind report: three findings fixed in `v0.2.3` | historical triage |
| [`rc2-adopter-feedback-triage.md`](rc2-adopter-feedback-triage.md) | `v0.1.4-rc2` adopter feedback: 14 findings, fixed in `v0.1.4-rc3` | historical triage |
| [`model-aware-orchestration-proposal.md`](model-aware-orchestration-proposal.md) | External 2026-10-19 proposal for model-aware orchestration, kept byte-for-byte; decisions live in the slices note | verbatim reference |
| [`model-research-2026-10-26-claude.md`](model-research-2026-10-26-claude.md) | Claude run of the proposal's §7.2 model-research prompt, kept byte-for-byte; canonical profiles live in `model-profiles/` | verbatim reference |
