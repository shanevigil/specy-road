# Deep-research prompt (v2): agent safety and governance posture for a spec-driven agent toolkit

Paste into a deep-research tool (ChatGPT Deep Research, Claude Research). It needs no repository access. Paste the
report back; it is saved as `docs/research/agent-safety-posture-<date>-<tool>.md`.

---

## Context: the toolkit and its fixed constraints

I maintain an open-source Python toolkit for spec-driven, multi-agent software work. It drives existing coding-agent
CLIs (Claude Code, Cursor's agent CLI, OpenAI Codex CLI) as unattended executors and as code reviewers, in git
worktrees, on the user's own subscription logins. Every change is reviewed by two reviewers from distinct model
families before it lands; each task declares the files it may touch; a tool-call guard denies some shell commands.

Any proposal must fit these constraints. Mark anything that breaks one as INCOMPATIBLE rather than recommending it:
1. The toolkit never calls an LLM itself; any reasoning step is done by the user's own coding agent through a prompt
   the toolkit generates.
2. It orchestrates the existing harness CLIs (and their subscription billing); it does not replace them with direct
   API agents.
3. It recommends; it does not silently enable or enforce. A human confirms every posture decision.
4. Local-first and offline-capable; the core is Python standard library only.
5. Policy is data read from the integration branch (YAML), validated by a schema.
6. Cautious about dependencies (pinned, hash-checked, license-reviewed; copyleft avoided in anything bundled).

## What two independent research runs already established (don't repeat; build on it)

- Real incidents share one pattern: the agent could reach production credentials or the real filesystem, ran with
  auto-approve, and backups sat in the same blast radius (Replit/SaaStr 2025; DataTalks.Club Terraform destroy that
  also removed snapshots, Feb 2026; Nx "s1ngularity" supply-chain use of agent CLIs, Aug 2025; Cursor denylist bypass
  CVE-2025-54131). AWS/Kiro causation is disputed; force-push incidents are anecdotal. Command-pattern blocking alone
  would not reliably have prevented any of them; least privilege and isolation would.
- In our own replay, unattended executors forged review approvals three ways (drove the human prompt with `expect`,
  called the record writer directly, added themselves to the roster). Signed reviews with keys outside the executor's
  reach plus branch protection close this.
- Both runs recommend: build a small posture contract (stored as data), an advisor prompt, human confirmation, and a
  deterministic `doctor` gap report that distinguishes configured / verified / attested / unknown; delegate execution
  boundaries to harness settings and the OS; recommend production controls (DB roles, cloud IAM, branch protection)
  to the platform owner; add no mandatory runtime dependency.
- Our own default launches Cursor workers with `--force` (allow everything not denied); we are changing that to a
  sandboxed default with an explicit opt-in.

## Open questions to research in depth

1. **Signed reviews by default?** One run's posture table makes signed reviews ON for internal-and-above projects; our
   current decision is OFF by default with a warning for unattended executors. What do comparable tools and
   regulated-environment guidance (SLSA, OpenSSF Scorecard, supply-chain attestations, code-signing practice) imply
   about defaults versus friction for small teams? Concrete key-management patterns that keep reviewer keys out of an
   executor's reach on a single developer machine (separate OS user, hardware keys, ssh-agent confinement, OS keychain).
2. **Compiling one policy to each harness.** For Claude Code (permission rules, hooks, sandbox), Codex CLI (sandbox
   modes, approval policy, rules), and Cursor agent CLI (permissions.deny, sandbox, hooks): exact current settings,
   what each can and cannot enforce (shell only? file tools? network? reads of ~/.ssh, ~/.aws?), version-specific
   gaps, and known bypasses. Produce a capability matrix and say where an OS-level boundary is required instead.
3. **Destructive-operation protection without model calls.** Which deterministic checks are worth building (git
   force-push and shared-ref deletion, `terraform/pulumi destroy`, `kubectl delete`, cloud CLI deletes, SQL DDL and
   unbounded DML in migrations) and which belong to platform controls instead? Evidence on false-positive rates and
   bypasses of command filters.
4. **Isolation options for a local developer**, ranked by friction and strength: harness sandboxes, devcontainers,
   rootless containers, gVisor, microVMs (Firecracker), bubblewrap, separate VM over MCP. What is realistic for one
   developer on Linux/macOS, and how a toolkit can detect (verify vs. attest) which one is in use.
5. **Posture model.** How should levels be defined (prototype / internal / production / sensitive, or by data
   sensitivity × autonomy × blast radius)? How do existing frameworks (NIST AI RMF, OWASP LLM/Agentic Top 10, SLSA
   levels, CIS) map to concrete protections? What should an unconfirmed posture default to?
6. **Advisor prompt design.** Best practice for an agent reading a project's governance documents (constitution,
   vision, constraints) to propose a posture with cited evidence, while resisting prompt injection from those
   documents, and how to make its output deterministic enough to diff over time.

## Weighted buy-vs-build (required for every candidate tool)

Score each candidate 0–3 on each criterion, show the weighted total, and give a verdict: **adopt as dependency**,
**integrate optionally** (detect and use if installed), **recommend only**, **build in-house**, or **incompatible**.

| Criterion | Weight |
|---|---|
| Fit with the six constraints above | 3 |
| Coverage of the problem it addresses | 2 |
| Supply-chain risk (maintainers, release signing, incident history) | 2 |
| License (permissive vs copyleft for bundling) | 2 |
| Maturity and maintenance (releases, issue response, adoption) | 1 |
| Dependency weight and runtime (pure Python vs Go/Rust binary vs service) | 1 |
| Local/offline suitability | 1 |
| Integration effort for a Python CLI | 1 |

Candidates to include at minimum: OPA/Conftest, gVisor, Firecracker, devcontainers CLI, bubblewrap, gitleaks,
TruffleHog, Squawk, pg_safeupdate, Invariant Guardrails, LlamaFirewall, container-use, and any newer agent-specific
sandbox or guardrail projects from 2026. Note LLM-based guardrails conflict with constraint 1 unless run by the user's
harness.

## Output

1. A short executive summary with a recommended first slice of work (3–5 items).
2. The capability matrix (question 2) and the scored buy-vs-build table.
3. Answers to each open question with evidence, marking weak or vendor-only sources.
4. A posture → protections table (on / recommended / off) for each level.
5. Disagreements with the two prior runs' conclusions, if the evidence supports them.
Cite sources with URLs and dates.
