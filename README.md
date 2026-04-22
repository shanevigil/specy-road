# specy-road

**One roadmap for the whole team**—so product, engineering, and coding agents share the same plan.

## What it is

**specy-road** is a toolkit for keeping priorities, written specs, and implementation work aligned. It fits teams that use AI-assisted editors (for example Claude or Cursor) together with product-led planning. Your team maintains a **roadmap** in the repository: what matters, in what order, and what depends on what. A small command-line tool checks that the roadmap is consistent, publishes a readable index, and can build **briefs**—focused packets of context for a single task—so nobody has to reread the entire project to know what to do next.

### Who it’s for

- **Product managers and delivery leads** — A single place for direction, sequencing, and visibility into what is active or blocked.
- **Developers and coding agents** — Task-sized context, shared contracts, and clear ownership areas so work stays parallel without stepping on the same files.

## Why teams use it

- **Single source of truth** — Less drift between tickets, docs, and “what we agreed.” The roadmap and planning sheets stay tied together; cross-cutting rules live in `shared/` where they belong.
- **Right-sized context** — `specy-road brief` pulls the relevant planning sheets and contracts for one roadmap item instead of the whole repository story.
- **Safer parallel work** — Stable IDs, **touch zones**, and `roadmap/registry.yaml` show who is working on what before files collide.
- **Your tools, your workflow** — The kit is about roadmaps and specs, not a particular IDE or agent ritual. See [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md).

## Getting started

Install the CLI (**Python 3.11+**) and **git**, then follow **[Install](#install)** and **[docs/install-and-usage.md](docs/install-and-usage.md)** for cloning, editable install, and **`specy-road init project`** in an application repo. After that, everyday use boils down to:

### For PMs

1. Prefer **`specy-road gui`** for the dashboard, or edit `roadmap/` and `planning/` directly ([docs/pm-gui.md](docs/pm-gui.md)).
2. Run **`specy-road export`** and **`specy-road validate`** before you commit.

More detail: [docs/pm-workflow.md](docs/pm-workflow.md). Optional **LLM Review** in the Gantt UI: [docs/pm-llm-review.md](docs/pm-llm-review.md).

### For developers

1. Pick up work with **`specy-road do-next-available-task`**, or **`specy-road brief <NODE_ID>`** for a specific node ([docs/dev-workflow.md](docs/dev-workflow.md)).
2. Finish with **`specy-road finish-this-task`**, then land changes with your team’s PR process ([docs/git-workflow.md](docs/git-workflow.md)).

## Install

Requires **Python 3.11+** and **git** (with a configured remote — `origin`
by default).

```bash
pip install specy-road
# optional extras:
#   pip install "specy-road[gui-next]"  # PM Gantt UI deps
#   pip install "specy-road[review]"    # LLM review (`specy-road review-node`)
```

The full install + everyday usage guide is at
**[docs/install-and-usage.md](docs/install-and-usage.md)**. Building from
source is documented in
**[docs/contributor-guide.md](docs/contributor-guide.md)**.

Consumer **`init project`**, `roadmap/git-workflow.yaml`, optional **`specyrd`** stubs, and bootstrap prompts are covered in **[docs/install-and-usage.md](docs/install-and-usage.md)**. Toolkit contributors (tests, pre-commit, releases): **[docs/contributor-guide.md](docs/contributor-guide.md)**.

## More on how to work with it

Typical path in an **application** repository after `specy-road init project`: roadmap and planning for direction and detail; validation, export, and briefs for engineering and agents; registry and branches for safe parallel work. Maintainers working on **this** toolkit follow [AGENTS.md](AGENTS.md), [docs/toolkit-development.md](docs/toolkit-development.md), and [docs/contributor-guide.md](docs/contributor-guide.md).

1. **Bootstrap** — `specy-road init project` (once per repo) creates `constitution/`, `roadmap/`, `shared/`, `constraints/`, `schemas/`, `planning/`, `work/`, and `AGENTS.md`.
2. **Author** — Edit JSON chunks under `roadmap/` (listed in `manifest.json`). See [docs/roadmap-authoring.md](docs/roadmap-authoring.md).
3. **Validate** — `specy-road validate` (use `--repo-root` if not in the project root).
4. **Publish views** — `specy-road export` regenerates `roadmap.md` from the merged graph.
5. **Focus a task** — `specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md`, then implement against `shared/` contracts cited for that node.
6. **Branches** — Follow [docs/git-workflow.md](docs/git-workflow.md): register in `roadmap/registry.yaml` on the **integration branch** from `roadmap/git-workflow.yaml`, then `feature/rm-<codename>` (or use `specy-road do-next-available-task`).
7. **Optional IDE commands** — `specyrd` installs stubs that invoke the CLI; see [docs/contributor-guide.md#ide-command-stubs-specyrd](docs/contributor-guide.md#ide-command-stubs-specyrd).

## Where to read next

| Document | Purpose |
| -------- | ------- |
| [docs/install-and-usage.md](docs/install-and-usage.md) | Install from source, `init project`, everyday PM/dev/GUI flows |
| [docs/contributor-guide.md](docs/contributor-guide.md) | Toolkit contributors: CI parity, pre-commit, releases, `specyrd` |
| [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md) | What the kit promises and what it leaves to you |
| [docs/architecture.md](docs/architecture.md) | End-to-end flow: manifest, chunks, validation, briefs |
| [docs/roadmap-authoring.md](docs/roadmap-authoring.md) | JSON chunks, manifest order, generated `roadmap.md` |
| [docs/git-workflow.md](docs/git-workflow.md) | Consumer workflow contract (`git-workflow.yaml`), branches, registry, merge-back |
| [docs/toolkit-development.md](docs/toolkit-development.md) | Short maintainer notes (this repo vs consumer contract) |
| [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) | Optional patterns (CLAUDE.md, Cursor rules, MCP) for app repos |
| [suggested_prompts/](suggested_prompts/) | Adoption prompts (clone this repo; not shipped on PyPI) |
| [AGENTS.md](AGENTS.md) | Short entry for coding agents |

## Related material

- [Spec-Kit](https://github.com/github/spec-kit) — inspiration only
- [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) — optional AI tooling ideas for application repositories

## Contributing to this repository

To participate in development of the **specy-road** toolkit itself, contact the repository owner. Technical setup: [docs/contributor-guide.md](docs/contributor-guide.md).

## License

MIT — see [LICENSE](LICENSE).
