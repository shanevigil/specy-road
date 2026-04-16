# Agents — load order

1. `constitution/purpose.md` — why this exists
2. `constitution/principles.md` — how we decide
3. `constraints/README.md` — enforced rules
4. `docs/supply-chain-security.md` — dependency and supply-chain verification policy (adopt what matches your stack)
5. Merged roadmap (`roadmap/manifest.json` + chunk files): your node, parents, and dependencies
6. `planning/<id>_<slug>_<node_key>.md` feature sheet for each node that has `planning_dir` (read ancestor sheets for context)
7. `shared/README.md`, then only contract files cited for the task

Focused brief:

```bash
specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md
```

**Task pickup:** When using `specy-road do-next-available-task`, use the **default** flow (sync integration branch, register, **push** integration branch, then `feature/rm-*`) so the team sees the claim on the remote. **`--no-sync`** and **`--no-push-registry`** are for explicit offline/CI-style use only—not a default for agents.
