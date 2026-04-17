# Install and project setup

Use this guide when you install **specy-road** from PyPI for work in an **application** repository.

- **Editable install** of this toolkit (contributors): [setup.md](setup.md) and [toolkit-development.md](toolkit-development.md).
- **PM Gantt UI** packaging (FastAPI + frontend): [pm-gui.md](pm-gui.md).

## Requirements

- **Python 3.11+**

## Install from PyPI

```bash
pip install specy-road
```

### Optional extras

```bash
# PM Gantt dashboard (`specy-road gui`)
pip install "specy-road[gui-next]"

# `specy-road review-node`
pip install "specy-road[review]"
```

You get two CLI entry points:

- **`specy-road`** — validate, brief, export, `init project`, task commands, …
- **`specyrd`** — optional IDE command stubs (see [below](#optional-specyrd-ide-command-stubs))

## New project (consumer)

From your **application repository root** (or pass a path to `specy-road init project`):

```bash
specy-road init project
# Edit roadmap/git-workflow.yaml so integration_branch / remote match your team (e.g. dev, origin)
specy-road validate
specy-road export
specy-road brief M1.1 -o work/brief-M1.1.md
```

Use `specy-road init project --dry-run` to preview, or `--force` to replace a scaffold. After init, set `roadmap/git-workflow.yaml` (integration branch and remote) so the CLI and PM Gantt match your repo; see [git-workflow.md](git-workflow.md). Optional: `specyrd init --here --ai cursor` adds slash-command stubs that call the same CLI.

## Optional bootstrap prompts

The **specy-road source tree** includes **[suggested_prompts/](../suggested_prompts/)** — copy-paste prompts for Cursor, Claude Code, or similar. They are **not** installed by `pip install`; open them from a **clone** of this repository.

| Prompt | When to use it |
| ------ | -------------- |
| [bootstrap-governance.md](../suggested_prompts/bootstrap-governance.md) | Existing repos: align vision, constitution, constraints, and `shared/`. |
| [bootstrap-roadmap.md](../suggested_prompts/bootstrap-roadmap.md) | Existing repos: migrate notes into `roadmap/`, `registry.yaml`, and `planning/`. |
| [bootstrap-agents-md.md](../suggested_prompts/bootstrap-agents-md.md) | Existing repos or after `init project`: merge `AGENTS.md`, `CLAUDE.md`, and Cursor rules; clarifies consumer vs toolkit boundaries. |

Run [`specy-road init project`](#new-project-consumer) in a new app repo first. Use these prompts only if you want an agent to help refine governance, roadmap content, or editor config—especially when you already have team docs to preserve.

## Optional: specyrd IDE command stubs

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

- [philosophy-and-scope.md](philosophy-and-scope.md) — required kit surface vs optional IDE glue
- [optional-ai-tooling-patterns.md](optional-ai-tooling-patterns.md) — broader optional agent/IDE patterns
- [AGENTS.md](../AGENTS.md) — agent load order (stubs defer to the same commands)
- [setup.md](setup.md) — additional `specyrd` examples for development clones

## CLI migration (tooling releases)

- **PM GUI:** use `specy-road init gui --install-gui` (and related flags), not `specy-road init --install-gui`.
- **Project scaffold:** use `specy-road init project` for `roadmap/`, `constitution/`, etc. in a consumer repository.
