# Dependency and supply-chain verification

This document describes how the **specy-road** toolkit repository approaches dependency risk: what is automated in CI, what maintainers run locally, and what requires human review. It applies to **Python** (this package and its dev dependencies) and **npm** (the PM Gantt UI under `gui/pm-gantt/`).

## Scope

| Surface | Location | CI default |
|--------|-----------|------------|
| Python runtime + dev/test | [`pyproject.toml`](../pyproject.toml), installed via [`requirements-ci.txt`](../requirements-ci.txt) | Yes |
| Optional extras (`gui`, `gui-next`, `review`) | Same `pyproject.toml` | Not installed in default CI — if you use them locally or in a custom env, audit that environment separately |
| npm (Gantt) | [`gui/pm-gantt/package.json`](../gui/pm-gantt/package.json) + `package-lock.json` | Yes (`npm ci`, prod deps for `npm audit`) |

## Policy

In addition to code review, audit **direct and transitive** Python and npm dependencies used in the contexts above.

For each dependency, the audit should:

1. Identify **package name**, **resolved version**, and whether it is **direct** or **transitive**.
2. Check authoritative advisory sources for known vulnerabilities, malware advisories, takedowns, compromise reports, or unsafe/deprecated status.
3. Check for known **malicious-package** indicators, including typosquatting, brand impersonation, sudden maintainer or publisher changes, suspicious install/postinstall scripts, credential theft behavior, obfuscation, remote-code download behavior, and unexpected network/system access.
4. Verify package **provenance** and publisher trust signals where available.
5. Flag packages that are **unmaintained**, **deprecated**, **archived**, or have materially weak trust signals when they are **security-relevant**.
6. Distinguish:
   - known exploitable vulnerability,
   - known malicious package,
   - elevated supply-chain risk / suspicious indicators,
   - policy violation due to unapproved source or version.

### Minimum acceptable sources (tool mapping)

| Source | How this repo uses it |
|--------|------------------------|
| PyPA Advisory Database / PyPI advisories, **OSV**, GitHub Advisory Database | **[pip-audit](https://pypi.org/project/pip-audit/)** (Python environment) — consult upstream docs for the exact advisory pipelines. |
| npm advisory data, **OSV**, GitHub Advisory Database | **`npm audit`** on the Gantt tree; optional second pass with **[OSV-Scanner](https://google.github.io/osv-scanner/)** on lockfiles (see CI). |
| OpenSSF malicious-packages corpus | Overlaps with **OSV** for many entries; **no single OSS tool** replaces judgment — use periodic manual review and optional commercial feeds (below). |
| Optional supplemental intelligence | Socket, Phylum, ReversingLabs, or equivalent — **not** required for this repo; adopt if your organization mandates them. |

### Policy rules

- Prefer **official registries** and **official publisher namespaces/scopes**.
- Treat **third-party mirrors**, **ad hoc tarballs**, **git URLs**, and **unpinned floating versions** as higher risk unless explicitly approved.
- Flag **npm lifecycle scripts** (especially `preinstall` / `install` / `postinstall` / `prepare`) and **Python setup/build hooks** when they execute shell commands, download remote content, alter credentials, or touch sensitive files.
- Flag dependencies with **recent compromise reports** even if a CVE is not yet assigned.
- **Do not** auto-upgrade or replace dependencies until findings are reviewed (Dependabot may open PRs; **humans** merge after review).

## What is automated vs manual

| Tier | What | Notes |
|------|------|--------|
| **CI** | `pip-audit` on the **frozen** install from `requirements-ci.txt`; `npm ci` + `npm audit --omit=dev` + `npm run lint` (Gantt); optional OSV-Scanner on lockfiles; lockfile-lint for npm | Gates merges to protected branches |
| **Local** | Same commands as [contributor-guide.md](contributor-guide.md#supply-chain--dependency-audits) | Run before release or when changing dependencies |
| **Periodic / release** | Human review using the checklist below | Typosquatting, maintainer churn, script review, rumors before CVEs |
| **Optional vendor** | Socket, Phylum, etc. | Org policy |

## Frozen Python resolution (maintainers)

CI and reproducible audits use **[`requirements-ci.txt`](../requirements-ci.txt)** — a **compiled** lock produced from `pyproject.toml` with the **`dev`** extra (not hand-edited).

**Regenerate** after changing dependencies in `pyproject.toml`:

```bash
pip install pip-tools
pip-compile requirements-ci.in -o requirements-ci.txt
```

**Install** like CI:

```bash
pip install -r requirements-ci.txt
```

Then run `pip-audit` (see [contributor-guide.md](contributor-guide.md#supply-chain--dependency-audits)).

## Reporting discipline: repo-scoped first

When reporting Python audit results, separate findings into two buckets:

1. **Repo-scoped (authoritative)** — `pip-audit -r requirements-ci.txt` after installing from the same file.
2. **Host/global environment (informational only)** — unscoped `pip-audit` from a developer machine.

Do not mix these in a single severity list. If unscoped host findings appear, explicitly mark them as **out of repo lock context** unless the package is also present in `requirements-ci.txt`.

## Optional extras audit procedure (`review`, `gui`, `gui-next`)

Default CI does not install optional extras. If you use them, run a separate audit in an isolated environment and report it as an **extras-scoped** pass:

```bash
python -m venv .venv-audit-extras
source .venv-audit-extras/bin/activate
pip install -e ".[review,gui-next]"
python -m pip install --upgrade 'pip>=25.3'
pip install pip-audit
pip-audit -f json
```

Use the same reporting split as above (extras-scoped vs host/global noise).

## Direct vs transitive (optional deep dive)

CI tools do not always print a combined “direct vs transitive” column. For a one-off report:

- **Python:** `pipdeptree --json-tree` (or `pip list -v`) and join with `pip-audit -f json`.
- **npm:** `npm ls --all --json` and compare package names to top-level `dependencies` in `package.json`.

## npm registry policy (lockfile)

The Gantt UI uses **`npm ci`** with a committed **`package-lock.json`**. CI runs **lockfile-lint** to reduce risk from unexpected registry hosts or schemes — see [`.github/workflows/validate.yml`](../.github/workflows/validate.yml).

## Pre-commit

Supply-chain scans are **not** part of the default pre-commit hooks (network use and latency). Run audits **locally** when changing dependencies or rely on **CI**.

## Finding report template

For each dependency finding (human or tool), record:

| Field | Content |
|-------|---------|
| **Severity** | CRITICAL / HIGH / MEDIUM / LOW |
| **Ecosystem** | PyPI / npm |
| **Package** | Name |
| **Installed version** | Resolved version |
| **Advisory or source** | CVE, GHSA, OSV id, npm advisory, blog, vendor report |
| **Why it is risky** | CVE, malware advisory, suspicious behavior, untrusted publisher, unsafe script, policy violation, etc. |
| **Realistic impact** | What could happen in **this** repo’s usage |
| **Remediation** | Pin safe version, replace package, remove, block publisher, disable script, vendor review, allowlist with expiry, etc. |

Machine-readable inputs: `pip-audit -f json`, `npm audit --json` (and OSV-Scanner JSON if used). CI may upload these as workflow artifacts for traceability.

## Quarterly manual checklist (supplemental)

Use when dependencies change little but calendar time passes, or after industry incidents:

- [ ] Skim release notes / security lists for **direct** dependencies.
- [ ] Spot-check **transitive** packages that execute code at install time (npm scripts; Python sdist/build).
- [ ] Confirm no **git:** or **http:** npm sources unless explicitly approved (lockfile-lint helps).
- [ ] Re-run advisory scans in a **clean** venv and fresh `npm ci`.

## See also

- [install-and-usage.md](install-and-usage.md) — end-user install
- [contributor-guide.md](contributor-guide.md) — exact local audit commands
- [README.md](../README.md) — maintainer verification summary  
- [`.github/workflows/validate.yml`](../.github/workflows/validate.yml) — CI steps and artifacts  
