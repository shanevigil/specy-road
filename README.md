# specy-road

**Roadmap-first coordination** for human teams and coding agents: one canonical graph under `roadmap/`, **planning/** Markdown for phase and milestone narratives, clear separation between **purpose**, **principles**, and **enforceable constraints**, and **shared/** contracts cited from work items.

## Why use it

- **Single source of truth** — The roadmap graph under `roadmap/` (`manifest.json` + ordered **JSON** chunk files) drives priorities, dependencies, and gates; **phase and milestone** nodes point at **`planning/<node-id>/`** for narrative; contracts live in `shared/` and are cited from work items.
- **Smaller context for agents** — Generate a focused brief for a node so assistants load only what that task needs, instead of the whole repo story.
- **Safer parallel work** — Immutable milestone IDs, **touch zones**, and **registration** in `roadmap/registry.yaml` make active work visible before files collide.
- **Your tools, your workflow** — The kit is opinionated about **roadmapping and specs**, not about which IDE, agent, or in-session planning style you use. See [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md).

## How this relates to [Spec-Kit](https://github.com/github/spec-kit)

Spec-Kit helped popularize disciplined specs and context hygiene. **specy-road** keeps that spirit but centers a **roadmap graph** and **registry** as the spine of coordination. It does **not** prescribe a particular agent “spec → plan → tasks” ceremony inside Cursor, Claude Code, or any other product—that stays between you and your tools.

## Install

Requires **Python 3.11+**.

```bash
pip install specy-road
# optional: pip install "specy-road[gui-next]" for the PM Gantt UI (`specy-road gui`)
# optional: pip install "specy-road[review]" for `specy-road review-node`
```

The package installs two commands: `**specy-road**` (validators, brief, export, `init project`, …) and `**specyrd**` (optional IDE glue — see [specyrd](#specyrd-optional-ide-command-stubs)).

### New project (consumer)

From your **application repository root** (or pass a path):

```bash
specy-road init project
specy-road validate
specy-road export
specy-road brief M1.1 -o work/brief-M1.1.md
```

Use `specy-road init project --dry-run` to preview files, or `--force` to replace an existing scaffold. Optional: `specyrd init --here --ai cursor` for slash-command stubs that call the same CLI.

### Developing **specy-road** (this repository)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

Validate the **dogfood** sample tree and run tests (maintainers):

```bash
specy-road validate --repo-root tests/fixtures/specy_road_dogfood
specy-road export --check --repo-root tests/fixtures/specy_road_dogfood
specy-road file-limits
pytest
```

Optional git hooks: `pip install pre-commit && pre-commit install` (same checks as CI).

## specyrd (optional IDE command stubs)

**specyrd** is an optional installer for **slash-command-style markdown** (or equivalent) that points agents at the same workflows as `**specy-road`**. It does **not** replace roadmap validation or briefs, and it is **not** [Spec Kit](https://github.com/github/spec-kit)’s `specify` CLI. Per–phase/milestone folders named `planning/<node-id>/` hold **overview/plan/tasks** narrative (required for those node types) — unrelated to that tool.

- **Subcommand:** `init` only.
- **Typical use:** Run once per repo (or per IDE); add a second agent pack by running `init` again with another `--ai`.

### Command line

```text
specyrd init [PATH] --ai <ID> [--ide <ID>] [--here] [--dry-run] [--force] [--ai-commands-dir REL_PATH]
```

- `**PATH**` — Directory used to resolve the repository (default: `.`). The tool prefers the git worktree root (`git rev-parse --show-toplevel`) when `PATH` is inside a git repo.
- `**--ai` / `--ide**` — Required. Same option under two names. Agent pack: `cursor`, `claude-code`, or `generic`.
- `**--here**` — Use the current working directory as the target (equivalent to `PATH` being `.`).
- `**--dry-run**` — Print paths that would be written; do not create or overwrite files.
- `**--force**` — Overwrite existing specyrd command stubs and `.specyrd/README.md` if they already exist.
- `**--ai-commands-dir REL_PATH**` — **Required** when `--ai generic`. Must be a **relative** path under the repo root (no `..`). Writes command `.md` files into that directory.

### What gets installed

By default (no `--role`), **fourteen** command files are written: `validate`, `brief`, `export`, `file-limits`, `author`, `constitution`, `claim`, `finish`, `do-next-task`, `sync`, `list-nodes`, `show-node`, `add-node`, `review-node` (file names are `specyrd-<name>.md`).


| Target        | Path (under repo root)                                          | Meta                                           |
| ------------- | --------------------------------------------------------------- | ---------------------------------------------- |
| `cursor`      | `.cursor/commands/specyrd-*.md`                                 | `.specyrd/README.md`, `.specyrd/manifest.json` |
| `claude-code` | `.claude/commands/specyrd-*.md`                                 | same                                           |
| `generic`     | `<REL_PATH>/specyrd-*.md` (`REL_PATH` from `--ai-commands-dir`) | same                                           |


`**--role`** installs a subset: `**pm**` — `validate`, `export`, `author`, `constitution`, `sync`, `list-nodes`, `show-node`, `add-node`, `review-node`; `**dev**` — `validate`, `brief`, `claim`, `finish`, `do-next-task`. Omit `--role` for the full set above.

Stubs only contain instructions to run `**specy-road**` from the project root (for example `specy-road validate`, `specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md`). Canonical behavior stays in the CLI.

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

1. **Bootstrap** — `specy-road init project` (once per repository) lays down `constitution/`, `roadmap/`, `shared/`, `constraints/`, `schemas/`, `planning/`, `work/`, and `AGENTS.md`.
2. **Author** — Edit roadmap JSON chunks under `roadmap/` (listed in `manifest.json`). See [docs/roadmap-authoring.md](docs/roadmap-authoring.md).
3. **Validate** — `specy-road validate` (optional `--repo-root` if not running from the project root).
4. **Publish views** — `specy-road export` regenerates `roadmap.md` from the merged graph.
5. **Focus a task** — `specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md` and implement against `shared/` contracts cited for that node.
6. **Parallel or roadmap-driven branches** — Follow [docs/git-workflow.md](docs/git-workflow.md): branch `feature/rm-<codename>`, **first commit** registers in `roadmap/registry.yaml`, then implement.
7. **Optional IDE commands** — [specyrd](#specyrd-optional-ide-command-stubs) installs thin stubs that invoke the same CLI.

## Where to read next


| Document                                                                     | Purpose                                                                                          |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md)                 | What the kit promises and what it leaves to you                                                  |
| [docs/architecture.md](docs/architecture.md)                                 | End-to-end flow (manifest, chunks, validation, briefs)                                           |
| [docs/roadmap-authoring.md](docs/roadmap-authoring.md)                       | JSON chunks, manifest ordering, generated `roadmap.md`                                             |
| [docs/git-workflow.md](docs/git-workflow.md)                                 | Branches, registry, merge-back                                                                   |
| [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) | Optional patterns (CLAUDE.md, Cursor rules, MCP, etc.) for product repos—not required by the kit |
| [AGENTS.md](AGENTS.md)                                                       | Short entry for coding agents                                                                    |


## Repository layout (overview)

**In your application repo** (after `specy-road init project`), expect `constitution/`, `constraints/`, `roadmap/`, `shared/`, `planning/`, `schemas/`, `work/`, `AGENTS.md`, and a generated `roadmap.md`.

**This repository** (the `specy-road` toolkit) additionally contains:

| Path | Role |
| ---- | ---- |
| [`specy_road/`](specy_road/) | Python package: `specy-road` / `specyrd` CLIs, `bundled_scripts/` (validators, brief, export), PM GUI assets |
| [`specy_road/templates/project/`](specy_road/templates/project/) | Files copied by `specy-road init project` |
| [`tests/fixtures/specy_road_dogfood/`](tests/fixtures/specy_road_dogfood/) | Maintainer sample roadmap + contracts for CI |
| [`templates/`](templates/) | Extra stubs (roadmap checklists, etc.) |
| [`docs/`](docs/) | Architecture, workflows, philosophy |

Consumer `vision.md` and `roadmap.md` live at the **project** root; they are not duplicated here.

## CLI migration (tooling releases)

- **PM GUI setup:** use `specy-road init gui --install-gui` (and related flags) instead of `specy-road init --install-gui`.
- **Project scaffold:** use `specy-road init project` to create `roadmap/`, `constitution/`, etc. in a consumer repository.

## Related material

- [Spec-Kit](https://github.com/github/spec-kit) — inspiration only  
- [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) — optional AI tooling ideas for application repositories

## License

MIT — see [LICENSE](LICENSE).