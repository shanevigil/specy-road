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
<!-- prevents: work that contradicts the purpose and principles the project wrote down | enforced: advisory | ref: AGENTS.md block, load order items 1 and 2 -->
- `{{PROJECT_PREFIX}}constraints/README.md`
<!-- prevents: changes that break the project's file and function line caps | enforced: specy-road file-limits | ref: AGENTS.md block, load order item 3 -->
- **Roadmap graph** — `{{PROJECT_PREFIX}}roadmap/manifest.json` plus the chunk
  files it lists under `includes`: your node, its parents, its `dependencies`
<!-- prevents: loading the whole graph, or missing a dependency the node relies on | enforced: specy-road brief inlines the node, its ancestors and its effective dependencies | ref: AGENTS.md block, load order item 5 -->
- `{{PROJECT_PREFIX}}shared/README.md`, then **only** the contracts your node
  cites
<!-- prevents: every contract in shared/ loaded into context for one task | enforced: specy-road brief inlines only the contracts the node's chain cites | ref: shared/README.md -->

### Roadmap model (do not confuse with the registry)

- **Merged graph (source of truth):** `{{PROJECT_PREFIX}}roadmap/manifest.json`
  lists ordered `includes` of **JSON** chunk files under
  `{{PROJECT_PREFIX}}roadmap/` (e.g. `phases/M1.json`). That is the data model —
  not YAML.
<!-- prevents: agents writing a merged YAML roadmap, or editing roadmap.md, instead of the JSON chunks | enforced: specy-road validate loads only the manifest and its includes | ref: docs/roadmap-authoring.md -->
- **Registration overlay:** `{{PROJECT_PREFIX}}roadmap/registry.yaml` records who
  claimed which node and their touch zones. It is not a merge chunk and does not
  replace the graph.
<!-- prevents: registry rows treated as graph data, or listed as a manifest include | enforced: specy-road validate checks the registry against the graph separately | ref: docs/git-workflow.md -->
- **Generated index:** `{{PROJECT_PREFIX}}roadmap.md` (`specy-road export`) and
  `{{PROJECT_PREFIX}}roadmap-context.md` (`specy-road digest`) are both generated
  and committed. Edit the graph, then regenerate — never the other way round.
<!-- prevents: hand edits to generated files that the next export or digest overwrites | enforced: export --check and digest --check drift gates | ref: docs/roadmap-authoring.md -->

Generate a focused brief before implementing:

```bash
specy-road brief <NODE_ID> -o {{PROJECT_PREFIX}}work/brief-<NODE_ID>.md
```

### Non-negotiables

- **Docs win.** If instructions conflict, prefer tracked repo docs over chat
  history.
<!-- prevents: an agent acting on stale chat history over the tracked docs that replaced it | enforced: advisory | ref: AGENTS.md block, precedence rule -->
- **No scope creep.** Don't refactor unrelated code "for cleanliness".
<!-- prevents: unrelated refactors that widen the diff and the review | enforced: touch zones in the brief and the reviewer excess checklist | ref: docs/design-notes/lean-code-census.md -->
- **Search before adding.** Use `specy-road search "<query>"` (ranked,
  deduplicated; `--scope archived` for completed work), not a grep of
  `planning/` or `work/`.
<!-- prevents: grep hits repeated across briefs and pr-bodies, and new artifacts that duplicate archived ones | enforced: advisory; search ranks and deduplicates | ref: CHANGELOG v0.2.1-rc1, agent context: digest and search -->
- **Other agents share this checkout.** Check `git status` and
  `git worktree list` before any git write; commit by explicit path, never
  `-A`/`-a`; no stash, reset, or branch switches here — use your own
  worktree. Full rule in `{{PROJECT_PREFIX}}AGENTS.md`.
<!-- prevents: one session's branch switch or git add -A landing on another session's uncommitted work | enforced: session check exits 1 when staged paths overlap another live session's | ref: docs/design-notes/agent-guidance-and-shared-checkouts.md -->
- **Roadmap-linked implementation.** Register the claim on the integration
  branch, then work on `feature/rm-<codename>`. The branch name comes from the
  node's `codename`; don't rename a node's title mid-flight.
<!-- prevents: unregistered work two agents both pick up, and branch names that drift from the node | enforced: do-next-available-task registers, pushes, then creates feature/rm-codename | ref: docs/git-workflow.md -->

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
