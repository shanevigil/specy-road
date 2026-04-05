# AGENTS — entry point for coding agents

**Project:** specy-road — roadmap-first coordination kit (not [Spec-Kit](https://github.com/github/spec-kit); inspired by it only).

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

## Bootstrap backlog (transient)

[`docs/bootstrap-next-steps.md`](docs/bootstrap-next-steps.md) tracked tooling bootstrap tasks; it is **complete** for the current scope—delete or archive when you no longer need it. High-level flow: [`docs/architecture.md`](docs/architecture.md).

## Coordination

Read [`docs/git-workflow.md`](docs/git-workflow.md) before starting roadmap-linked implementation: branch `feature/rm-<codename>`, register in [`roadmap/registry.yaml`](roadmap/registry.yaml) first commit.
