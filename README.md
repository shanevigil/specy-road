# specy-road

Roadmap-first coordination for humans and AI agents: **immutable IDs**, **touch zones**, optional structured planning, and separated **purpose / principles / constraints**.

## Decision: greenfield (no Spec-Kit fork)

This repository is a **new system**. It does **not** fork [github/spec-kit](https://github.com/github/spec-kit). Spec-Kit remains a useful reference for optional spec → plan → tasks flows and context discipline; specy-road centers the **roadmap graph** and multi-agent **registry** instead.

## Layout

| Path | Role |
|------|------|
| [`constitution/`](constitution/) | Purpose and principles (no operational enforcement here) |
| [`constraints/`](constraints/) | Enforceable rules + machine-readable limits |
| [`roadmap/`](roadmap/) | Canonical `roadmap.yaml` + `registry.yaml` |
| [`shared/`](shared/) | Contracts (API, data model, policies) — cite from tasks |
| [`specify/`](specify/) | Optional per-node spec/plan/tasks (see [`specify/README.md`](specify/README.md)) |
| [`templates/`](templates/) | Milestone stubs and authoring checklists |
| [`scripts/`](scripts/) | Validators and brief helper |
| [`docs/`](docs/) | Git workflow and coordination |

## Quick start (local)

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/validate_roadmap.py
python scripts/generate_brief.py M1.1
```

## GitHub remote (optional)

Create an empty repository on GitHub when ready, then:

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

Local development does **not** require a remote.

## Related material

- [Spec-Kit](https://github.com/github/spec-kit) — inspiration only  
- [`project-design-for-claudeandcursor.md`](project-design-for-claudeandcursor.md) — complementary AI project patterns  

## License

MIT — see [`LICENSE`](LICENSE).
