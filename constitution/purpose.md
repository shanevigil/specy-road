# Purpose

**specy-road** is a roadmap-first coordination **kit** (Python package + validators + optional PM UI) that product teams install so a canonical graph, contracts, and planning narrative live alongside their code. It prescribes a review contract and role separation — recorded review bound to a commit, and whoever implements does not approve — while leaving the choice of IDE, agent, and model to the team.

This repository ships the **tool**; consumer projects own their own `roadmap/`, `constitution/`, and `shared/` (see `specy-road init project`).
