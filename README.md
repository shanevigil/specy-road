# specy-road

**Roadmap-first coordination** for human teams and coding agents: one canonical graph for how the system evolves, clear separation between **purpose**, **principles**, and **enforceable constraints**, and optional deeper specs when a milestone needs them.

## Why use it

- **Single source of truth** — The roadmap (`roadmap/roadmap.yaml`) drives priorities, dependencies, and gates; contracts live in `shared/` and are cited from work items.
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
pip install -e ".[dev]"     # optional: editable install, pytest, specy-road CLI
```

Validate the repo and (optionally) run tests:

```bash
python scripts/validate_roadmap.py
python scripts/export_roadmap_md.py --check   # optional: markdown matches YAML
python scripts/validate_file_limits.py
pytest                                           # if dev extras installed
specy-road validate                              # same as validate_roadmap.py when CLI is installed
```

Optional git hooks: `pip install pre-commit && pre-commit install` (runs the roadmap validator).

## How to work with it

1. **Author** — Edit [`roadmap/roadmap.yaml`](roadmap/roadmap.yaml) (immutable IDs, dependencies, codenames, touch zones). See [docs/roadmap-authoring.md](docs/roadmap-authoring.md).
2. **Validate** — Run `python scripts/validate_roadmap.py` (or `specy-road validate`).
3. **Publish views** — Regenerate the index: `python scripts/export_roadmap_md.py` (root `roadmap.md` and phase files under `roadmap/phases/`).
4. **Focus a task** — `python scripts/generate_brief.py <NODE_ID> -o work/brief-<NODE_ID>.md` and implement against [`shared/`](shared/README.md) contracts cited for that node.
5. **Parallel or roadmap-driven branches** — Follow [docs/git-workflow.md](docs/git-workflow.md): branch `feature/rm-<codename>`, **first commit** registers in [`roadmap/registry.yaml`](roadmap/registry.yaml), then implement.
6. **Heavy / risky milestones** — Optionally add [`specify/<node-id>/`](specify/README.md) (`spec.md`, `plan.md`, `tasks.md`) from templates; the roadmap remains canonical.

## Where to read next

| Document | Purpose |
| -------- | ------- |
| [docs/philosophy-and-scope.md](docs/philosophy-and-scope.md) | What the kit promises and what it leaves to you |
| [docs/architecture.md](docs/architecture.md) | End-to-end flow (YAML, validation, briefs) |
| [docs/roadmap-authoring.md](docs/roadmap-authoring.md) | Editing YAML vs generated markdown |
| [docs/git-workflow.md](docs/git-workflow.md) | Branches, registry, merge-back |
| [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) | Optional patterns (CLAUDE.md, Cursor rules, MCP, etc.) for product repos—not required by the kit |
| [AGENTS.md](AGENTS.md) | Short entry for coding agents |

## Repository layout (overview)

| Path | Role |
| ---- | ---- |
| [`constitution/`](constitution/) | Purpose and principles (norms, not machine-enforced) |
| [`constraints/`](constraints/) | Enforceable rules and machine-readable limits |
| [`roadmap/`](roadmap/) | Canonical `roadmap.yaml` and `registry.yaml` |
| [`shared/`](shared/) | Contracts to cite from tasks |
| [`specify/`](specify/) | Optional per-node spec/plan/tasks |
| [`templates/`](templates/) | Milestone stubs and checklists |
| [`scripts/`](scripts/) | Validators, brief helper, markdown export |
| [`specy_road/`](specy_road/) | Package and `specy-road` CLI |
| [`docs/`](docs/) | Architecture, workflows, philosophy |

[`vision.md`](vision.md) states product vision; [`roadmap.md`](roadmap.md) is generated from YAML (Gate column, etc.).

## GitHub remote (optional)

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

Local development does not require a remote.

## Related material

- [Spec-Kit](https://github.com/github/spec-kit) — inspiration only  
- [docs/optional-ai-tooling-patterns.md](docs/optional-ai-tooling-patterns.md) — optional AI tooling ideas for application repositories

## License

MIT — see [LICENSE](LICENSE).
