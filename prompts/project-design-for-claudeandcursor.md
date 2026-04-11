# AI-Assisted Project Design Guide (Tool-Agnostic)

## For any coding agent + any IDE

This guide is intentionally generic. It focuses on patterns that work across
stacks, repos, and agent tools.

---

## Philosophy

Treat documentation as executable coordination infrastructure:

1. **Docs are the source of truth** for architecture, contracts, and workflow.
2. **Agents are capable readers** when context is explicit and structured.
3. **Parallel work needs explicit coordination** (ownership, touch zones, claims).
4. **Small cohesive files improve agent quality** and reduce missed context.
5. **Verification gates must be explicit and non-optional**.

---

## The Five Layers

| Layer | Typical artifact(s) | Purpose |
|---|---|---|
| Entry point | `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md` | First-load repo contract for humans and agents |
| IDE/agent rule packs | IDE-specific rule files | Scoped conventions and safety rails |
| Source-of-truth docs | `docs/*.md` (or equivalent) | Architecture, contracts, workflow, operations |
| Session memory | Tool-specific memory/index files | Durable high-signal context across sessions |
| Verification | CI + local commands | Deterministic pass/fail gates |

If two layers conflict, the repository's canonical docs win.

---

## Part 1: Entry-point file

Use one root file as the first thing agents read (name is repo-specific).

### Keep this file compact

Keep it dense and link out to longer docs. Repeatedly loading a bloated entry
file lowers signal quality.

### Recommended sections

1. **Project identity**
   - One sentence: what this system does and for whom.
2. **Stack and toolchain**
   - Languages, frameworks, package managers, runtime versions.
   - Include non-obvious constraints (for example, "use `uv`, not `pip`").
3. **Repository structure map**
   - High-level directories and ownership.
4. **Workflow invariants**
   - Branching and claim/registration requirements.
   - Rules for scope control and cross-module changes.
5. **Code quality limits**
   - File/function limits, dead-code policy, abstraction boundaries.
6. **Code conventions**
   - Naming, typing, error handling, and style rules.
7. **Verification gates**
   - Exact commands or pointers to canonical commands doc.
8. **Doc map**
   - Where to find architecture, contracts, commands, workflow rules.

### Generic template snippet

```markdown
## Workflow Invariants

- Create a branch before implementation (never commit directly to protected branches).
- Follow the repository's active-work registration protocol, if defined.
- Stay inside declared touch zones unless scope is explicitly expanded.
- Run all required verification gates before commit.
```

---

## Part 2: IDE/agent rule packs

Rule files are optional but useful for scoped behavior.

### Recommended shape

- Keep project-wide safety rules in always-apply files.
- Keep language/framework rules scoped by file globs.
- Avoid duplicating canonical docs; link to them.

### Suggested rule groups

- `001-project-standards`: naming and module ownership basics.
- `002-code-quality`: hard limits and anti-patterns.
- `003-workflow`: pointer to branch/claim/merge protocol.
- `100+`: language-specific conventions.
- `200+`: backend/service conventions.
- `300+`: contract/testing/security integration rules.

Use numbering only as an ordering convention; exact filenames are repo-specific.

---

## Part 3: Source-of-truth docs

Every project should have canonical docs that define the contract between humans,
agents, and the codebase.

### Minimum recommended docs

- **Architecture doc**
  - Layer boundaries, allowed imports/dependencies, ownership map.
- **Contract doc**
  - API/data/file-format contracts and compatibility rules.
- **Commands doc**
  - Build/test/lint/typecheck/dev commands with exact invocation details.
- **Workflow doc**
  - Branch model, active-work registration, merge-closeout protocol.

### Optional but high leverage

- **Roadmap/work-tracking doc(s)** with touch zones and dependency fields.
- **Environment/hosting doc** for local/stage/prod differences.
- **Security policy doc** for secrets, logging, subprocess, and path safety.

---

## Part 4: Memory hygiene

If your agent tool supports persistent memory, use it for:

- Environment quirks discovered in practice
- Durable workflow references
- Stable external pointers

Do not store what the repo already documents clearly. Keep memory short and
validate any stale-looking memory against current files.

---

## Part 5: Generic coordination protocol

For multi-agent or parallel work, define and enforce:

1. **Branch naming rules** (roadmap-driven vs ad-hoc work).
2. **Active-work registration** (registry table/file or equivalent).
3. **Touch zones** (expected paths/globs per task).
4. **First-commit claim rule** (if used by the repo).
5. **Merge closeout** (deregister + update status artifacts).

Implementation details vary by repo; prompts should require "follow documented
workflow" rather than hardcoding a single system.

---

## Part 6: Verification gates

Require explicit, deterministic gates before commit:

1. Static analysis (lint + type checks)
2. Tests (targeted during iteration, full suite before merge)
3. Build/package/smoke/integration gate (if defined)

Use placeholders in prompts when commands differ by project:

- `[YOUR_STATIC_ANALYSIS_CMD]`
- `[YOUR_TEST_CMD]`
- `[YOUR_INTEGRATION_OR_SMOKE_CMD]`

---

## Part 7: Prompt discipline

Prompt quality remains critical even with good docs.

- Keep tasks atomic.
- Ask for a contract-first plan before implementation on larger changes.
- Require tests and gate checks.
- Require explicit stop points when docs are missing or ambiguous.

---

## Appendix A: New repository bootstrap checklist

- [ ] Create an entry-point file with workflow and quality invariants.
- [ ] Establish canonical docs for architecture/contracts/commands/workflow.
- [ ] Define branch + active-work coordination protocol.
- [ ] Define verification gates with exact commands.
- [ ] Add optional IDE/agent rule packs that point to canonical docs.
- [ ] Add optional memory index conventions (if tooling supports it).

---

## Appendix B: New work-item checklist

- [ ] Identify canonical docs and ownership boundaries first.
- [ ] Confirm no active-work overlap using the repo's tracking system.
- [ ] Define contract delta (or explicitly state none).
- [ ] Define tests from acceptance criteria.
- [ ] Implement in dependency order with smallest safe diff.
- [ ] Run all documented verification gates before commit.

