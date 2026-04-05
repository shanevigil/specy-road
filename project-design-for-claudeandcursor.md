# AI-Assisted Project Design Guide
## For Claude Code + Cursor (and compatible AI coding agents)

> **Reference implementation:** a React 19 + FastAPI full-stack app developed entirely with AI assistance. Every pattern in this guide was battle-tested there first.

---

## Philosophy

This guide is built on one core insight: **documentation is code**. When you treat your rules, architecture decisions, and conventions as first-class artifacts — formally written, cross-referenced, and version-controlled — AI agents can read them the same way a new senior engineer would. The result is dramatically fewer misunderstandings, less rework, and a codebase that stays coherent as it grows.

The five principles that follow from this:

1. **Docs are the source of truth.** Not comments. Not chat history. Not verbal agreements. If a rule matters, it lives in a file the agent can read.
2. **Design for AI agents as capable readers.** Write documentation with the assumption that a skilled agent will read it carefully and follow it. Agents are not dumb — they just need explicit context.
3. **Multi-agent coordination is designed in from day one.** Touch zones, codenames, and registration discipline prevent conflicts before they happen.
4. **Small, cohesive files are not a style preference — they are infrastructure.** Files under 400 lines and functions under 50 lines are small enough for agents to read in full, reason about completely, and modify safely. This is a direct enabler of AI quality.
5. **Rules must be non-negotiable to be useful.** Code quality rules that are "guidelines" get ignored by agents. Make them hard limits with a reason.

---

## The Five Layers

A well-configured AI-assisted project has five layers:

| Layer | File(s) | Purpose |
|---|---|---|
| **Entry point** | `CLAUDE.md` | Primary contract — stack, structure, workflow rules, code quality |
| **IDE rules** | `.cursor/rules/NNN-name.mdc` | Layer-specific guidelines for Cursor/Copilot |
| **Specifications** | `docs/*.md` | Authoritative specs for architecture, API, git, commands |
| **Memory** | `~/.claude/projects/<slug>/memory/` | AI session state that persists across conversations |
| **Verification** | CI scripts / docker / test commands | Pass/fail gates that cannot be negotiated |

All five layers must be consistent. When they conflict, **docs win** — they are the canonical source.

---

## Part 1: CLAUDE.md — The Entry Point

### What it is

`CLAUDE.md` is the first file Claude Code reads when it opens a project. It is the primary contract between you and the agent. Every session starts by loading this file into context.

**Placement:** repo root. Always checked in. Never gitignored.

**Size:** keep it dense. Every line is reprocessed on every agent message. Research shows context windows should stay at 40-60% utilization — a bloated CLAUDE.md wastes that budget. If a section gets long, move it to `docs/` and reference it with `@docs/<name>.md`.

### Required Sections

#### 1. Project identity (2-3 lines)

```markdown
# my-project

One sentence describing what this project does and for whom.
```

#### 2. Tech stack

List every major technology the agent will touch. Be specific about versions and package managers — agents make wrong assumptions when these are unspecified.

```markdown
## Tech Stack

- **Frontend**: React 19, TypeScript (strict), Vite, React Query, react-hook-form, Zod
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, pydantic-settings
- **Package managers**: `pnpm` (frontend), `uv` (backend) — never npm/yarn/pip directly
- **Database**: PostgreSQL (prod), SQLite (local dev)
- **Container**: Docker + Docker Compose
```

Document non-obvious package manager constraints explicitly. "Never npm/pip directly" has saved dozens of wrong-tool calls.

#### 3. Project structure tree

Show the directory layout with a one-line comment on each directory's purpose. This tells the agent where to look for things without reading every file.

```markdown
## Project Structure

my-project/
├── frontend/
│   └── src/
│       ├── components/   # Shared UI components
│       ├── pages/        # Route-level page components
│       ├── hooks/        # Custom React hooks
│       ├── services/     # API client and service functions
│       ├── types/        # TypeScript types mirroring backend schemas
│       └── utils/        # Pure utility functions
├── backend/
│   └── app/
│       ├── routers/      # Route handlers (thin — call services, return responses)
│       ├── schemas/      # Pydantic request/response models
│       ├── models/       # DB/ORM models
│       ├── services/     # Business logic (no HTTP concerns)
│       └── main.py       # App factory
└── docs/                 # Architecture, API contract, commands, roadmap
```

#### 4. Workflow rules

Hard rules the agent must follow on every task, not just when asked:

```markdown
## Workflow Rules

- **Always create a branch before making changes** — never commit directly to `dev`, `staging`, or `main`
- Branch naming: `feature/<name>`, `fix/<name>`, `refactor/<name>`
- Roadmap item branches: `feature/rm-<codename>` — see @docs/git-workflow.md
- When changing a backend schema, always update the corresponding frontend type in the same commit
- Run all verification gates before committing — see @docs/commands.md
```

#### 5. Multi-agent roadmap workflow (one line + pointer)

```markdown
## Multi-Agent Roadmap Workflow

See @docs/git-workflow.md for the complete protocol: branch naming, registration discipline,
merge-back rules, and touch zone requirements.
```

#### 6. Code quality — non-negotiable

These must be hard limits, not guidelines. The reason behind each rule matters — include it so agents understand the constraint and don't route around it.

```markdown
## Code Quality (Non-Negotiable)

- **No file exceeds 400 lines.** Modularize before adding more code to a file at the limit.
  (Reason: files this size fit in an agent's reasoning window completely. Larger files cause partial reads and missed context.)
- **No function exceeds 50 lines.** If it does, it has more than one job.
- **DRY**: search for existing implementations before writing new code. If logic exists in 3+ places, extract it now.
- **YAGNI**: do not add code, fallbacks, or abstractions for scenarios not in the current task.
- **No flag parameters** — `doThing(mode='fast')` is two functions.
- **No dead code** — unused imports, variables, and unreachable branches are deleted before committing.
- Do not modify files outside the stated task scope without asking first.
```

#### 7. Code conventions

Language-specific rules. Be explicit about naming, type safety, and library-specific version constraints agents commonly get wrong:

```markdown
## Code Conventions

- Python: `snake_case` for files/functions/vars, `PascalCase` for classes
- TypeScript: `kebab-case` for files, `PascalCase` for components/types, `camelCase` for functions/hooks
- Booleans: `isLoading`, `hasError`, `canSubmit` — always prefixed with `is/has/can/should`
- No `any` in TypeScript — use `unknown` and narrow it
- No `# type: ignore` or `@ts-ignore` without an explanatory comment
- Pydantic v2 only: `.model_dump()` not `.dict()`, `.model_validate()` not `.from_orm()`
```

The Pydantic v2 rule is a real example of where agents default to the wrong API. Name the specific wrong calls to block.

#### 8. Docs references

End CLAUDE.md with a table that maps each doc to its purpose. Use `@docs/` syntax so Claude Code loads them on reference:

```markdown
## Docs (source of truth — read before implementing)

- Architecture and layer rules: @docs/architecture.md
- API contract, type mapping, endpoint registry: @docs/api-contract.md
- Dev commands and verification gates: @docs/commands.md
- Environment tiers (local/stage/prod): @docs/hosting.md
- Feature roadmap and production path: @docs/roadmap.md
- Git workflow, branch hierarchy, and multi-agent coordination: @docs/git-workflow.md
```

---

## Part 2: Cursor Rules — `.cursor/rules/`

### What they are

Cursor rule files (`.mdc`) give Cursor's AI persistent, scoped instructions beyond what fits in CLAUDE.md. They complement Claude Code — the rules load automatically based on which files are open.

**Path:** `.cursor/rules/NNN-name.mdc`
**Naming:** 3-digit prefix for ordering and grouping. Lower numbers = higher priority / broader scope.

### File format

```yaml
---
description: One-sentence purpose (shown in Cursor's rules panel)
globs:
  - "src/**/*.ts"
  - "src/**/*.tsx"
alwaysApply: false
---

# Rule content here (markdown)
```

Use `alwaysApply: true` for project-wide rules (naming, quality limits). Use `globs` for layer-specific rules (backend rules only apply to `app/**/*.py`).

### Recommended rule set

#### 000s — Always-apply project standards

**`001-project-standards.mdc`** (`alwaysApply: true`)

- Naming conventions table (file naming, class naming, function naming, boolean naming)
- Layer rules: which directories can import from which (services call API, components don't)
- Type mirroring requirement: backend schema changes require frontend type updates in the same commit

**`002-code-quality.mdc`** (`alwaysApply: true`)

The most important rule file. Include:

- Hard file/function size limits (400/50)
- DRY/YAGNI/Orthogonality/Broken Windows principles — name each
- AI-specific scope rules:
  - "Do not modify files outside the stated task scope without asking first"
  - "Do not refactor surrounding code unless it is required by the task"
  - "Do not add docstrings, comments, or type annotations to code you didn't change"
  - "State which files will change before modifying more than 2 files"
  - "Ask if a fix requires touching more than 5 files"

The last two points are critical. They prevent agents from going wide without warning.

**`003-multi-agent-workflow.mdc`** (`alwaysApply: true`)

Thin pointer: "See `docs/git-workflow.md` for branch naming, registration discipline, and merge-back rules."

Don't duplicate the workflow — just point to the canonical doc.

#### 100s — Frontend

**`100-typescript-frontend.mdc`** (globs: `src/**/*.ts`, `src/**/*.tsx`)

- TypeScript strict mode always on
- Absolute imports from `src/` (`@/` alias if configured)
- No `any` — use `unknown` and narrow
- Error handling: never swallow errors silently
- State management: `useState` for local, React Query for server state, Context/Zustand for global
- Environment variables: typed config module only — never inline `import.meta.env` in components
- Export pattern: named exports, one component per file

**`101-react-components.mdc`** (globs: `src/components/**/*.tsx`, `src/pages/**/*.tsx`)

- Functional components only
- Props interface defined above the component, named `<ComponentName>Props`
- Custom hooks extraction: extract when a hook is used in 2+ components
- React Query: constant query key factories exported from service files, not inlined
- Form validation: Zod schema + react-hook-form only; no manual validation logic

**`102-api-services.mdc`** (globs: `src/services/**/*.ts`)

- One service file per resource (`project-service.ts`, `beat-service.ts`)
- Every service file exports: query key factory + typed async functions
- All fetch calls go through `apiClient` only — no bare `fetch` in services
- Return types must match Pydantic response schemas exactly
- Use `ApiError` class (custom Error subclass with `status` and `message`) for error handling

#### 200s — Backend

**`200-fastapi-backend.mdc`** (globs: `app/**/*.py`)

- Router files: thin — validate input, call service, handle domain exceptions → HTTPException, return response schema
- Service files: business logic only — no FastAPI imports, no HTTPException
- Dependency injection: `Depends()` only — never instantiate services directly in route handlers
- Configuration: pydantic-settings `BaseSettings` only — never `os.environ` directly
- Async: all I/O operations must be `async` — no blocking calls in route handlers
- Error handling: services raise domain exceptions; routers map to HTTPException; global handler returns safe 500

**`201-pydantic-schemas.mdc`** (globs: `app/schemas/**/*.py`)

- Pydantic v2 only: `.model_dump()`, `.model_validate()`, `.model_dump_json()`
- Schema ordering within a file: `Base` → `Create*Request` → `Update*Request` → `*Response` → `*ListResponse`
- `ConfigDict(from_attributes=True)` on all Response models
- `Field(...)` with validation for required fields
- No password hashes or internal IDs in Response models

#### 300s — Integration

**`300-api-contract.mdc`** (`alwaysApply: true`)

This is the hardest constraint in the whole system and must be stated in both this rule file AND `docs/api-contract.md`:

> "Every Pydantic schema change requires a TypeScript type update in the same commit. No exceptions."

Include the full Python → TypeScript type mapping table:

| Python / Pydantic | TypeScript |
|---|---|
| `str` | `string` |
| `int`, `float` | `number` |
| `bool` | `boolean` |
| `UUID` | `string` |
| `datetime` | `string` (ISO 8601) |
| `list[T]` | `T[]` |
| `T \| None` | `T \| null` |
| `dict[str, T]` | `Record<string, T>` |
| `Literal["a", "b"]` | `"a" \| "b"` |
| Pydantic model | `interface` |

**`301-testing.mdc`** (`alwaysApply: true`)

- Backend: pytest + pytest-asyncio; `httpx.AsyncClient` for integration tests
- Test file location mirrors source: `app/routers/users.py` → `tests/routers/test_users.py`
- Test data: factory functions, not inline dicts
- Frontend: Vitest + React Testing Library; MSW for API mocking
- TDD principle: write test skeletons before asking the agent to implement — AI-generated code produces 1.7x more issues per PR than human code; a failing test is the best guardrail

**`302-auth.mdc`** (globs: `app/**/*.py`, `src/**/*.ts`)

- JWT bearer tokens; secret in settings (never hardcoded)
- `get_current_user` dependency on every protected route
- Frontend: store access token in memory (not localStorage); refresh token in httpOnly cookie
- `apiClient` attaches via `getAuthHeaders()` — no manual header setting in components
- 401 response → attempt refresh → on failure, redirect to `/login`

---

## Part 3: `docs/` — Source-of-Truth Specifications

### Why docs and not inline comments

Comments live next to the code they describe and go stale with it. Architectural decisions, API contracts, and workflow rules are cross-cutting — they affect dozens of files. Centralizing them in `docs/` means one place to update and one place for agents to read.

Agents learn the habit: **before implementing, read the relevant doc**. This is enforced by pointing to docs from CLAUDE.md and Cursor rules rather than embedding the content.

### Required for every project

#### `docs/architecture.md`

Define the layer rules explicitly. What can import from what. What each layer is responsible for. Agents will violate layering if it isn't written down.

Minimum sections:
- Backend layer diagram (Router → Service → Model/DB) with enforced rules
- Frontend layer diagram (Page → Component → Service) with enforced rules
- Error handling strategy (where exceptions are raised, where they're caught, what escapes to the client)
- Data fetching strategy (server state vs. UI state vs. global state)
- Configuration management (how env vars are accessed — always through a typed config module)

#### `docs/api-contract.md`

The schema registry. Contains:
- Python → TypeScript type mapping table (canonical reference)
- Backend schema naming convention (`<Resource>Base`, `Create<Resource>Request`, `Update<Resource>Request`, `<Resource>Response`, `<Resource>ListResponse`)
- Frontend type naming convention (mirrors backend)
- Standard response envelopes (paginated list shape, error shape)
- **The full endpoint table** — every route with method, path, request shape, response shape, and status codes
- Checklist for adding/changing an endpoint (8 items: schema, type, service function, query keys, router handler, service method, tests, `response_model=`)

The endpoint table is the single most valuable artifact for multi-session work. Agents consult it to know what exists before building duplicate routes.

#### `docs/commands.md`

Every dev command the agent will ever run. Group by:
- Running the app (local, with different DB profiles)
- Frontend dev tools (typecheck, lint, test, build) — with exact paths when package managers aren't on PATH
- Backend dev tools (test, typecheck, lint, dependency sync)
- Verification gates (the three mandatory pre-commit checks)

Document environment quirks explicitly. Example: if `pnpm` is not on PATH and agents must use `node_modules/.bin/tsc`, write that down. This single note prevents dozens of wrong command attempts.

#### `docs/git-workflow.md`

The full branching protocol. Sections:

**Branch hierarchy:**
```
main        ← tagged releases only
  └── staging   ← integration; merging triggers deploy
        └── dev     ← daily development trunk
              └── feature/rm-<codename>   ← roadmap items
              └── fix/<name>              ← bug fixes
              └── feature/<name>          ← non-roadmap features
```

**Merge flow:** all feature/fix branches → `dev` → `staging` → `main`

**Tagging convention:** semver on `main` only

| Tag | When |
|---|---|
| `v0.x.0` | Roadmap phase or feature milestone |
| `v0.x.y` | Bug/security patch within a milestone |
| `v1.0.0` | First public release |

**Multi-agent roadmap workflow** — this is the most important section for AI-assisted development:

1. Every roadmap item must have a `[codename: short-kebab-name]` tag on its heading
2. Every roadmap item must have a `**Touch zones:** <paths/globs>` line immediately after
3. Before starting any item, read `docs/roadmap-status.md` — check for overlap with in-progress touch zones
4. **First commit** on every `feature/rm-<codename>` branch: add entry to `docs/roadmap-status.md`
5. Commit message: `chore(rm-<codename>): register as in-progress`
6. No implementation code before this registration commit
7. Remove the entry from `docs/roadmap-status.md` before merging back

The registration discipline is what makes parallel agents safe. Without it, two agents editing the same files will produce merge conflicts with no way to trace responsibility.

### Recommended docs

#### `docs/roadmap.md`

Every planned feature, bug fix, and improvement. Each item follows this format:

```markdown
### Feature name `[codename: feature-name]`

**Touch zones:** `src/components/foo/`, `backend/app/services/bar.py`

**Problem:** What is broken or missing.

**Fix:** What to build. Be specific enough that an agent can implement it without asking clarifying questions.

**Implementation notes:** Any non-obvious constraints, existing functions to reuse, or things NOT to do.
```

The codename must be unique across all items. It becomes the branch name (`feature/rm-<codename>`) and the registration key in `roadmap-status.md`.

#### `docs/roadmap-status.md`

A simple table tracking what is currently in progress:

```markdown
| Codename | Branch | Item | Touch Zones | Started |
|---|---|---|---|---|
| char-edit | feature/rm-char-edit | Character name editing | `frontend/src/components/characters/` | 2026-03-01 |
```

Empty when no work is in progress. Updated by the agent on its first commit; cleaned up before merge.

#### `docs/hosting.md`

The environment tier definitions:

- **Local** — Docker Desktop, SQLite by default, dev tools via container
- **Stage** — VPS or PaaS (Hetzner, Fly.io, Render, DigitalOcean), Postgres, same Docker image as local
- **Production** — serverless containers (Cloud Run, Fargate, Container Apps) or dedicated server; managed Postgres, object storage for uploads

Document which `docker-compose` files correspond to which tier, and what environment variables differ between them.

### Optional / project-specific docs

For any domain with complex geometric or layout invariants (e.g., a pixel-perfect chart that must align with CSS layout), write a geometry contract doc that defines:
- CSS custom properties (source of truth)
- The TypeScript constants that mirror them
- A checklist of what to verify when either changes

This pattern applies broadly: any time two systems (CSS ↔ TS, backend ↔ frontend types) must stay in sync, write a contract doc that names both sides and the sync rule.

---

## Part 4: Claude Code Memory System

### How it works

Claude Code persists per-project memory in:
```
~/.claude/projects/<project-slug>/memory/
```

The slug is derived from the project path (slashes become hyphens).

Every session, Claude Code loads `MEMORY.md` from this directory. That file is a pointer index — each line references a memory file. The index is kept to 200 lines maximum; lines after that are truncated.

### MEMORY.md format

```markdown
# Memory Index

## Feedback
- [title](file.md) — one-line hook describing when to apply this

## Project
- [title](file.md) — one-line hook describing what this tracks

## Reference
- [title](file.md) — one-line hook describing what's stored here
```

Each entry is one line, under ~150 characters. The index is a navigation tool — memory content lives in the referenced files.

### Memory file format

```markdown
---
name: Short descriptive name
description: One-line — used to decide relevance in future conversations
type: feedback | user | project | reference
---

Memory content here.

**Why:** The reason this was saved (for feedback/project types).
**How to apply:** When and where this guidance kicks in.
```

The `Why` and `How to apply` lines make feedback memories usable in edge cases — you can judge whether the rule applies rather than blindly following it.

### Three tiers of memory (map to Claude Code's four types)

**Procedural (type: `feedback`)** — how-to knowledge that persists across sessions:
- Dev environment quirks (package managers not on PATH, commands that only work in Docker)
- Verified patterns that worked ("bundled PR was right here, not split")
- Anti-patterns to avoid ("don't mock the database — we got burned")

**Episodic (type: `project`)** — what happened and current state:
- Roadmap state: ordered list of next items to implement (update each session)
- Git workflow structure: branch hierarchy, where the spec lives
- Recent decisions: why a particular approach was chosen over alternatives

**Semantic (type: `reference`)** — stable facts and pointers:
- Where things live in external systems (Linear project for bugs, Grafana dashboard for latency)
- Key architectural decisions that aren't obvious from reading the code

### What to seed on day 1

After your first session, create these three memory files:

1. **`feedback_dev_environment.md`** — capture any package manager quirks, commands that need special invocation, or environment gotchas discovered during setup
2. **`project_git_workflow.md`** — branch hierarchy, where `docs/git-workflow.md` lives, tagging convention
3. **`project_roadmap_state.md`** — ordered list of the first 10 planned items, highest priority first

Update `project_roadmap_state.md` at the end of every session that completes or adds items.

### What NOT to store in memory

- Code patterns, conventions, file paths — derivable by reading the project
- Git history, recent commits — `git log` is authoritative
- Debugging solutions or fix recipes — the fix is in the code; the commit message has context
- Anything already in CLAUDE.md or docs/
- Ephemeral task details or in-progress state

Memory is expensive (it's re-loaded every session) and goes stale. Keep it lean and high-signal.

### Memory maintenance

Before acting on a memory that names a specific function, file, or flag:
- If it names a file path: verify the file exists
- If it names a function or flag: grep for it
- If the memory conflicts with what you observe in the code: trust the code, update the memory

---

## Part 5: Git Workflow Contract

### The three-branch hierarchy

```
main        ← tagged releases; never commit directly
  └── staging   ← integration; merging deploys to staging environment
        └── dev     ← daily development trunk; all feature/fix branches land here
```

Never commit directly to `staging` or `main`. All work starts on a branch cut from `dev`.

### Branch naming

| Type | Pattern | Example |
|---|---|---|
| Roadmap item | `feature/rm-<codename>` | `feature/rm-char-edit` |
| Bug fix | `fix/<name>` | `fix/scroll-runaway` |
| Non-roadmap feature | `feature/<name>` | `feature/export-pdf` |
| Refactor | `refactor/<name>` | `refactor/beat-service` |

### Roadmap item codename convention

Every item in `docs/roadmap.md` must have:

1. A `[codename: xxx]` tag in the heading (1-3 words, kebab-case, unique across all items)
2. A `**Touch zones:** <paths/globs>` line immediately after the heading

The codename becomes:
- The branch name (`feature/rm-<codename>`)
- The registration key in `docs/roadmap-status.md`
- The commit message prefix (`chore(rm-<codename>)`)

### Registration discipline (first-commit rule)

The **first commit** on every `feature/rm-<codename>` branch must add an entry to `docs/roadmap-status.md`.

Commit message: `chore(rm-<codename>): register as in-progress`

No implementation code before this commit. This discipline:
- Makes in-progress work visible to other agents
- Creates a clear "work started" marker in git history
- Enables overlap detection before conflicts happen

### Merge-back protocol

1. Remove entry from `docs/roadmap-status.md` before merging
2. Merge into `dev` (not `staging` or `main`)
3. Resolve `docs/roadmap.md` conflicts: keep your completed item removed AND keep all remaining items intact
4. Resolve `docs/roadmap-status.md` conflicts: remove your entry, keep all others
5. Delete the feature branch after merge: `git branch -d feature/rm-<codename> && git push origin --delete feature/rm-<codename>`

---

## Part 6: Verification Gates

Every project must have three mandatory verification gates that all pass before any commit:

### Gate 1 — Static analysis (typecheck + lint)

```bash
# TypeScript example
node_modules/.bin/tsc --noEmit && node_modules/.bin/eslint src/

# Python example
uv run mypy app/ && uv run ruff check app/
```

### Gate 2 — Tests

```bash
# Frontend
node_modules/.bin/vitest run

# Backend
docker compose exec backend uv run pytest
```

**Key principle:** gates must be fast and produce clear pass/fail output. Slow gates cause agents to skip them or get stuck in retry loops. If a full test run is slow, run the single relevant test file during iteration; run the full suite before committing.

### Gate 3 — Build / container

```bash
docker compose up -d --build
```

This gate catches integration issues that static analysis and unit tests miss (container config, env vars, port bindings). It runs last and must pass before any commit lands in `dev`.

Document all three gates explicitly in `docs/commands.md`. Agents treat documented gates as mandatory; undocumented gates get skipped.

---

## Part 7: MCP Servers (Model Context Protocol)

MCP servers give AI agents structured tool calls for external systems — Docker, GitHub, databases, filesystem — rather than requiring bash commands. Structured tool calls are safer (scoped permissions), more reliable (typed inputs/outputs), and produce cleaner agent reasoning.

### Recommended MCP servers

| Server | Purpose | When to add |
|---|---|---|
| **Docker MCP** | Container + Compose management: build, start/stop, logs, compose orchestration | Any project using Docker Compose |
| **GitHub MCP** | PR/issue creation, CI status, code review — without leaving the agent session | Any project on GitHub |
| **Git MCP** | Fine-grained git ops (log, diff, branch, tag) as structured tools | Any project with complex git workflows |
| **PostgreSQL MCP** | Direct DB queries from agent sessions | When Postgres is in the stack |
| **Filesystem MCP** | Large file operations (built into Claude Code — no setup needed) | Always available |

Docker hosts 300+ signed, containerized MCP servers at hub.docker.com/mcp.

### Adding MCP servers to Claude Code

Add to `.claude/settings.json` in the project root:

```json
{
  "mcpServers": {
    "docker": {
      "command": "docker",
      "args": ["mcp", "gateway", "run", "docker/docker-mcp-server"]
    },
    "github": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"]
    }
  }
}
```

### Docker MCP for verification gates

If your verification gates are Docker Compose commands, the Docker MCP server lets agents invoke them as structured tool calls rather than bare bash. This means:
- Scoped permission (agent can run compose commands without full shell access)
- Cleaner reasoning (tool call result vs. stdout parsing)
- Automatic log capture for debugging failed builds

---

## Part 8: Parallel Agents with Git Worktrees

When multiple agents work simultaneously on separate roadmap items, git worktrees give each agent true file isolation — not just separate branches, but separate working directory copies.

### How it works

```bash
# Agent A working on feature-auth in its own worktree
claude --worktree feature-auth

# Agent B working on feature-search simultaneously
claude --worktree feature-search
```

Each worktree:
- Creates an isolated branch (`worktree-feature-auth`)
- Gets its own copy of working files at `.claude/worktrees/<name>/`
- Shares git history with the main working tree
- Is automatically cleaned up if the agent makes no changes

### Why this matters

Without worktrees, two agents editing `src/auth.ts` simultaneously will produce merge conflicts. With worktrees, Agent A and Agent B each have their own `src/auth.ts` and changes are reconciled at merge time when you have full context.

### Pairing with the codename system

The codename + touch zones system defines the intent ("what this agent will touch"). Worktrees provide the mechanism ("give this agent its own copy of those files"). Together they enable safe parallel development:

1. Each roadmap item has a codename and touch zones (intent)
2. Each agent works in its own worktree (isolation)
3. Registration in `docs/roadmap-status.md` makes work visible (coordination)

### When to use worktrees vs. sequential work

Use worktrees when:
- Two items have non-overlapping touch zones (safe parallel work by definition)
- You want to compare two approaches to the same problem
- One agent is doing backend work while another does frontend

Work sequentially when:
- Touch zones overlap significantly
- The second item depends on the first (use worktrees only after merge)

---

## Part 9: Prompt Discipline

Even with perfect project configuration, the quality of individual prompts matters. These patterns consistently improve output:

### Atomic tasks

Frame every request as a single, well-scoped task you already understand deeply. "Implement the whole auth system" produces worse output than "Add the `get_current_user` FastAPI dependency that validates a JWT against `settings.jwt_secret`."

The codename + touch zones system enforces this at the roadmap level. Apply the same discipline to in-session requests.

### Use "think" for complex decisions

The word "think" in a prompt explicitly triggers extended reasoning in Claude models — more computation time evaluating alternatives before responding. Use it for:

- Architectural decisions with significant trade-offs
- Complex refactors with many affected files
- Planning sessions where you want the agent to consider alternatives before proposing one

Example: *"Think carefully about how the undo stack should coordinate with TipTap's internal history before proposing an approach."*

### Context utilization target: 40-60%

Even with 200k+ token context windows, indiscriminately loading context degrades output quality. The goal is curated, relevant context — not maximum context.

Practical implications:
- CLAUDE.md should stay dense and pruned (every line costs something)
- Don't paste entire files into chat when a snippet is sufficient
- Docs are loaded on reference (`@docs/name.md`) — only the relevant ones

### Write tests before asking agents to implement

AI-generated code produces approximately 1.7x more issues per PR than human-authored code (measured across 470 real PRs). The most common gaps: null checks, early returns, exception handling at boundaries.

Writing test skeletons first:
1. Forces you to think through the edge cases before the agent does
2. Gives the agent a concrete specification to implement against
3. Catches the specific issues AI code tends to miss

This is the highest-leverage testing practice for AI-assisted development.

---

## Appendix A: New Project Bootstrap Checklist

Use this checklist when starting a new project. Complete in order — later items depend on earlier ones.

### Day 0 — Repository setup

- [ ] Create repo with `main`, `staging`, `dev` branches
- [ ] Configure branch protection: require PR to merge to `staging` and `main`
- [ ] Create initial commit on `dev` with project structure

### Day 1 — AI configuration

- [ ] Write `CLAUDE.md` (all 8 sections above)
- [ ] Create `.cursor/rules/` directory
- [ ] Write `001-project-standards.mdc` (always-apply)
- [ ] Write `002-code-quality.mdc` (always-apply, include AI scope rules)
- [ ] Write `003-multi-agent-workflow.mdc` (pointer to git-workflow.md)
- [ ] Write stack-specific rules (100s for frontend, 200s for backend, 300s for integration)

### Day 1 — Docs

- [ ] Write `docs/architecture.md` (layer rules, import rules, error handling)
- [ ] Write `docs/api-contract.md` (type mapping, schema naming, initial endpoint table)
- [ ] Write `docs/commands.md` (all dev commands, all verification gates)
- [ ] Write `docs/git-workflow.md` (branch hierarchy, tagging, multi-agent protocol)

### Day 1 — Memory bootstrap

- [ ] Write `feedback_dev_environment.md` (document any env quirks discovered)
- [ ] Write `project_git_workflow.md` (branch names, where the spec lives)
- [ ] Create `MEMORY.md` index pointing to both files

### Day 2+ — Add as needed

- [ ] Write `docs/roadmap.md` (first 5-10 items with codenames + touch zones)
- [ ] Write `docs/roadmap-status.md` (empty table, ready for registration)
- [ ] Write `docs/hosting.md` (local/stage/prod tier definitions)
- [ ] Configure MCP servers in `.claude/settings.json` (Docker, GitHub)
- [ ] Write `project_roadmap_state.md` memory file (ordered priority list)

---

## Appendix B: New Roadmap Item Checklist

Every new item added to `docs/roadmap.md` must include:

- [ ] `[codename: xxx]` tag in the heading (1-3 words, kebab-case, unique)
- [ ] `**Touch zones:** <paths/globs>` line immediately after heading
- [ ] **Problem** section: what is broken or missing
- [ ] **Fix** section: what to build (specific enough to implement without clarifying questions)
- [ ] **Implementation notes** section: constraints, reuse pointers, anti-patterns

Before starting implementation:

- [ ] Read `docs/roadmap-status.md` — confirm no in-progress item's touch zones overlap
- [ ] Cut branch from `dev`: `git checkout -b feature/rm-<codename>`
- [ ] First commit: add entry to `docs/roadmap-status.md`
- [ ] Commit message: `chore(rm-<codename>): register as in-progress`
- [ ] Only then begin implementation

---

## Appendix C: Pre-Commit Checklist

Before every commit to a feature branch:

- [ ] Gate 1: typecheck + lint pass (no errors, warnings reviewed)
- [ ] Gate 2: tests pass (run full suite or targeted test file)
- [ ] Gate 3: `docker compose up -d --build` succeeds
- [ ] Schema changes: TypeScript types updated in the same commit
- [ ] No files modified outside the stated task scope
- [ ] No new dead code (unused imports, unreachable branches removed)
- [ ] No file exceeds 400 lines
- [ ] No function exceeds 50 lines
- [ ] Commit message follows convention: `type(scope): description`
