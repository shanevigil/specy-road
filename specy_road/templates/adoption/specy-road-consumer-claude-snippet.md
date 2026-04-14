## specy-road (consumer)

**Relationship:** This repository is the application. An optional root-level `specy-road/` directory is often a local clone of the upstream toolkit for reference—not the place to patch CLI, GUI, or validator behavior.

**Troubleshooting:** Separate **integration** issues (this repo’s `roadmap/`, `planning/`, env vars, wrappers) from suspected **toolkit** bugs. For toolkit bugs, produce an **upstream handoff** (repro, package version, logs)—do not edit `specy-road/**` here to “fix” the kit.

**Pointers:** CLI load order and invariants → `AGENTS.md`. GUI, repo root, and `SPECY_ROAD_REPO_ROOT` → toolkit `docs/pm-workflow.md` and package `README.md`, or optional project-specific notes (e.g. `docs/commands.md` if your team adds that file).
