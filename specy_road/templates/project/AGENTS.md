# Agents — load order

1. `constitution/purpose.md` — why this exists
2. `constitution/principles.md` — how we decide
3. `constraints/README.md` — enforced rules
4. Merged roadmap (`roadmap/manifest.json` + chunk files): your node, parents, and dependencies
5. `planning/<node-id>/` for phase/milestone nodes (`overview.md`, `plan.md`, optional tasks)
6. `shared/README.md`, then only contract files cited for the task

Focused brief:

```bash
specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md
```
