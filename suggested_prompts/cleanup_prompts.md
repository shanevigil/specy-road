# Cleanup Prompts (Generic)

Prompts for keeping a codebase lean, maintainable, and aligned with its
documented quality constraints.

---

## Docs-first usage (required)

Before using any prompt in this file:
- Read `docs/` (or the canonical docs location) to identify size limits,
  verification gates, and source/test layout.
- Do **not** assume fixed filenames or toolchains.
- If required information is missing, stop and ask for placeholders:
  - `[YOUR_STATIC_ANALYSIS_CMD]`
  - `[YOUR_TEST_CMD]`
  - (optional) `[YOUR_DEAD_CODE_SCAN_CMD]`

---

## File & Function Size Enforcement

Purpose: Identify and split files/functions that exceed documented hard limits.

```prompt
Scan the codebase for size violations using limits defined in project docs.

If docs do not define size limits (max file lines, max function/method lines),
stop and ask the user to provide them before continuing.

For each violation, report:
- File path + current line count (file violations)
- File path + function/method name + line count (function violations)
- Why it is large (multiple responsibilities, algorithm complexity, generated
  content, etc.)
- Proposed split strategy with names that match project conventions

Do not split automatically. Present findings and plan first.

If asked to proceed on specific targets:
1. Read full dependency/call-site context first
2. Split by responsibility, not arbitrary line-count chunks
3. Update imports/callers so behavior remains unchanged
4. Avoid API/behavior changes while performing structural splits

After each applied split:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```

---

## Documentation Hygiene

Purpose: Keep documentation high-signal: explain non-obvious intent, remove
noise and stale commentary.

```prompt
Audit documentation quality in code touched by this session.

Add docs only where genuinely needed:
- Docstrings for non-trivial behavior (intent, preconditions, outputs)
- Inline comments for surprising constraints, edge-case rationale, or
  non-obvious safety behavior

Avoid adding docs where unnecessary:
- Thin wrappers with obvious behavior
- Trivial model/field declarations
- Functions whose name + signature already convey intent

Remove docs/comments that are stale or low-value:
- Comments that merely restate code
- Outdated docstrings
- Stale TODO/FIXME notes that should be moved to tracking artifacts
- Commented-out code blocks

Do not touch unrelated files just for comment churn.

After changes:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
```

---

## Dead Code Cleanup

Purpose: Remove unreachable or unused code safely.

```prompt
Scan for dead code and remove it with high confidence.

Check for:
- Unused imports
- Assigned-but-never-read variables
- Unused functions/classes (including stale exports)
- Unreachable branches
- Commented-out code blocks

Before removal, confirm code is truly unused:
- Check direct imports, re-exports, dynamic loading patterns, and tests.

Do not remove:
- Active scaffolding for in-progress tracked work
- Code likely in active parallel work (if repo defines in-progress tracking,
  use it; otherwise ask user how to avoid conflicts)
- Fixtures/helpers used by tests

If docs do not define dead-code scanning method, ask for:
- [YOUR_DEAD_CODE_SCAN_CMD]

After cleanup:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```
