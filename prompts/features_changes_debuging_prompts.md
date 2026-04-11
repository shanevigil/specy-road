# Features, Changes, and Debugging Prompts

Prompts for running implementation sessions end-to-end while remaining
docs-driven and repository-agnostic.

---

## Docs-first usage (required)

Before using any prompt in this file:
- Read `docs/` (or the repository's canonical docs location) to identify
  workflow rules, ownership boundaries, contracts, and verification gates.
- Do **not** assume fixed doc filenames, branch names, or toolchains.
- If required info is missing, stop and ask the user for placeholders:
  - `[YOUR_STATIC_ANALYSIS_CMD]`
  - `[YOUR_TEST_CMD]`
  - (optional) `[YOUR_INTEGRATION_OR_SMOKE_CMD]`

---

## Debug Session Kickoff

Purpose: Diagnose and fix a reported bug from errors, logs, tracebacks, or a
reproduction report.

```prompt
I am reporting a bug. The relevant context is provided below this prompt
(error text and/or reproduction steps). Follow this process.

Step 0 — Confirm workflow (docs-driven)
Check whether project docs define:
- Branching and naming for fixes/features
- Active-work tracking / claim registration and closeout

If workflow rules are missing, stop and ask the user what workflow to follow.

Step 1 — Understand the failure
Use docs-defined ownership boundaries to identify the owning module/component.
Do not edit code until the owning area and likely failure file(s) are clear.

If ownership is undocumented, stop and ask the user for intended boundaries.

Step 2 — Trace call path
Trace from entry point to failure site using docs-defined architecture and
boundaries. Read each relevant file before proposing a root-cause hypothesis.

Step 3 — Reproduce and confirm
If root cause is not immediately obvious, define a minimal reproduction
scenario and confirm the hypothesis before fixing. Do not guess.

Step 4 — Fix
Apply the smallest change that resolves the failure. Avoid unrelated refactors
or opportunistic cleanup.

Step 5 — Regression test
Add the minimum regression test in the project's documented test framework.
If unit testing is not feasible, explain manual verification clearly.

Verification gates (all must pass before committing):
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```

---

## New Feature

Purpose: Implement a new feature end-to-end and update docs only where changes
actually alter the documented contract/workflow.

```prompt
I want to add a new feature. The feature description is below this prompt.
Follow this process.

Step 0 — Check active work
Read docs for overlap-avoidance and work tracking.
If defined, follow it exactly.
If not defined, stop and ask how to track/branch this work.

Step 1 — Understand baseline
Read architecture and contract docs (do not assume filenames). Identify
existing components to extend before introducing new abstractions.

Step 2 — Contract-first proposal (stop for confirmation)
Before writing code, propose:
1. Modules/components touched (per docs ownership map)
2. External contract/interface changes (APIs, schemas, file formats, flags)
3. Config changes (name, type, default, runtime source)
4. Boundary/import implications
5. Tests to write (file + test name + what each proves)

Present this proposal and wait for confirmation.

Step 3 — Implement in dependency order
Implement contracts/models before callers, configuration before dependent
paths, and tests aligned with project layout conventions.

Step 4 — Update docs only if needed
Update docs that are now outdated. For each doc edit, state why it is needed.
Do not make speculative doc edits.

Step 5 — Verify
Verification gates (all must pass before committing):
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
- Gate 3 — Integration / smoke tests (if applicable):
  [YOUR_INTEGRATION_OR_SMOKE_CMD]
```

---

## Complete a Scaffolded Feature

Purpose: Finish partially scaffolded functionality (stubbed code or doc-defined
but unimplemented behavior) using contract-first execution.

```prompt
I want to complete a scaffolded feature in this repository. Follow this process.

Step 0 — Confirm workflow
If docs define branch/work-tracking rules, follow them.
If not, stop and ask for branch + in-progress + closeout conventions.

Definition of “scaffolded”
- Stub functions (`NotImplementedError`, placeholder returns)
- Incomplete wiring or TODO/FIXME markers
- Doc-defined behavior not implemented in code

Step 1 — Inventory candidates (no coding yet)
Search for scaffold signals and report candidates with file/line references.
For each candidate report:
- Entry point
- What exists already
- What is missing to be done
- Risk (HIGH/MEDIUM/LOW)
- Recommendation: exactly one highest-leverage candidate

Scaffold signals to search for:
- `raise NotImplementedError`
- Placeholder returns in non-trivial paths (`return []`, `return {}`, etc.)
- `TODO` / `FIXME` markers
- Any repo-documented scaffold markers

Step 2 — Choose one and define done
Pick one candidate and define explicit acceptance criteria:
- Command/interaction that exercises it
- Expected output/behavior
- Validation proving correctness

Step 3 — Contract-first proposal (stop for confirmation)
Propose contract changes (if any), touched modules, and the de-scaffold plan.
Wait for confirmation before coding.

Step 4 — Implement with smallest safe diff
Implement in dependency order; remove scaffolding as behavior is completed.

Step 5 — Tests and verification
Add the minimum tests proving completion (unit + integration when needed).

Verification gates:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
- Gate 3 — End-to-end / smoke (if applicable):
  [YOUR_INTEGRATION_OR_SMOKE_CMD]

Closeout:
- Provide exact command(s)/steps to exercise the completed feature.
- List scaffolding artifacts removed/replaced.
```

---

## Implement Next Work Item

Purpose: Select and implement the next eligible work item from project tracking
with plan confirmation, tests-first execution, and explicit closeout.

```prompt
Implement the next work item defined by this repository's docs. Follow this
process.

PHASE 1 — IDENTIFY & PLAN (no code changes yet)

Step 0 — Check active work
Read in-progress tracking and touch zones/dependencies.
If missing, stop and ask how overlap should be prevented.

Step 1 — Select next eligible item
Use the docs-defined selection method and eligibility criteria.

Step 2 — Assess contract delta
List all required contract/interface changes, or state "none".

Step 3 — Assess architecture delta
List required boundary/import/data-flow changes, or state "none".

Step 4 — Design tests (describe only)
For each acceptance criterion, list test file, test name, and assertion intent.
If manual verification is needed, define it explicitly.

Step 5 — Stop for confirmation
Present:
- Work item
- Scope
- Contract delta
- Architecture delta
- Tests to be written
- Files expected to change

Wait for confirmation before writing code.

PHASE 2 — IMPLEMENT (after confirmation)

Step 6 — Workflow setup
Follow docs-defined branch/registration rules.

Step 7 — Docs first (only if planned deltas require it)
Apply needed architecture/contract doc updates before production code.

Step 8 — Tests before implementation
Write planned tests first (failing/skipped initially is fine).

Step 9 — Implement
Implement in dependency order consistent with ownership boundaries.

PHASE 3 — CLOSEOUT

Step 10 — Verification gates
- Gate 1:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2:
  [YOUR_TEST_CMD]
- Gate 3 (if documented):
  [YOUR_INTEGRATION_OR_SMOKE_CMD]

Step 11 — Architecture/compliance audit
Run the repository's compliance-review prompt/process (for example, the
Architecture & Compliance section in the local prompt set) and resolve
HIGH/MEDIUM issues. Re-run gates after fixes.

Step 12 — Work-item closeout
Follow the repo's documented closeout steps (status updates, deregistration,
tracker updates, or equivalent).
```
