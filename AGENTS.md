# AGENTS — entry point for coding agents

**Project:** specy-road — roadmap-first coordination kit (not [Spec-Kit](https://github.com/github/spec-kit); inspired by it only).

The kit is **opinionated** about roadmapping, specs, and contracts; it does **not** prescribe which agent or IDE you use or how you plan work inside a session. Read [`docs/philosophy-and-scope.md`](docs/philosophy-and-scope.md) for scope. Optional tooling ideas (CLAUDE.md, Cursor rules, MCP, etc.) live in [`docs/optional-ai-tooling-patterns.md`](docs/optional-ai-tooling-patterns.md) and are **not** required here.

## Load order (keep context small)

1. [`constitution/purpose.md`](constitution/purpose.md) — why this exists  
2. [`constitution/principles.md`](constitution/principles.md) — how we decide  
3. [`constraints/README.md`](constraints/README.md) — enforced rules  
4. [`roadmap/roadmap.yaml`](roadmap/roadmap.yaml) — **your node only** + parents + `dependencies`  
5. [`shared/README.md`](shared/README.md) — then open **only** cited contract files  

For a focused slice:

```bash
python scripts/generate_brief.py <NODE_ID> -o work/brief-<NODE_ID>.md
```

## Coordination

Read [`docs/git-workflow.md`](docs/git-workflow.md) before starting roadmap-linked implementation: branch `feature/rm-<codename>`, register in [`roadmap/registry.yaml`](roadmap/registry.yaml) first commit.
