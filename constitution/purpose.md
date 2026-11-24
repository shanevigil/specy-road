# Purpose

**specy-road** is a roadmap-first coordination **kit** (Python package + validators + optional PM UI) that product teams install to govern three things in a repository:

- **Its plan** — a canonical roadmap graph, contracts and planning narrative that live alongside the code.
- **Its multi-agent execution** — workers launched on the team's agent CLIs, a roster naming which harnesses and models may fill each role, review delegation to fresh sessions, and grind sessions that work through ready leaves. These are part of the product, not add-ons.
- **Its review trail** — recorded review bound to a commit, and whoever implements does not approve.

The team picks its IDE, agent CLIs and models; specy-road records the choice in the roster, and model profiles are data the team chooses from.

specy-road is not a CI system; not a hosted service; not an IDE or editor plugin; not an agent harness (it launches agent CLIs and does not replace them).

This repository ships the **tool**; consumer projects own their own `roadmap/`, `constitution/`, and `shared/` (see `specy-road init project`).
