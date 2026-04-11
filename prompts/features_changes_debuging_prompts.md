# Features, Changes & Debugging Prompts

Prompts for starting an agentic session to debug a problem or implement a new feature end-to-end — including updating project docs when the scope warrants it.

---

## Docs-first usage (required)

Before using any prompt in this file:
- Read `docs/` to find the project’s workflow expectations (branching, work tracking, release process), module ownership map, conventions, and verification gates.
- Do **not** assume any specific doc filenames or a specific toolchain.
- If `docs/` does not specify what you need, **stop and ask the user** to provide the missing inputs as placeholders:
  - `[YOUR_STATIC_ANALYSIS_CMD]`
  - `[YOUR_TEST_CMD]`

---

## Debug Session Kickoff

Purpose: Diagnose and fix a reported bug using error messages, tracebacks, or a description of unexpected behavior.

```prompt
I am reporting a bug. The relevant context is provided below this prompt (error text or reproduction steps). Work through the following process.

Step 0 — Confirm workflow (docs-driven)
Check whether `docs/` defines:
- How to branch and name branches for fixes/features
- Whether there is a work-tracking system and how to register in-progress work

If `docs/` does not define this workflow, stop and ask the user what workflow to follow for this fix.

Step 1 — Understand the failure
Read the error output and determine which module/component owns the failing behavior using the ownership/module map documented in `docs/`.

If `docs/` does not define module ownership, stop and ask the user for the intended ownership boundaries before proceeding.

Do not touch any file until you have identified the owning module/component and the specific file(s) responsible.

Step 2 — Trace the call path
Trace from the entry point down to the failure site. Use `docs/` to guide the intended call path and boundaries (entry points, public APIs, integration points).

Read every file in the path before forming a hypothesis.

Step 3 — Reproduce and confirm
If the bug is not immediately obvious from reading the code, describe a minimal reproduction scenario (inputs, command, sequence of steps) and confirm the hypothesis before writing a fix. Do not guess.

Step 4 — Fix
Apply the smallest change that corrects the failure. Do not refactor surrounding code, rename things, or make “while I’m here” improvements.

Step 5 — Add a regression test
Add a regression test in the project’s test suite (as documented in `docs/`) that would have caught this failure. Follow existing patterns.

If the bug cannot be reasonably unit tested, note the gap and describe how to verify manually.

Verification gates (all must pass before committing):
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```

---

## New Feature

Purpose: Implement a new feature end-to-end across whichever modules/components it touches. Includes deciding whether the feature warrants docs updates.

```prompt
I want to add a new feature. The description is provided below this prompt. Work through the following process.

Step 0 — Check active work (docs-driven)
Check whether `docs/` defines a work-tracking system and how to avoid overlapping work.

If `docs/` defines work tracking, follow it exactly.
If `docs/` does not define work tracking, stop and ask the user how they want to track and branch this work.

Step 1 — Understand the current state
Read the relevant architecture and contract documents in `docs/` (do not assume filenames). Also read any docs-defined conventions/constraints that must not be violated.

Identify whether existing components can be extended rather than replaced. Search for relevant existing code before proposing net-new abstractions.

Step 2 — Design the contract (stop for confirmation)
Before writing any implementation, produce a contract proposal:
1. Which modules/components are touched (as defined by `docs/`)?
2. New or changed external interfaces/contracts (data models/schemas, APIs, file formats, CLI flags, configuration).
3. New or changed config surface — name each new setting, its type, default, and how it is configured at runtime (env var, config file, flags), per `docs/`.
4. Which ownership/import rules apply (from `docs/`)? Flag any new cross-boundary dependencies.
5. Tests to be written — name each test (file + test name) and what it proves, based on the acceptance criteria.

Surface this contract and wait for confirmation before proceeding to implementation. A wrong contract is far more expensive to fix after code is written.

Step 3 — Implement in dependency order
Implement in dependency order based on the ownership/module map in `docs/`. Do not assume specific layer names or directories.

At minimum, ensure:
- Contracts/models are implemented before callers.
- Configuration is implemented before code paths that depend on it.
- Tests mirror the project structure as documented in `docs/`.

Step 4 — Update docs (only if warranted)
After implementation is complete, update the relevant documents in `docs/` if they are now out of date (commands, workflows, module ownership boundaries, contracts/schemas/config expectations).

Do not update docs speculatively; state why each doc needs updating before editing it.

Step 5 — Verify
Verification gates (all must pass before committing):
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
- Gate 3 — Integration / smoke tests (if applicable):
  Run the integration/validation/smoke-test gates documented in `docs/`.
  If `docs/` does not define them, stop and ask the user for the correct end-to-end commands.
```

---

## Complete a Scaffolded Feature

Purpose: Take a feature that is already partially scaffolded (stubs, placeholder implementations, doc-only entries) and finish it end-to-end — contract first, then implementation.

```prompt
I want to complete something that is already scaffolded in this repo (not a brand-new feature). Work through the following process.

Step 0 — Confirm workflow (docs-driven)
If `docs/` defines a work-tracking/roadmap system and branching protocol, follow it exactly.
If `docs/` does not define it, stop and ask the user what workflow to follow (branching, how to track “in progress”, and closeout).

Definition of “scaffolded”
- Code scaffolds: stub functions that return empty placeholder values or raise `NotImplementedError`, placeholder implementations with hardcoded outputs, incomplete wiring, or obvious TODO/FIXME markers.
- Doc-only scaffolds: items in `docs/` that describe behavior/contracts that are not yet implemented in code.

Step 1 — Inventory scaffolded candidates (do not code yet)
Search for scaffold signals and build a short list of candidates with file + line references and why each looks scaffolded.

Scaffold signals to search for:
- `raise NotImplementedError`
- `return []` or `return {}` in non-trivial code paths
- `# TODO` / `# FIXME`
- Any docs-defined scaffold markers (if documented)

For each candidate, report:
- Entry point (file + line)
- What exists already (contracts/models? business logic? integration wiring? tests?)
- What’s missing to be “done” (user-visible behavior + working output)
- Risk (HIGH/MEDIUM/LOW)
- Recommendation: pick ONE highest-leverage candidate to complete first

Step 2 — Choose one scaffold and define “done”
Pick exactly one candidate. Define explicit acceptance criteria:
- What command produces the deliverable?
- What does the output look like?
- What validation confirms it is correct?

Step 3 — Contract-first proposal (stop for confirmation)
Before implementing, propose the contract and wait for confirmation:
- Contract changes (if any): models/schemas, configuration, external interfaces, invariants
- Modules/components touched and ownership rules that apply (from `docs/`)
- De-scaffold plan: what stubs/placeholders will be removed/replaced

Do not write code until the contract is confirmed.

Step 4 — Implement end-to-end (smallest diff)
Implement in dependency order based on the module map/ownership rules in `docs/`. Remove scaffolding as you go (delete stubs, remove placeholder returns/raises).

Step 5 — Tests and verification
- Add the minimum tests that prove the scaffold is truly completed:
  - Unit tests for the completed function(s) — happy path + invalid input
  - Integration test if the feature spans multiple components

Verification gates (all must pass before committing):
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
- Gate 3 — End-to-end (as appropriate):
  Run the end-to-end commands documented in `docs/`. If `docs/` does not define them, stop and ask the user for the correct verification commands.

Closeout:
- Provide the exact command(s) to exercise the completed feature.
- List which scaffolding artifacts were removed/replaced and where.
```

---

## Implement Next Work Item

Purpose: Pick the next unimplemented item from the project’s work-tracking system (if defined in `docs/`) and implement it end-to-end — with contract + architecture + test planning (stop for confirmation), tests before production code, and a closeout sequence that leaves all gates green.

```prompt
Implement the next work item as defined in `docs/`. Work through the following process.

PHASE 1 — IDENTIFY & PLAN (do not write code yet)

Step 0 — Check active work and select with overlap awareness
If `docs/` defines an in-progress status view/manifest, read it and note all in-progress items and their touch zones.
If `docs/` does not define this, stop and ask the user how to avoid overlapping work.

Step 1 — Identify the next unimplemented item
Follow the selection process documented in `docs/` (roadmap/issue tracker conventions). Use the module map in `docs/` to decide where to look for implementations and tests.

Step 2 — Assess contract changes
List every change to the project’s contract surface this item requires (models/schemas, APIs, file formats, configuration).
If the item requires no contract changes, state that explicitly.

Step 3 — Assess architecture changes
Compare the item’s requirements against the architecture rules in `docs/`. Flag any deviation (new module boundaries, new import relationships, new data flows).
If no architecture changes are needed, say so.

Step 4 — Design the tests (describe, do not write yet)
For each acceptance criterion, name the test:
- Test file (mirroring project structure) and test function name
- What it asserts and what inputs it uses
- If no automated test is warranted for a step, describe the manual verification instead

Step 5 — Stop for confirmation
Present a summary:
  • Work item: <name>
  • Scope: <single session | phased>
  • Contract delta: <list or none>
  • Architecture delta: <list or none>
  • Tests to be written: <list>
  • Files that will change: <list>

Do not write implementation or test code until this plan is confirmed.

PHASE 2 — IMPLEMENT (after confirmation)

Step 6 — Workflow setup
Follow the git/workflow guidance documented in `docs/` (branch naming, registration, closeout). If `docs/` does not define it, stop and ask the user for the workflow before proceeding.

Step 7 — Update docs first (only if required by the plan)
Update `docs/` for confirmed architecture/contract changes before writing production code.

Step 8 — Write tests before production code
Write the tests identified in Step 4 first. They should fail or be skipped at this point — that is expected.

Step 9 — Implement
Implement in dependency order using the module ownership map in `docs/`.

PHASE 3 — CLOSEOUT (mandatory)

Step 10 — Verification gates
Run Gate 1:
  [YOUR_STATIC_ANALYSIS_CMD]
Run Gate 2:
  [YOUR_TEST_CMD]

Run any additional end-to-end gates documented in `docs/`. If `docs/` does not define them, stop and ask the user for the correct commands.

Step 11 — Architecture & Vision Compliance check
Run the full “Architecture & Vision Compliance” audit from `coding_prompts/compliance_prompts.md` and resolve all HIGH and MEDIUM gaps. Re-run verification gates after any fixes.

Step 12 — Close out the work item
If `docs/` defines how to close out work items (roadmap updates, issue resolution, status transitions), follow it exactly. If not documented, stop and ask the user.
```

