# Git workflow and multi-agent coordination

This document is product-agnostic. Adapt branch names (`main` / `dev`) to your org; the **invariants** are registration, touch zones, and non-overlapping active claims.

## Branch naming

| Kind | Pattern | Example |
|------|---------|---------|
| Roadmap-driven feature | `feature/rm-<codename>` | `feature/rm-roadmap-ci` |
| Non-roadmap fix | `fix/<slug>` | `fix/validator-path` |
| Non-roadmap feature | `feature/<slug>` | `feature/docs-index` |

`<codename>` must match the milestone codename in the roadmap graph (chunk files under [`roadmap/`](../roadmap/); see [`manifest.json`](../roadmap/manifest.json)) — kebab-case, globally unique.

## Before implementation

1. Confirm **gates** and dependencies for your milestone (see root/index or generated tables).
2. Read [`roadmap/registry.yaml`](../roadmap/registry.yaml) — no overlapping **touch zones** with active entries (coordinate with PM / integration lead if unsure).
3. Create branch from your integration branch (e.g. `dev`): `git checkout -b feature/rm-<codename>`.

## First-commit registration (mandatory)

On a roadmap-driven branch, the **first commit** must register work—**no implementation** before that:

1. Add a row to **`roadmap/registry.yaml`** (or, in an application repo, `docs/roadmap-status.md` per team convention) with: codename, `node_id`, branch `feature/rm-<codename>`, touch zones, optional `started` date.
2. Commit message: `chore(rm-<codename>): register as in-progress`

## While working

- Stay within declared **touch zones** unless explicitly expanding scope with team agreement.
- Prefer **git worktrees** for parallel agents when two items could touch disjoint paths.

## Merge back

1. Remove your registry entry (or table row) before merge.
2. Merge via PR/MR; green validation (e.g. `specy-road validate`) should pass.
3. Delete the feature branch after merge.

## Correcting merged work: revert vs follow-up

On a shared integration branch, **do not rewrite history** others may have pulled (avoid
`git push --force` to “un-merge”).

| Intent | Safer pattern |
| --- | --- |
| Remove the effect of a bad merge from `main` | Open a **revert** PR (revert the merge commit). History stays linear and auditable. |
| Improve code that is already merged | Branch from current `main` and land a **follow-up** PR (`fix/...`, `feature/...`, or a new roadmap-driven branch if the PM tracks it). |

Roadmap bookkeeping (registry, node status, follow-up tasks) lives in
[dev-workflow.md](dev-workflow.md).

## Roles

| Role | Responsibility |
|------|------------------|
| PM / Director | Specs, contracts, roadmap authoring — stays far ahead of execution |
| Developer (+ agent) | Implements against contracts; owns branch through merge |

Parallelism across milestones is allowed when **dependencies** and **touch zones** permit it — `specy-road validate` is the check, not a human approval.
