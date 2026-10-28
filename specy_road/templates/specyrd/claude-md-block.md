## specy-road (roadmap-first coordination)

This repository keeps a canonical roadmap graph, contracts, and planning
narrative alongside its code. Follow those contracts; don't invent new
workflows. Written by `specyrd init` ({{SPECYRD_VERSION}}) — everything outside
the markers around this section is yours.

### Start here (required load order)

1. `{{PROJECT_PREFIX}}roadmap-context.md` — the generated current-state summary
   (`specy-road digest`). Far smaller than the corpus it stands in for, and
   always current. Read it before anything else — except a `work/brainstorm-*` prompt: open that first.
2. `{{PROJECT_PREFIX}}AGENTS.md` — load order and coordination rules.

Then, for a roadmap-linked task, keep context small:

- `{{PROJECT_PREFIX}}constitution/purpose.md` and
  `{{PROJECT_PREFIX}}constitution/principles.md`
- `{{PROJECT_PREFIX}}constraints/README.md`
- **Roadmap graph** — `{{PROJECT_PREFIX}}roadmap/manifest.json` plus the chunk
  files it lists under `includes`: your node, its parents, its `dependencies`
- `{{PROJECT_PREFIX}}shared/README.md`, then **only** the contracts your node
  cites

### Roadmap model (do not confuse with the registry)

- **Merged graph (source of truth):** `{{PROJECT_PREFIX}}roadmap/manifest.json`
  lists ordered `includes` of **JSON** chunk files under
  `{{PROJECT_PREFIX}}roadmap/` (e.g. `phases/M1.json`). That is the data model —
  not YAML.
- **Registration overlay:** `{{PROJECT_PREFIX}}roadmap/registry.yaml` records who
  claimed which node and their touch zones. It is not a merge chunk and does not
  replace the graph.
- **Generated index:** `{{PROJECT_PREFIX}}roadmap.md` (`specy-road export`) and
  `{{PROJECT_PREFIX}}roadmap-context.md` (`specy-road digest`) are both generated
  and committed. Edit the graph, then regenerate — never the other way round.

Generate a focused brief before implementing:

```bash
specy-road brief <NODE_ID> -o {{PROJECT_PREFIX}}work/brief-<NODE_ID>.md
```

### Non-negotiables

- **Docs win.** If instructions conflict, prefer tracked repo docs over chat
  history.
- **No scope creep.** Don't refactor unrelated code "for cleanliness".
- **Search before adding.** Use `specy-road search "<query>"` (ranked,
  deduplicated; `--scope archived` for completed work), not a grep of
  `planning/` or `work/`.
- **Other agents share this checkout.** Check `git status` and
  `git worktree list` before any git write; commit by explicit path, never
  `-A`/`-a`; no stash, reset, or branch switches here — use your own
  worktree. Full rule in `{{PROJECT_PREFIX}}AGENTS.md`.
- **Roadmap-linked implementation.** Register the claim on the integration
  branch, then work on `feature/rm-<codename>`. The branch name comes from the
  node's `codename`; don't rename a node's title mid-flight.

### Common commands

```bash
specy-road validate          # graph + registry + planning artifacts
specy-road export --check    # roadmap.md drift gate
specy-road digest --check    # roadmap-context.md drift gate
specy-road file-limits       # per-file line caps
```

### Keeping this in sync

`specy-road upgrade` updates the schemas, the IDE skills and this section after
a `pip install -U specy-road`. It rewrites only what `.specyrd/manifest.json`
records as managed, and never touches anything outside those markers.
