# Optional agent review prompts

**Not part of specy-road’s core contract.** These are **copy-paste prompts** for humans or coding agents doing optional quality passes (architecture audit, scoped review, coverage gaps, dependencies, security, pre-release). Replace placeholders with commands from **your** repository’s `docs/` and CI config.

For workflow placement (CI vs session), see [dev-workflow.md](dev-workflow.md).

---

## Docs-first usage (required)

Before using any prompt below:

- Read `docs/` to find the project’s architecture/ownership rules, contracts, conventions, and verification gates.
- Do **not** assume specific doc filenames or a specific toolchain.
- If `docs/` does not specify what you need, **stop and ask** the user to provide the missing inputs as placeholders:
  - `[YOUR_STATIC_ANALYSIS_CMD]`
  - `[YOUR_TEST_CMD]`
  - (optional) `[YOUR_DEPENDENCY_INSTALL_CMD]` (only for dependency changes)
  - (optional) `[YOUR_SECURITY_SCAN_CMD]` (only for dependency/CVE scanning)

---

## Architecture and vision compliance

**Purpose:** Check the codebase for adherence to the project’s documented architecture.

```text
Review `docs/` for compliance against the actual codebase.

Do not assume specific filenames. Identify which documents define:
- Architecture and module ownership (including import boundaries)
- Data/API contracts (schemas, formats, invariants)
- Conventions and constraints (naming, style, tooling, security)
- Verification gates (static analysis, tests, other required checks)

If `docs/` does not clearly define the required rules (especially architecture/ownership/import rules and gates), stop and ask the user which doc(s) to use and/or to provide placeholders for the missing commands.

Audit scope:
1. Architecture and ownership rules (from `docs/`):
   - Extract the ownership/import rules documented in `docs/` and audit the code for violations.
   - If `docs/` does not define ownership/import rules, stop and ask the user to specify them before auditing.

2. Language/framework conventions (from `docs/`):
   - Audit for violations of conventions explicitly documented in `docs/`.
   - Do not enforce conventions that are not documented; if something seems important but undocumented, flag it as a docs gap.

3. Contract compliance (from `docs/`):
   - Identify the project’s contract surface (data schemas, API schemas, file formats, config contracts) as documented in `docs/`.
   - Audit the implementation against those contracts.

4. Roadmap hygiene:
   - Only if `docs/` defines a roadmap/work-tracking system: audit for staleness and internal consistency using the rules documented there.
   - If `docs/` does not define such a system, skip this section (do not invent one).

Before reporting a gap, verify it against the current file — don't report something as missing until you've confirmed it doesn't exist.

For each gap found, state:
- Severity (HIGH/MEDIUM/LOW)
- Fix target: code or docs
- Risk: what could break if changed

Verification gates (must ALL pass after changes are applied):
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]

When committing, stage only the files changed in this session. Do not include pre-existing uncommitted changes that were present before the audit began.
```

---

## Code review (scoped to changes)

**Purpose:** Review recently changed code for quality, correctness, and adherence to project conventions — not a full codebase scan.

```text
Review all the code changed in this session (or since the last commit).

Check for:
1. Correctness — logic bugs, off-by-one errors, unhandled edge cases, missing null/error guards at system boundaries (file I/O, subprocess calls, external API responses)
2. Code quality — excessive complexity, unclear responsibilities, dead code (unused imports/variables/unreachable branches), premature abstractions
3. Conventions — naming, types, error handling, logging, and any other rules documented in `docs/`
4. Architecture/ownership rules — ensure changed code respects the rules documented in `docs/` (ownership boundaries, allowed imports, layering if defined)
5. Security — ensure changed code respects security rules documented in `docs/` (subprocess safety if applicable, secret handling, logging constraints)

For each issue found, state the file and line number, the problem, and a concrete fix. Distinguish between must-fix (correctness/security) and should-fix (style/quality).

Do not suggest refactors or improvements to code that was not changed.
Do not add docstrings, comments, or tests unless directly related to a correctness issue found.

After applying fixes:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```

---

## Test coverage audit

**Purpose:** Identify gaps in test coverage and recommend targeted tests for the highest-risk untested paths.

```text
Audit the test suite (as documented in `docs/`) against the actual implementation to find coverage gaps.

If `docs/` defines a module map / architecture breakdown, use that to structure the audit (tests should mirror the project’s structure and risk profile). If `docs/` does not define the source/test layout, stop and ask the user for the intended scope directories before continuing.

For each gap found, state:
- What is untested
- Why it is risky (what failure mode it could mask)
- The minimum test that would provide meaningful coverage
- Whether it should be a unit test or integration test

Prioritise by risk using the project’s own critical-path definitions in `docs/` (correctness and security first, then the highest-impact stability and operability risks).

Do not write the tests yet — produce a prioritised gap report first.
If asked to proceed, write tests following existing patterns and confirm they pass with:
  [YOUR_TEST_CMD]
before committing.
```

---

## Dependency audit

**Purpose:** Identify outdated, vulnerable, unused, or incorrectly installed dependencies.

```text
Audit all project dependencies for staleness, risk, and hygiene.

First, identify the dependency manifest and tooling documented in `docs/` (examples: `pyproject.toml`, `requirements.txt`, `package.json`, `go.mod`, etc.).

If `docs/` does not define (a) the dependency manifest location(s), (b) the install/update procedure, and (c) the security scan process, stop and ask the user for:
- `[YOUR_DEPENDENCY_INSTALL_CMD]`
- `[YOUR_SECURITY_SCAN_CMD]`

Examine the dependency manifest(s):
1. List all production and dev dependencies with their current pinned versions
2. Flag any package with a known CVE or that is more than 2 major versions behind latest stable
3. Verify installs follow the dependency management process documented in `docs/` (package manager, lockfile policy, environment setup)
4. Identify any import in the source directories documented in `docs/` that is not declared in the dependency manifest (missing declaration)
5. Identify any declared dependency that is never imported anywhere in the source tree (unused)

Run `[YOUR_SECURITY_SCAN_CMD]` to check for known vulnerabilities.

For each issue, state the package, the problem (CVE / outdated / unused / undeclared), and the recommended action.

Do not upgrade packages automatically. Present findings first. If asked to upgrade, change only the version specifier(s) and run `[YOUR_DEPENDENCY_INSTALL_CMD]`, then verify with:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```

---

## Security audit

**Purpose:** Identify security vulnerabilities and hardening gaps.

```text
Perform a security audit of the codebase. Focus on realistic attack surfaces as documented in `docs/` (runtime environment, inputs/outputs, external services, subprocess usage, file I/O, and authentication/authorization boundaries if any).

Do not perform web searches unless `docs/` explicitly authorizes it for this workflow. If `docs/` is silent, keep the audit repo+docs driven.

If `docs/` does not define security expectations relevant to this project (e.g., subprocess policy, secrets policy, logging/redaction policy), stop and ask the user which policies to enforce.

Check the following areas (where applicable to this project):
1. Subprocess safety
   - Verify subprocess calls do not interpolate untrusted strings into shell commands (prefer list form; avoid `shell=True`).
   - Verify file paths derived from user input are validated/normalized against expected directories per rules documented in `docs/`.

2. Environment variable and config handling
   - Confirm environment variable access follows the rules documented in `docs/`.
   - Verify required secrets documented in `docs/` fail loudly (without leaking secret values) if missing.
   - Verify that no API key or secret value is passed to logging or printed.

3. Secrets hygiene
   - Scan for hardcoded API keys, tokens, or passwords in the source directories documented in `docs/`.
   - Confirm the secret-handling conventions documented in `docs/` are followed (gitignore policy, example env/config files, redaction policy).

4. File path safety
   - Confirm output directories are constructed under configured base paths; no user input can escape them.
   - Confirm file reads are restricted per rules documented in `docs/` (no arbitrary-path reads if not intended).

5. Dependency vulnerabilities
   - Run `[YOUR_SECURITY_SCAN_CMD]` and flag any CVEs found.

For each finding, state:
- Severity: CRITICAL / HIGH / MEDIUM / LOW
- File and line
- The attack vector and realistic impact
- Recommended fix

Do not modify any code without confirmation. Present findings first.
After applying fixes, verify:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```

---

## Pre-release checklist

**Purpose:** Gate check before cutting a release or promoting a branch. Run before any version tag or release merge.

```text
Run a pre-release readiness check. This is a gate — every item must pass before the release proceeds. Flag blockers vs. warnings.

If `docs/` does not define a release checklist and its required commands, stop and ask the user to provide them.

1. Static analysis and tests
   - Gate 1 — Static analysis:
     [YOUR_STATIC_ANALYSIS_CMD]
   - Gate 2 — Tests:
     [YOUR_TEST_CMD]

2. Release/integration gates
   - Run the release gates documented in `docs/` (integration smoke tests, validation commands, packaging/export steps, etc.).

3. Configuration and secrets
   - No hardcoded secrets or API keys anywhere in source.
   - Secret/config handling follows `docs/` (gitignore policy, example env/config files, startup error behavior).

4. Dead code and debug artifacts
   - No print() or debug statements left in production paths (as defined by `docs/`).
   - No TODO/FIXME comments in code that ships (move to issues or delete).
   - No commented-out code blocks.

5. Docs alignment
   - Contracts, architecture, and operational docs in `docs/` match the implementation.
   - If `docs/` defines a roadmap/work-tracking system, ensure it’s current and consistent.

Report each item as PASS, FAIL, or WARNING with details. Treat any FAIL as a release blocker. Do not apply fixes automatically — surface the failures and wait for direction.
```

---

## See also

- [dev-workflow.md](dev-workflow.md) — task loop, CI vs session review, post-merge work
- [optional-ai-tooling-patterns.md](optional-ai-tooling-patterns.md) — optional layering for agents
