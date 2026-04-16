# Git workflow and multi-agent coordination

This document is product-agnostic. Adapt branch names (`main` / `dev`) to your org; the **invariants** are registration, touch zones, and non-overlapping active claims.

## Machine-readable contract (`roadmap/git-workflow.yaml`)

The scaffold includes **`roadmap/git-workflow.yaml`**: your team’s **integration branch** (daily trunk) and **remote** name. The specy-road CLI (`specy-road sync`, `do-next-available-task`) and the **PM Gantt** read this file unless you override with `--base` / `--remote` or optional environment variables (`SPECY_ROAD_INTEGRATION_BRANCH`, `SPECY_ROAD_REMOTE`). If the file is missing, tools fall back to `main` / `origin` and may warn.

**Precedence:** CLI flags → env → `roadmap/git-workflow.yaml` → defaults.

Keep this file accurate so PMs see correct git status in the dashboard and validation can warn when local refs are stale (for example after `git fetch`).

## PM Gantt and `registry.yaml` visibility

The **PM Gantt** reads **`roadmap/registry.yaml` from the current working tree** (same repo root as other `specy-road` commands: discover from cwd / git, or **`SPECY_ROAD_REPO_ROOT`**), then **merges** registry rows from remote-tracking **`feature/rm-*`** refs when **remote registry overlay** is enabled in PM Gantt **Settings** (default **on** for new GUI profiles; requires Git remote + **Test Git**). See [design-notes/registry-hydration-remote-refs.md](design-notes/registry-hydration-remote-refs.md). Set **`SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY=0`** to force HEAD-only behavior without changing saved settings.

On the **integration branch**, the on-disk file often has **`entries: []`** while developers hold active claims only on **`feature/rm-*`** branches (first-commit registration). **Overlay** still exposes those rows in the GUI after **`git fetch`**. The outline **green accent** appears only when your **checked-out branch name** matches a row’s **`branch`** field — typical for **developers** on the feature branch, not for **PMs** on the integration branch; see [pm-workflow.md](pm-workflow.md#monitoring-in-progress-work-while-on-the-integration-branch) and [design-notes/pm-gantt-registry-checkout.md](design-notes/pm-gantt-registry-checkout.md).

**Examples** (schema: [`../specy_road/templates/project/schemas/git-workflow.schema.json`](../specy_road/templates/project/schemas/git-workflow.schema.json)):

`main` as the daily trunk:

```yaml
version: 1
integration_branch: main
remote: origin
```

`dev` as the daily trunk (feature work merges here before promotion to `staging` / `main`):

```yaml
version: 1
integration_branch: dev
remote: origin
```

## Branch naming

| Kind | Pattern | Example |
|------|---------|---------|
| Roadmap-driven feature | `feature/rm-<codename>` | `feature/rm-roadmap-ci` |
| Non-roadmap fix | `fix/<slug>` | `fix/validator-path` |
| Non-roadmap feature | `feature/<slug>` | `feature/docs-index` |

`<codename>` must match the milestone codename in the roadmap graph (JSON chunks under `roadmap/`; see [`roadmap/manifest.json`](../specy_road/templates/project/roadmap/manifest.json) in a scaffolded project) — kebab-case, globally unique.

## Before implementation

1. Confirm **gates** and dependencies for your milestone (see root/index or generated tables).
2. Read `roadmap/registry.yaml` in your application repository — no overlapping **touch zones** with active entries (coordinate with PM / integration lead if unsure). Example layout: [`roadmap/registry.yaml`](../specy_road/templates/project/roadmap/registry.yaml). Maintainers working on this toolkit use the dogfood copy: [`tests/fixtures/specy_road_dogfood/roadmap/registry.yaml`](../tests/fixtures/specy_road_dogfood/roadmap/registry.yaml).
3. Create the roadmap-driven branch from your integration branch (e.g. `dev`): `git checkout -b feature/rm-<codename>`.

## First-commit registration (mandatory)

On that new branch, the **first commit** registers work only — **no implementation** in that commit:

1. Add a row to **`roadmap/registry.yaml`** (or, in an application repo, `docs/roadmap-status.md` per team convention) with: codename, `node_id`, branch `feature/rm-<codename>`, touch zones, optional `started` date.
2. Commit message: `chore(rm-<codename>): register as in-progress`

Only **after** that registration commit should you add implementation commits.

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
