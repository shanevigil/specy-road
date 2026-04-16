# Git workflow and multi-agent coordination

This document is product-agnostic. Adapt branch names (`main` / `dev`) to your org; the **invariants** are registration, touch zones, and non-overlapping active claims.

## Machine-readable contract (`roadmap/git-workflow.yaml`)

The scaffold includes **`roadmap/git-workflow.yaml`**: your team’s **integration branch** (daily trunk) and **remote** name. The specy-road CLI (`specy-road sync`, `do-next-available-task`) and the **PM Gantt** read this file unless you override with `--base` / `--remote` or optional environment variables (`SPECY_ROAD_INTEGRATION_BRANCH`, `SPECY_ROAD_REMOTE`). If the file is missing, tools fall back to `main` / `origin` and may warn.

**Precedence:** CLI flags → env → `roadmap/git-workflow.yaml` → defaults.

Keep this file accurate so PMs see correct git status in the dashboard and validation can warn when local refs are stale (for example after `git fetch`).

## PM Gantt and `registry.yaml` visibility

The **PM Gantt** reads **`roadmap/registry.yaml` from the current working tree** (same repo root as other `specy-road` commands: discover from cwd / git, or **`SPECY_ROAD_REPO_ROOT`**), then **merges** registry rows from remote-tracking **`feature/rm-*`** refs when **remote registry overlay** is enabled in PM Gantt **Settings** (default **on** for new GUI profiles; requires Git remote + **Test Git**). See [design-notes/registry-hydration-remote-refs.md](design-notes/registry-hydration-remote-refs.md). Set **`SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY=0`** to force HEAD-only behavior without changing saved settings.

**Default dev CLI path:** `specy-road do-next-available-task` **commits registration to the integration branch first**, then creates `feature/rm-*`. **Coordination contract:** with the default CLI (sync + push), that registration is also **on the remote** integration branch so the team shares one source of truth; skipping push is an explicit opt-in (see [dev-workflow.md](dev-workflow.md#agents-and-registration)). After **`git pull`** on the integration branch, **HEAD’s `registry.yaml` shows active rows** without relying on overlay. **Overlay** still helps for older flows or unpushed feature-only registration — it merges rows from remote **`feature/rm-*`** refs after **`git fetch`**. The outline **green accent** appears when your **checked-out branch name** matches a row’s **`branch`** field (usually the feature branch for implementers); see [pm-workflow.md](pm-workflow.md#monitoring-in-progress-work-while-on-the-integration-branch) and [design-notes/pm-gantt-registry-checkout.md](design-notes/pm-gantt-registry-checkout.md).

Optional field **`merge_request_requires_manual_approval`** (boolean) documents that MRs need human approval; the `finish-this-task` CLI may print a reminder.

Optional field **`require_implementation_review_before_finish`** (boolean): when **true**, `finish-this-task` requires a prior **`specy-road mark-implementation-reviewed`** (human reads `work/implementation-summary-<NODE_ID>.md` and approves in `roadmap/registry.yaml`). New scaffolds default this to **true**; omit or set **false** to allow the legacy flow (`finish-this-task` only). Schema: [`../specy_road/templates/project/schemas/git-workflow.schema.json`](../specy_road/templates/project/schemas/git-workflow.schema.json).

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
3. **Register on the integration branch, then branch:** add your row to **`roadmap/registry.yaml`** and commit **on the integration branch** (e.g. `dev`) — registration only, no implementation in that commit. Message: `chore(rm-<codename>): register as in-progress`, optionally with CI-skip suffixes matching automation: `[skip ci] [ci skip] ***NO_CI***` (see [`do-next-available-task`](dev-workflow.md)). Push if others need visibility (the automated CLI pushes by default after registering). Then: `git checkout -b feature/rm-<codename>` and implement on that branch. (Automated path: [`do-next-available-task`](dev-workflow.md) does brief → register on integration → push integration branch → create feature branch → prompt.)

Teams using `docs/roadmap-status.md` instead of YAML should follow the same **register on integration before feature work** discipline.

## Registration commit (mandatory)

The **registration commit** contains **only** the registry update (or equivalent status row):

1. Add a row with: codename, `node_id`, branch `feature/rm-<codename>`, non-empty touch zones, optional `started` date.
2. Commit on the **integration branch** first; then create **`feature/rm-<codename>`** for implementation commits.

`specy-road do-next-available-task` appends common CI-skip tokens to the registration commit message by default (best-effort; your pipeline may still require `paths` / `paths-ignore` rules). Manual commits should use the same pattern if you want consistent CI behavior.

Only **after** registration (and branching) should you add implementation commits on the feature branch.

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
