# specy-road

**Roadmap-first coordination** for teams and coding agents.

You keep one **roadmap graph** under `roadmap/`, one **feature sheet** per node under `planning/` (Markdown), **constitution** prose (purpose and principles), **enforceable limits** under `constraints/`, and **shared** contracts that work items cite. The CLI validates the graph, exports a readable index, and generates **briefs** so agents load only what a task needs.

## Why use it

- **Single source of truth** — Priorities, dependencies, and gates live in `roadmap/` (`manifest.json` plus JSON chunks). Nodes with `planning_dir` point at a single sheet under `planning/`. Cross-cutting contracts live in `shared/` and are cited where they apply.
- **Smaller context for agents** — `specy-road brief` assembles the right planning sheets and contracts for one node instead of the whole repo story.
- **Safer parallel work** — Stable IDs, touch zones, and `roadmap/registry.yaml` make active work visible before files collide.
- **Your tools, your workflow** — The kit cares about roadmaps and specs, not which IDE or agent ceremony you use. See [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md).

## How this relates to [Spec-Kit](https://github.com/github/spec-kit)

Spec-Kit helped popularize disciplined specs and context hygiene. **specy-road** keeps that spirit but puts a **roadmap graph** and **registry** at the center. It does **not** prescribe an in-product “spec → plan → tasks” ritual in Cursor, Claude Code, or elsewhere—that stays between you and your tools.

## Install

Requires **Python 3.11+**.

```bash
pip install specy-road
# optional: pip install "specy-road[gui-next]" for the PM Gantt UI (`specy-road gui`)
# optional: pip install "specy-road[review]" for `specy-road review-node`
```

How the PM Gantt UI is packaged (FastAPI + built frontend): [docs/pm-gui.md](docs/pm-gui.md).

You get two commands: **`specy-road`** (validate, brief, export, `init project`, …) and **`specyrd`** (optional IDE stubs — see [specyrd](#specyrd-optional-ide-command-stubs)).

### New project (consumer)

From your **application repository root** (or pass a path):

```bash
specy-road init project
# Edit roadmap/git-workflow.yaml so integration_branch / remote match your team (e.g. dev, origin)
specy-road validate
specy-road export
specy-road brief M1.1 -o work/brief-M1.1.md
```

Use `specy-road init project --dry-run` to preview, or `--force` to replace a scaffold. After init, set `roadmap/git-workflow.yaml` (integration branch and remote) so the CLI and PM Gantt match your repo; see [docs/git-workflow.md](docs/git-workflow.md). Optional: `specyrd init --here --ai cursor` adds slash-command stubs that call the same CLI.

### Bootstrap prompts (optional)

The **specy-road source tree** includes **[suggested_prompts/](suggested_prompts/)** — copy-paste prompts for Cursor, Claude Code, or similar. They are **not** installed by `pip install`; open them from a **clone** of this repository.

| Prompt | When to use it |
| ------ | -------------- |
| [bootstrap-governance.md](suggested_prompts/bootstrap-governance.md) | Existing repos: align vision, constitution, constraints, and `shared/`. |
| [bootstrap-roadmap.md](suggested_prompts/bootstrap-roadmap.md) | Existing repos: migrate notes into `roadmap/`, `registry.yaml`, and `planning/`. |
| [bootstrap-agents-md.md](suggested_prompts/bootstrap-agents-md.md) | Existing repos or after `init project`: merge `AGENTS.md`, `CLAUDE.md`, and Cursor rules; clarifies consumer vs toolkit boundaries. |

**New project:** run [specy-road init project](#new-project-consumer) first. Use these prompts only if you want an agent to help refine governance, roadmap content, or editor config—especially when you already have team docs to preserve.

### Developing **specy-road** (this repository)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-ci.txt
```

`requirements-ci.txt` is a compiled lock matching CI; regenerate with `pip-compile` — see [docs/supply-chain-security.md](docs/supply-chain-security.md). The short [requirements.txt](requirements.txt) mirrors core runtime deps from `pyproject.toml` for reference only.

Validate the **dogfood** sample tree and run tests (maintainers):

```bash
specy-road validate --repo-root tests/fixtures/specy_road_dogfood
specy-road export --check --repo-root tests/fixtures/specy_road_dogfood
specy-road file-limits
pytest
# After changing gui/pm-gantt sources:
#   cd gui/pm-gantt && npm ci && npm run lint && npm test && npm run build
```

**Dependency and supply-chain:** see [docs/supply-chain-security.md](docs/supply-chain-security.md). Quick checks: after `pip install -r requirements-ci.txt`, run `pip install pip-audit && pip-audit`; for the Gantt UI tree, `cd gui/pm-gantt && npm ci && npm audit --omit=dev`. More detail: [docs/setup.md](docs/setup.md#dependency-and-security-checks).

**Trying `specy-road init project`:** With no path, the CLI uses the git worktree root—in **this** repo that would scaffold into the toolkit tree. Prefer an explicit directory (for example `specy-road init project /tmp/specy-consumer-sandbox`) or the gitignored [playground/](playground/README.md).

Optional git hooks: `pip install pre-commit && pre-commit install` — runs part of CI (roadmap validate, export `--check`, file limits), not supply-chain audits or `pytest`. See [docs/setup.md](docs/setup.md#install-the-pre-commit-hook).

## specyrd (optional IDE command stubs)

**specyrd** installs **slash-command-style** stubs that point agents at the same workflows as **`specy-road`**. It does not replace validation or briefs, and it is **not** [Spec Kit](https://github.com/github/spec-kit)’s `specify` CLI. Feature sheets are flat **`planning/*.md`** files per roadmap node—unrelated to that tool.

- **Subcommand:** `init` only.
- **Typical use:** Run once per repo (or per IDE); add another agent pack by running `init` again with a different `--ai`.

### Command line

```text
specyrd init [PATH] --ai <ID> [--ide <ID>] [--here] [--dry-run] [--force] [--ai-commands-dir REL_PATH]
```

- **PATH** — Resolves the repo (default: `.`). Inside a git repo, the tool prefers the worktree root (`git rev-parse --show-toplevel`).
- **--ai / --ide** — Required (same flag twice). Agent pack: `cursor`, `claude-code`, or `generic`.
- **--here** — Use the current directory as the target (same as `PATH` being `.`).
- **--dry-run** — Print paths only; do not write files.
- **--force** — Overwrite existing stubs and `.specyrd/README.md`.
- **--ai-commands-dir REL_PATH** — Required for `--ai generic`. Must be relative under the repo root (no `..`). Writes `specyrd-*.md` into that folder.

### What gets installed

By default (no `--role`), **fourteen** stub files are written: `validate`, `brief`, `export`, `file-limits`, `author`, `constitution`, `claim`, `finish`, `do-next-task`, `sync`, `list-nodes`, `show-node`, `add-node`, `review-node` (files named `specyrd-<name>.md`).

| Target | Path (under repo root) | Also writes |
| ------ | ------------------------ | ----------- |
| `cursor` | `.cursor/commands/specyrd-*.md` | `.specyrd/README.md`, `.specyrd/manifest.json` |
| `claude-code` | `.claude/commands/specyrd-*.md` | same |
| `generic` | `<REL_PATH>/specyrd-*.md` | same |

**--role** installs a subset: **`pm`** — `validate`, `export`, `author`, `constitution`, `sync`, `list-nodes`, `show-node`, `add-node`, `review-node`; **`dev`** — `validate`, `brief`, `claim`, `finish`, `do-next-task`. Omit `--role` for the full set.

Stubs only tell the agent to run **`specy-road`** from the project root (for example `specy-road validate`, `specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md`). Behavior stays in the CLI.

### Examples

```bash
# Cursor: from repo root
specyrd init --here --ai cursor

# Claude Code: explicit path
specyrd init /path/to/repo --ai claude-code

# Preview writes only
specyrd init . --ai cursor --dry-run

# Generic: put stubs under docs/agent-commands/ (relative to repo root)
specyrd init --here --ai generic --ai-commands-dir docs/agent-commands

# Overwrite a previous run’s stubs
specyrd init --here --ai cursor --force
```

### See also

- [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md) — required kit surface vs optional IDE glue  
- [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) — broader optional agent/IDE patterns  
- [AGENTS.md](AGENTS.md) — agent load order (stubs defer to the same commands)

## How to work with it

1. **Bootstrap** — `specy-road init project` (once per repo) creates `constitution/`, `roadmap/`, `shared/`, `constraints/`, `schemas/`, `planning/`, `work/`, and `AGENTS.md`.
2. **Author** — Edit JSON chunks under `roadmap/` (listed in `manifest.json`). See [docs/roadmap-authoring.md](docs/roadmap-authoring.md).
3. **Validate** — `specy-road validate` (use `--repo-root` if not in the project root).
4. **Publish views** — `specy-road export` regenerates `roadmap.md` from the merged graph.
5. **Focus a task** — `specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md`, then implement against `shared/` contracts cited for that node.
6. **Branches** — Follow [docs/git-workflow.md](docs/git-workflow.md): register in `roadmap/registry.yaml` on the **integration branch**, then `feature/rm-<codename>` (or use `specy-road do-next-available-task`).
7. **Optional IDE commands** — [specyrd](#specyrd-optional-ide-command-stubs) installs thin stubs that invoke the same CLI.

## Where to read next

| Document | Purpose |
| -------- | ------- |
| [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md) | What the kit promises and what it leaves to you |
| [docs/architecture.md](docs/architecture.md) | End-to-end flow: manifest, chunks, validation, briefs |
| [docs/roadmap-authoring.md](docs/roadmap-authoring.md) | JSON chunks, manifest order, generated `roadmap.md` |
| [docs/git-workflow.md](docs/git-workflow.md) | Branches, registry, merge-back |
| [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) | Optional patterns (CLAUDE.md, Cursor rules, MCP) for app repos |
| [suggested_prompts/](suggested_prompts/) | Adoption prompts for existing projects ([Bootstrap prompts](#bootstrap-prompts-optional)) |
| [AGENTS.md](AGENTS.md) | Short entry for coding agents |

## Repository layout (overview)

**In your application repo** (after `specy-road init project`), expect `constitution/`, `constraints/`, `roadmap/`, `shared/`, `planning/`, `schemas/`, `work/`, `AGENTS.md`, and a generated `roadmap.md`.

**This repository** (the toolkit) also contains:

| Path | Role |
| ---- | ---- |
| [specy_road/](specy_road/) | Python package: CLIs, `bundled_scripts/`, PM GUI assets |
| [specy_road/templates/project/](specy_road/templates/project/) | Scaffold copied by `specy-road init project` |
| [suggested_prompts/](suggested_prompts/) | Adoption prompts (not installed by `pip`) |
| [tests/fixtures/specy_road_dogfood/](tests/fixtures/specy_road_dogfood/) | Maintainer sample roadmap for CI |
| [templates/](templates/) | Extra stubs (roadmap checklists, etc.) |
| [docs/](docs/) | Architecture, workflows, philosophy |

Consumer `vision.md` and `roadmap.md` live at the **project** root; they are not duplicated in this toolkit repo.

## CLI migration (tooling releases)

- **PM GUI:** use `specy-road init gui --install-gui` (and related flags), not `specy-road init --install-gui`.
- **Project scaffold:** use `specy-road init project` for `roadmap/`, `constitution/`, etc. in a consumer repository.

## Related material

- [Spec-Kit](https://github.com/github/spec-kit) — inspiration only  
- [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) — optional AI tooling ideas for application repositories

## License

MIT — see [LICENSE](LICENSE).
