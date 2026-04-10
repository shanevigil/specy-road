# specy-road

**Roadmap-first coordination** for human teams and coding agents: one canonical graph for how the system evolves, clear separation between **purpose**, **principles**, and **enforceable constraints**, and optional deeper specs when a milestone needs them.

## Why use it

- **Single source of truth** — The roadmap graph under `roadmap/` (`manifest.json` + ordered **JSON** chunk files) drives priorities, dependencies, and gates; contracts live in `shared/` and are cited from work items.
- **Smaller context for agents** — Generate a focused brief for a node so assistants load only what that task needs, instead of the whole repo story.
- **Safer parallel work** — Immutable milestone IDs, **touch zones**, and **registration** in `roadmap/registry.yaml` make active work visible before files collide.
- **Your tools, your workflow** — The kit is opinionated about **roadmapping and specs**, not about which IDE, agent, or in-session planning style you use. See [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md).

## How this relates to [Spec-Kit](https://github.com/github/spec-kit)

Spec-Kit helped popularize disciplined specs and context hygiene. **specy-road** keeps that spirit but centers a **roadmap graph** and **registry** as the spine of coordination. It does **not** prescribe a particular agent “spec → plan → tasks” ceremony inside Cursor, Claude Code, or any other product—that stays between you and your tools.

## Install

Requires **Python 3.11+**.

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e ".[dev]"     # optional: editable install, pytest, both CLIs below
# optional: pip install -e ".[review]" for specy-road review-node (OpenAI/Azure)
# optional: pip install -e ".[gui]" for Streamlit roadmap dashboard (streamlit run scripts/roadmap_gui.py)
# optional: PM GUI stack notes + React Flow spike — docs/pm-gui-redesign.md, gui-spike/react-flow-spike/
```

The package installs two commands: `**specy-road**` (validators, brief, export) and `**specyrd**` (optional IDE glue — see [specyrd](#specyrd-optional-ide-command-stubs)).

Validate the repo and (optionally) run tests:

```bash
python scripts/validate_roadmap.py
python scripts/export_roadmap_md.py --check   # optional: roadmap.md matches merged graph
python scripts/validate_file_limits.py
pytest                                           # if dev extras installed
specy-road validate                              # same as validate_roadmap.py when CLI is installed
specy-road scaffold-planning <NODE_ID>           # optional: planning/<id>/ markdown + set roadmap planning_dir
```

Optional git hooks: `pip install pre-commit && pre-commit install` (roadmap validate, export drift check, file limits — same as CI except `pytest`).

## specyrd (optional IDE command stubs)

**specyrd** is an optional installer for **slash-command-style markdown** (or equivalent) that points agents at the same workflows as `**specy-road`** and `python scripts/…`. It does **not** replace roadmap validation or briefs, and it is **not** [Spec Kit](https://github.com/github/spec-kit)’s `specify` CLI. Optional per-milestone folders named `planning/<node-id>/` in this kit are **this repo’s** overview/plan/tasks files — unrelated to that tool.

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

Stubs only contain instructions to run `**specy-road**` / `**scripts/**` from the repository root (for example `specy-road validate`, `specy-road brief <NODE_ID> -o work/brief-<NODE_ID>.md`). Canonical behavior stays in the CLI and scripts.

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

1. **Author** — Edit roadmap JSON chunks under `[roadmap/](roadmap/)` (listed in `manifest.json`). See [docs/roadmap-authoring.md](docs/roadmap-authoring.md).
2. **Validate** — Run `python scripts/validate_roadmap.py` (or `specy-road validate`).
3. **Publish views** — Regenerate the root index: `python scripts/export_roadmap_md.py` (writes `roadmap.md` only; phase `.json` files are source).
4. **Focus a task** — `python scripts/generate_brief.py <NODE_ID> -o work/brief-<NODE_ID>.md` and implement against `[shared/](shared/README.md)` contracts cited for that node.
5. **Parallel or roadmap-driven branches** — Follow [docs/git-workflow.md](docs/git-workflow.md): branch `feature/rm-<codename>`, **first commit** registers in `[roadmap/registry.yaml](roadmap/registry.yaml)`, then implement.
6. **Heavy / risky milestones** — Optionally add `[planning/<node-id>/](planning/README.md)` (`overview.md`, `plan.md`, `tasks.md`) from templates; the roadmap remains canonical.
7. **Optional IDE commands** — If you use Cursor, Claude Code, or another flow, run `[specyrd init](#specyrd-optional-ide-command-stubs)` to add thin command stubs; they call the same `specy-road` / `scripts/` commands as above.

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


| Path                             | Role                                                                                             |
| -------------------------------- | ------------------------------------------------------------------------------------------------ |
| `[constitution/](constitution/)` | Purpose and principles (norms, not machine-enforced)                                             |
| `[constraints/](constraints/)`   | Enforceable rules and machine-readable limits                                                    |
| `[roadmap/](roadmap/)`           | Canonical `manifest.json`, JSON chunk files (e.g. `phases/*.json`), `registry.yaml`                 |
| `[shared/](shared/)`             | Contracts to cite from tasks                                                                     |
| `[planning/](planning/)`         | Optional per-node overview/plan/tasks                                                              |
| `[templates/](templates/)`       | Milestone stubs and checklists                                                                   |
| `[scripts/](scripts/)`           | Validators, brief helper, markdown export                                                        |
| `[specy_road/](specy_road/)`     | Package; `specy-road` CLI (validators, brief, export) and optional `specyrd` (IDE command stubs) |
| `[docs/](docs/)`                 | Architecture, workflows, philosophy                                                              |


`[vision.md](vision.md)` states product vision; `[roadmap.md](roadmap.md)` is a generated index from the merged graph (Gate column, etc.).

## Related material

- [Spec-Kit](https://github.com/github/spec-kit) — inspiration only  
- [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) — optional AI tooling ideas for application repositories

## License

MIT — see [LICENSE](LICENSE).