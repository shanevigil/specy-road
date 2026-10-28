# Triage: "SRE for AI" research report → review and QA

> **Outcome:** six small slices built on `WIP/improvements-0-3-1`; everything
> production-operations-shaped rejected. Contributor procedure for review
> rounds: [contributor-guide.md](../contributor-guide.md#independent-review-rounds).

## Input

"Reliability Engineering for spect-road: A 2026 Research and Product
Blueprint", a ChatGPT deep-research run on applying SRE practice to AI/agent
systems, 2026-10-27 (777 lines). It was a temporary file in the repo root and
is **not committed**; this note keeps what matters, as
[v0-3-1-worker-orchestration.md](v0-3-1-worker-orchestration.md) did for its inputs.

## The report in ten lines

- Reliability for AI-operated systems is a **closed loop** with a **deterministic policy layer** that authorizes and actuates; models only investigate and recommend.
- Its one strong idea is an **evidence discipline**: every assertion carries provenance (`observed | inferred | declared | unknown`), source and time, and "we do not know" is recorded. A readiness claim climbs **declared → observed → tested → validated**.
- It rests on Google SRE posts, OpenTelemetry/OpenSLO specs, vendor docs (Gremlin, AWS FIS, PagerDuty, Rootly, Antithesis), Microsoft/Salesforce RCA papers, and one Substack post it calls "a design manifesto, not a research paper".
- It is written for a **production-operations product** (telemetry, SLOs, chaos, remediation), not a roadmap-and-review toolkit; its effort estimates are invented; it never asks what evidence looks like when the "system" is a code change and the "incident" is a wrong review.

## Triage

Verdicts: **adopt**, **adapt**, **present** (already does it), **reject** (does not fit, or needs a model API / daemon / MCP / a reopened decision).

| # | Idea | Maps to | Verdict | Reasoning |
|---|---|---|---|---|
| 1 | Deterministic policy authorizes; model recommends | `review_gate.py`, `--yes` never approves; D7 | present | The gate is a file-and-git rule set. |
| 2 | Provenance labels on every assertion | packet sections; worker events `source`/`authority` | adapt → S2 | The packet mixed executor claims with git facts unlabelled. |
| 3 | Source + timestamp for evidence fields | `review_packet.py::_header` | adapt → S2 | Policy source ref/SHA and date; the commit is the binding. |
| 4 | Negative knowledge | `possibly_modified_externally`, PASS-WITH-NOTE | present, + S1 | An empty `verify` rendered as silence. |
| 5 | Declared → observed → tested → validated | READY `verify`, `commands_rerun`, gate | adapt → S1, S3 | The rungs existed; nothing checked them. |
| 6 | Unsupported-claim rate | `commands_rerun` | adapt → S3 | A policy switch, not a metric. |
| 7 | Evidence / SLO coverage | `validate` | adapt → S4 | A leaf with no `acceptance` gets a review that attests nothing. |
| 8 | MTTR, attribution, RCA top-k, rollback, ROI metrics | none | reject | No referent in a roadmap toolkit. |
| 9 | Go/no-go gates per capability | sandbox runbook, release runbook §8 | present | |
| 10 | Incident learnings into memory | review-round tests, CHANGELOG, design notes | present, adapt → S6 | Procedure was undocumented. |
| 11 | Chaos / fault injection | fake-harness tests, runbook §5.9, `terminate` | present, adapt → S5 | Nobody killed the real harness under a real wrapper. |
| 12 | Deterministic simulation | fake harness in `tests/test_worker_cli.py` | present | Do not add more. |
| 13 | Experiment result downgrades readiness | new commit stales reviews; block returns leaf | present | |
| 14 | Evidence age / retest cadence | `models stale` | present (profiles); reject (adapters) | Runbook records CLI versions. |
| 15 | Execution gateway with preconditions | `worker delegate` preconditions, `abort-task-pickup` | present | Rollback is git. |
| 16 | Agent identity without ambient permissions | stated limit; signed reviews | present as limit | OS isolation is out of scope. |
| 17 | Signed requests, audit trail | signed reviews, `Reviewed-by`, event log | present | |
| 18 | Autonomy ladder | gate on by default; eligibility, `class`, `sensitivity`; D7 | present | |
| 19 | Kill switch | `worker terminate`, grind exit 4, `session guard` | present | |
| 20 | Unified change timeline | `history`, `worker events`, git | present | |
| 21 | Observed vs declared dependencies | touch-zone flags, `worker reconcile` | present | |
| 22 | Topology / knowledge / state lenses | brief + `handoff status` | present | |
| 23 | Reconstruction tax | `brief`, `history`, archived search | present | |
| 24 | Prompt/tool injection | `_DATA_LINE`, untrusted-data delimiters | present | |
| 25 | Continuous evaluation, fallback | pytest, file-limits, fixture gates, runbook | present | |
| 26 | Shadow mode / replay | review-round regression tests | present | |
| 27 | Adapters over owning the data plane | harness adapters (D2) | present | |
| 28 | SLOs, error budgets, OpenSLO | none | reject | No telemetry, no consumer. |
| 29 | Progressive delivery, canaries | `dev → main` PR + tag gate | reject | Needs a running service. |
| 30 | Resilience pattern linter | `validate`, `file-limits` | reject; adapt → S4 | Only review readiness is lintable. |
| 31 | Reliability Evidence Graph | roadmap + registry + events | reject | A second data plane. |
| 32 | LLM-assisted RCA | none | reject | Model call from the CLI. |
| 33 | Agentic remediation control plane | none | reject | Daemon; reopens D3. |
| 34 | Predictive change risk | none | reject | Needs telemetry and a model. |
| 35 | Digital / scenario twins, DST | none | reject | The fake harness is the only twin needed. |
| 36 | Reliability economics / ROI | none | reject | No cost data. |
| 37 | OTel, OpenSLO, Datadog, PagerDuty, Gremlin, FIS, … integrations | none | reject | Production actuators the toolkit never touches. |
| 38 | SRE entity model | existing schemas | reject | Renaming is churn. |
| 39 | Runbook automation | `grind-session` hooks, `/specyrd-orchestrate` | present | |
| 40 | 18-week, 4–5 FTE roadmap | none | reject | Invented numbers for another product. |

## Built

| Slice | What | Commit |
|---|---|---|
| S1 | `handoff status` and the packet report a non-zero or missing READY verifier; state unchanged | `2ddf5fc` |
| S2 | Packet sections state their provenance; header names the policy source and generation | `9e76924` |
| S3 | `policy.reviewer_reruns_required` (default false); the interactive human approval is exempt | `79eaee6` |
| S4 | `validate` warns on open leaves without `acceptance` while the gate is on | `8e56f74`, `45fcb9c` |
| S5 | Runbook §5 step 9b: kill the wrapper, then the harness; negative evidence in §0 | `129a39d` |
| S6 | This note and the contributor guide's review-round procedure | this note's commit |

Maintainer questions were answered as the triage recommended: a failing
verifier does not block the gate (the exit code is the executor's claim);
the rerun switch defaults off; `docs/orchestration.md` was trimmed rather
than given a `file-limits` override; the acceptance warning is silent with
the gate off; the packet records a date plus `HEAD`, not a clock time; the
report is not committed.

Reading the code for S5 corrected the triage's guess: a harness killed under
a live wrapper leaves the worker `failed` (an `error` event with the signal's
negative exit), not `idle`, so `worker resume` refuses it.

## Rejected, so it is not re-added

SLOs, error budgets and "review SLOs" (#28); a second evidence graph, entity
model or vector index (#31, #38); any model call from the CLI for RCA or
memory (#32; `review-node` stays the opt-in PM planning reviewer); a
remediation control plane, action service, daemon or MCP surface (#33; D1,
D3); predictive scoring and twins (#34, #35); ROI models (#36); telemetry or
vendor adapters (#37); a metrics command or scorecard (#8); canary gates on
`dev → main` (#29); an adapter-staleness clock (#14); renaming fields to SRE
nouns or adding `confidence` numbers; reopening D1–D7, the slice-1 gate
rules, or signed reviews.
