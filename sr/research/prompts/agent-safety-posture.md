# Deep-research prompt: agent safety and governance posture

Paste into a deep-research tool (ChatGPT Deep Research, Claude Research, or similar). It needs no access to the
specy-road repository; paste back the report.

---

I maintain an open-source Python toolkit that runs spec-driven, multi-agent software work: it drives coding-agent
CLIs (Claude Code, Cursor's agent CLI, OpenAI Codex CLI) as unattended executors and as code reviewers, in git
worktrees, with a review gate (two approvals from distinct model families before a change lands), touch zones
(declared file scope per task), and a tool-call guard that denies some shell commands. The toolkit does not call
LLMs itself; it orchestrates harness CLIs and recommends settings rather than enforcing them silently.

I want to design an "agent safety and governance posture" feature: a project records its posture once (for example
prototype / internal / production or security-sensitive; data sensitivity; interactive vs unattended agents), an
advisor (the team's own coding agent, reading the project's constitution, vision, constraints and governance docs)
proposes the posture for a human to confirm, and a `doctor` command reports gaps between recommended and configured
protections. Please research:

1. Incidents and failure modes of autonomous coding agents in 2025-2026: production databases deleted, destructive
   migrations, force-pushes over history, cloud resources destroyed, secrets leaked or exfiltrated, tests or
   approvals faked ("reward hacking"). For each well-sourced case: what access the agent had and what control would
   have prevented it. Mark weakly sourced claims.
2. Protection categories and current best practice: least privilege (no production credentials in agent workspaces,
   read-only database roles, scoped tokens), isolation (sandboxes, devcontainers, disposable VMs/microVMs, network
   egress limits), destructive-command guards (DROP/TRUNCATE/unbounded DELETE, rm -rf, git force-push/reset on shared
   refs, terraform/pulumi destroy, kubectl delete, cloud CLI deletes), human approval for irreversible actions,
   tamper-evident audit trails (e.g. cryptographically signed review records), blast-radius limits, backups and
   point-in-time recovery, branch protection.
3. What each harness provides natively today: Claude Code permissions (allow/deny rules), hooks and sandboxing;
   Codex CLI sandbox modes and approval policies; Cursor agent CLI controls; how a toolkit can declare one policy and
   translate it into each harness's own settings.
4. Buy vs build: open-source tools a Python toolkit could depend on, integrate optionally, or merely recommend
   (policy engines such as OPA/Rego; sandbox runtimes such as gVisor, Firecracker, devcontainers, bubblewrap; secret
   scanners such as gitleaks and trufflehog; database/infrastructure guard tools; agent-guardrail projects). For each:
   license, maturity and maintenance, dependency weight, local/offline suitability, supply-chain risk.
5. A recommended design: posture levels; a table of posture -> protections (on / recommended / off); what the toolkit
   should build, what it should delegate to harness settings, and what it should recommend to the platform (database
   roles, cloud IAM, branch protection); 4-8 concrete first work items; open questions.
Cite sources with URLs and dates.
