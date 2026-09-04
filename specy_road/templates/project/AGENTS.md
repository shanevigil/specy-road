# Agents — load order

0. `roadmap-context.md` — the current state of the roadmap in one file: what is
   done, what was decided, which gates are open, which dependencies were dropped,
   and what has been archived. Read this before crawling `planning/` or `work/`.
   Regenerate with `specy-road digest`.
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

## Finding things

Do not grep `planning/` or `work/` directly. Those directories hold a great deal
of duplicated text — a brief inlines its ancestor planning sheets and every
the `shared/*.md` files it cites, and a pr-body re-inlines the whole brief — so a raw
search returns the same passage many times over. Use the ranked, deduplicated
index instead:

```bash
specy-road search "<query>"                    # live + archived, current work first
specy-road search "<query>" --scope archived   # completed work, hidden from IDE indexing
specy-road search <NODE_ID>                    # everything about one node
specy-road history <NODE_ID>                   # how it reached its current state
```

Archived roadmap material is deliberately excluded from IDE indexing (see
`.cursorindexingignore`) so it cannot crowd out current decisions. It is still
fully readable — search returns a path, and you open it.

The brief inlines each effective dependency's `## Intent` block under `## 6. Dependency context (intent of upstream work)` — read it before opening dependency planning sheets directly. When **authoring** a planning sheet, do not paraphrase what dependencies deliver; the brief carries that for the coding agent automatically.

**Task pickup:** When using `specy-road do-next-available-task`, the command always **syncs** the integration branch, **registers**, **pushes** it, then creates `feature/rm-*` so the team sees the claim on the remote (there are no flags to skip sync or push). The pickup target is always an actionable **leaf**; ancestors are context containers and roll up progress from descendants. To release a claim without finishing, use `specy-road abort-task-pickup` on `feature/rm-*` (see `docs/dev-workflow.md`).

Three selection rules that are easy to read backwards:

- **`status: Blocked` leaves are offered FIRST**, not skipped — a blocked leaf is the one most worth unblocking. Pickup prints `status: Blocked` when it hands you one. To keep work out of the queue entirely, give it a `type: gate` dependency instead of marking it Blocked.
- **`execution_milestone` (`Human-led` / …) is advisory.** It documents intent; it does not gate pickup. `type: gate` is the enforcing mechanism.
- **A dependency on a phase or milestone is satisfied by its rollup** — every leaf descendant `Complete` — not by that node's own `status` field.

After Blocked and MR-rejected, auto-pick follows **outline (tree) order**, not raw merged chunk order (`docs/roadmap-authoring.md`).
