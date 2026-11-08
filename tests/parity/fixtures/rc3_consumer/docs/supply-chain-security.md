# Dependency and supply-chain verification

Use this as a **starting policy** for your application repository. Adopt the sections that match your stack (Python only, npm only, or both). Wire the same checks into **CI** so they run on every change.

## Principles

- Audit **direct and transitive** dependencies for the environments you ship or run in production (and CI).
- Prefer **official registries**; treat **git URLs**, **ad hoc tarballs**, **mirrors**, and **floating unpinned** versions as higher risk unless approved.
- **Do not** merge automated dependency upgrades without human review of findings.
- Combine **tooling** (CVE/advisory scans) with **periodic human review** for typosquatting, install scripts, maintainer churn, and compromise rumors before CVEs exist.

## Minimum tooling (typical)

| Ecosystem | Examples | Advisory coverage |
|-----------|----------|-------------------|
| Python | `pip-audit` on a **frozen** environment (`pip-tools` / `uv` lock or `pip freeze` from CI) | PyPI/OSV pipelines (see `pip-audit` docs) |
| npm | `npm ci` + `npm audit` using a committed **`package-lock.json`** | npm / GitHub advisory pipeline |
| Cross-check | [OSV-Scanner](https://google.github.io/osv-scanner/) on lockfiles | OSV |

Optional: Socket, Phylum, ReversingLabs, or similar if your organization requires them.

## Policy checklist

For each dependency in scope, your process should be able to answer:

1. Package name, **resolved version**, direct vs transitive.
2. Known vulnerabilities or malware advisories (from the sources above).
3. Suspicious indicators: typosquatting, bad scripts, obfuscation, unexpected network access.
4. Provenance / publisher trust where available.
5. Unmaintained or deprecated packages that matter for security.

Classify findings: exploitable vuln, malicious package, elevated risk, or **policy** violation (unapproved source/version).

## Finding report (template)

| Field | Example |
|-------|---------|
| Severity | CRITICAL / HIGH / MEDIUM / LOW |
| Ecosystem | PyPI / npm |
| Package | `…` |
| Version | `…` |
| Reference | CVE / GHSA / OSV / vendor |
| Why risky | Short reason |
| Impact | In your app’s context |
| Remediation | Pin, replace, remove, allowlist with expiry, etc. |

## Related files in this scaffold

- [`constraints/README.md`](../constraints/README.md) — enforced repo rules (code/roadmap); supply-chain is operational policy you enforce in CI yourself.
