# Recurring Audit Prompts (Generic)

A collection of reusable audit/review prompts for architecture compliance,
quality checks, and release readiness.

---

## Docs-first usage (required)

Before using any prompt in this file:
- Read `docs/` (or the repo's canonical docs location) to identify architecture
  rules, ownership boundaries, contracts, conventions, and verification gates.
- Do **not** assume fixed filenames, branch names, or toolchains.
- If required information is missing, stop and ask for placeholders:
  - `[YOUR_STATIC_ANALYSIS_CMD]`
  - `[YOUR_TEST_CMD]`
  - (optional) `[YOUR_DEPENDENCY_INSTALL_CMD]`
  - (optional) `[YOUR_SECURITY_SCAN_CMD]`

**specy-road toolkit (this repository):** canonical commands live in `docs/setup.md` (see **Dependency and security checks** and **CI**). Typical substitutions when running prompts here:

| Placeholder | specy-road toolkit command |
|-------------|----------------------------|
| `[YOUR_DEPENDENCY_INSTALL_CMD]` | `pip install -r requirements.txt && pip install -e ".[dev]"` |
| `[YOUR_SECURITY_SCAN_CMD]` | `pip install pip-audit && pip-audit` (same venv as dev install; optional `PIPAPI_PYTHON_LOCATION="$(command -v python)"` if pip-audit warns). Gantt UI: `cd gui/pm-gantt && npm ci && npm audit --omit=dev` |
| `[YOUR_TEST_CMD]` | `pytest` |
| `[YOUR_STATIC_ANALYSIS_CMD]` | No dedicated linter in this repo; use maintainer gates: `specy-road validate --repo-root tests/fixtures/specy_road_dogfood`, `specy-road export --check --repo-root tests/fixtures/specy_road_dogfood`, `specy-road file-limits` |

---

## Architecture & Vision Compliance

Purpose: Validate implementation against documented architecture and contract
rules.

```prompt
Audit the codebase for compliance with the repository's canonical docs.

First identify which docs define:
- Architecture and ownership boundaries (including allowed imports/dependencies)
- Contract surfaces (APIs, schemas, file formats, config)
- Conventions and constraints (naming, error handling, security)
- Verification gates

If these are not clearly documented, stop and ask the user which documents or
rules to enforce before continuing.

Audit scope:
1. Architecture/ownership compliance
2. Contract compliance
3. Convention compliance (only what docs explicitly define)
4. Work-tracking hygiene (only if the repo defines such a system)

For each gap, report:
- Severity (HIGH/MEDIUM/LOW)
- File and line reference
- Whether fix target is code or docs
- Risk/impact if changed

Before reporting a gap, verify against current file contents.

After fixes, run:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```

---

## Scoped Code Review

Purpose: Review only code changed in this session or since a selected baseline.

```prompt
Review all code changed in this session (or since the chosen baseline commit).

Check for:
1. Correctness issues (logic, edge cases, boundary error handling)
2. Quality issues (complexity, dead code, unclear ownership, over-abstraction)
3. Convention violations documented in project docs
4. Architecture/ownership boundary violations
5. Security regressions in changed code paths

For each issue, report:
- File + line
- Problem
- Suggested concrete fix
- Priority: must-fix (correctness/security) or should-fix (quality/style)

Do not propose broad unrelated refactors outside changed code.

After applying fixes:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```

---

## Test Coverage Gap Audit

Purpose: Identify high-risk untested behavior before writing additional tests.

```prompt
Audit tests against implementation to find coverage gaps.

If docs define an architecture/module map, use it to structure the audit.
If source/test layout is not documented, stop and ask the user for scope
directories before proceeding.

For each gap, report:
- Untested behavior
- Why it is risky
- Minimum useful test to add
- Recommended test type (unit/integration/e2e)

Prioritize by correctness/security risk first, then stability/operability.

Do not write tests yet; produce a prioritized gap report first.
If asked to proceed, add tests and verify with:
  [YOUR_TEST_CMD]
```

---

## Dependency Audit

Purpose: Identify vulnerable, stale, undeclared, or unused dependencies.

```prompt
Audit dependency hygiene for this repository.

First identify dependency manifests and package management process from docs.
If docs do not define install/update/security-scan workflow, stop and ask for:
- [YOUR_DEPENDENCY_INSTALL_CMD]
- [YOUR_SECURITY_SCAN_CMD]

Audit steps:
1. List production + development dependencies and pinned/ranged versions.
2. Flag known vulnerabilities and major-version lag where relevant.
3. Verify dependency changes follow documented lockfile/install policy.
4. Identify imports not declared in manifests (undeclared deps).
5. Identify declared packages not used in source/test paths (unused deps).

Run:
  [YOUR_SECURITY_SCAN_CMD]

Report each finding with package, issue type, and recommended action.
Do not auto-upgrade unless explicitly asked.

If asked to apply upgrades:
- Run [YOUR_DEPENDENCY_INSTALL_CMD]
- Then verify:
  - [YOUR_STATIC_ANALYSIS_CMD]
  - [YOUR_TEST_CMD]
```

---

## Security Audit

Purpose: Identify realistic attack surfaces and hardening gaps.

```prompt
Perform a security audit guided by project docs.

If docs define security policy, enforce that policy.
If security expectations are undocumented, stop and ask the user which policy
to apply before proceeding.

Audit areas (where applicable):
1. Subprocess safety and command construction
2. Input/path validation and traversal resistance
3. Config/secrets handling and redaction
4. Authn/authz boundaries
5. Dependency CVEs ([YOUR_SECURITY_SCAN_CMD])

For each finding, report:
- Severity (CRITICAL/HIGH/MEDIUM/LOW)
- File + line
- Attack vector and realistic impact
- Recommended fix

Do not apply changes until findings are reviewed.
After fixes:
- [YOUR_STATIC_ANALYSIS_CMD]
- [YOUR_TEST_CMD]
```

---

## Pre-Release Gate Check

Purpose: Run a release-readiness checklist and identify blockers.

```prompt
Run pre-release readiness checks. Mark each item PASS/FAIL/WARNING.

If docs do not define release checklist and commands, stop and ask the user.

1. Static analysis + tests
   - [YOUR_STATIC_ANALYSIS_CMD]
   - [YOUR_TEST_CMD]

2. Integration/smoke/release gates
   - Run repo-documented release validation commands.

3. Configuration/secrets hygiene
   - No hardcoded secrets
   - Startup/runtime behavior matches documented config policy

4. Dead code/debug artifact hygiene
   - No shipping debug statements, stale TODO/FIXME, or commented-out code
   - Follow project exceptions only if explicitly documented

5. Docs alignment
   - Contracts/architecture/operations docs reflect current behavior
   - Work-tracking artifacts are consistent (if repo uses them)

Treat every FAIL as a release blocker.
Do not auto-fix; present blockers and recommended remediation first.
```
