# Cleanup Prompts

Prompts for keeping the codebase lean, readable, and within the hard limits
set in project documentation.

---

## Docs-first usage (required)

Before using any prompt in this file:
- Read `docs/` to find the project’s hard limits (file/function size), verification gates, and source/test directory layout.
- Do **not** assume any specific doc filenames or toolchain.
- If `docs/` does not specify what you need, **stop and ask the user** to provide the missing inputs as placeholders:
  - `[YOUR_STATIC_ANALYSIS_CMD]`
  - `[YOUR_TEST_CMD]`
  - (optional) `[YOUR_DEAD_CODE_SCAN_CMD]` (only if `docs/` does not define how to scan unused code/imports)

---

## File & Function Size Enforcement

Purpose: Find and split any file or function that exceeds the hard limits in
project docs before they become harder to break apart.

```prompt
Scan the entire codebase for size violations against the limits documented in `docs/`.

If `docs/` does not specify size limits (max file lines, max function/method lines), stop and ask the user to provide them before continuing.

For each violation found, report:
- File path and current line count (for files)
- File path, function name, and current line count (for functions)
- A brief diagnosis: why is it large? (multiple responsibilities, complex
  algorithm, large data structure, generated code, etc.)
- A proposed split strategy: what logical units could it be divided into,
  and what would the new files/functions be named following project conventions
  (snake_case files, grouped by responsibility not by size)

Do not split anything automatically. Present the full list of violations
and proposed strategies first.

When asked to proceed on a specific file or function:
1. Read the file carefully to understand all dependencies and call sites
   before making any changes
2. Split following existing naming conventions (snake_case files; group by
   responsibility, not by size)
3. Ensure every import is updated — nothing should break
4. Do not change logic, rename public APIs, or alter behavior while splitting

Verification gates after each split:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```

---

## Documentation Hygiene

Purpose: Ensure non-obvious code is explained, while keeping documentation
lean — no comments that restate what the code already says clearly.

```prompt
Audit the codebase for documentation quality. The goal is the right amount
of documentation: enough to explain non-obvious intent, not so much that
comments become noise.

Add documentation where it is missing and genuinely needed:

- Docstrings on functions with non-trivial logic. A good docstring states what the function does, any important preconditions, and what it returns — not how it does it line by line.
- Inline comments on specific lines where the logic would surprise a
  competent reader (e.g. why a particular edge case is handled a certain
  way, why a default value is what it is, why a subprocess call uses a
  specific flag)
- Do NOT add docstrings to thin wrapper functions, simple Pydantic field
  definitions, or any function whose name and type signature already make
  its purpose clear

Remove documentation where it is stale or adds no value:
- Comments that simply restate what the code does
- Docstrings that are outdated and no longer match the function's behavior
- TODO/FIXME comments older than the current feature branch (move to
  issues or delete)
- Commented-out code blocks

Do not add documentation to files you are not already touching for a real
reason — this prompt is not a license to touch every file in the repo.
Focus on the highest-complexity areas first as identified by `docs/` (architecture/module map), and any file flagged during a recent code review.

After changes:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
```

---

## Dead Code Cleanup

Purpose: Remove unused code that adds noise and maintenance burden without
providing value.

```prompt
Scan the codebase for dead code and remove it. Dead code is code that exists
but can never be reached or is never used.

Check for:
- Unused imports across the source directories documented in `docs/`.
- Variables assigned but never read
- Functions or classes defined but never called or imported anywhere
- Unreachable branches (code after an unconditional return, conditions
  that can never be true given the types)
- Commented-out code blocks (remove; git history preserves the original)

For each item found, confirm it is genuinely unreachable or unused before
removing — check all import paths, including re-exports and dynamic imports.

Do not remove:
- Code that is unused today but is clearly scaffolding for an in-progress
  feature on this branch
- Code that may be active in parallel work if `docs/` defines a parallel-work tracking system (e.g., an “in progress” manifest). If `docs/` does not define such a system, stop and ask the user how to avoid deleting code used by other active branches.
- Test fixtures or helpers that appear unused in source but are used in
  the test suite (as documented in `docs/`)

If `docs/` does not specify how to scan dead code/unused imports, stop and ask the user for `[YOUR_DEAD_CODE_SCAN_CMD]`.

After removing dead code:
- Gate 1 — Static analysis:
  [YOUR_STATIC_ANALYSIS_CMD]
- Gate 2 — Tests:
  [YOUR_TEST_CMD]
```
