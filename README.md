# specy-road

Roadmap-first coordination for humans and AI agents: **immutable IDs**, **touch zones**, optional structured planning, and separated **purpose / principles / constraints**.

This repository is a **new system** based on [github/spec-kit](https://github.com/github/spec-kit). Spec-Kit remains a useful reference for optional spec → plan → tasks flows and context discipline; specy-road centers product manager lead, spec driven development by implementing a **roadmap graph** and multi-agent coding by implennting a m **registry** instead.

## Layout


| Path                             | Role                                                                                                |
| -------------------------------- | --------------------------------------------------------------------------------------------------- |
| `[constitution/](constitution/)` | Purpose and principles (no operational enforcement here)                                            |
| `[constraints/](constraints/)`   | Enforceable rules + machine-readable limits                                                         |
| `[roadmap/](roadmap/)`           | Canonical `roadmap.yaml` + `registry.yaml`                                                          |
| `[shared/](shared/)`             | Contracts (API, data model, policies) — cite from tasks                                             |
| `[specify/](specify/)`           | Optional per-node spec/plan/tasks (see `[specify/README.md](specify/README.md)`)                    |
| `[templates/](templates/)`       | Milestone stubs and authoring checklists                                                            |
| `[scripts/](scripts/)`           | Validators, brief helper, markdown export, file limits                                              |
| `[specy_road/](specy_road/)`     | Package and `specy-road` CLI (`pip install -e .`)                                                   |
| `[docs/](docs/)`                 | Git workflow, [architecture](docs/architecture.md), roadmap authoring, bootstrap backlog            |
| `[vision.md](vision.md)`         | Short product vision (see also `constitution/`)                                                     |
| `[roadmap.md](roadmap.md)`       | Generated index with **Gate** column — run `python scripts/export_roadmap_md.py` after editing YAML |


## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e ".[dev]"    # optional: editable install, pytest, specy-road CLI
python scripts/validate_roadmap.py
python scripts/export_roadmap_md.py --check   # optional: ensure markdown matches YAML
python scripts/validate_file_limits.py
python scripts/generate_brief.py M1.1
pytest                      # if dev extras installed
specy-road validate         # same as validate_roadmap.py when CLI installed
```

See `[docs/roadmap-authoring.md](docs/roadmap-authoring.md)` for YAML vs generated markdown. Optional git hooks: `pip install pre-commit && pre-commit install` (runs the roadmap validator).

## GitHub remote (optional)

Create an empty repository on GitHub when ready, then:

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

Local development does **not** require a remote.

## Related material

- [Spec-Kit](https://github.com/github/spec-kit) — inspiration only  
- `[project-design-for-claudeandcursor.md](project-design-for-claudeandcursor.md)` — complementary AI project patterns

## License

MIT — see `[LICENSE](LICENSE)`.