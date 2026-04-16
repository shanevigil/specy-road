# PM Gantt: registry vs git checkout

## Data flow

- The FastAPI **`GET /api/roadmap`** handler loads `roadmap/registry.yaml` with [`load_registry()`](../../specy_road/bundled_scripts/roadmap_gui_lib.py) from the **repository root** resolved for the GUI ([`get_repo_root()`](../../specy_road/gui_app_helpers.py): `SPECY_ROAD_REPO_ROOT`, else roadmap discovery from cwd).
- When [**remote registry overlay**](registry-hydration-remote-refs.md) is enabled (default in GUI defaults, gated by Git remote + **Test Git**), the server **merges** `registry.yaml` from **`git show refs/remotes/<remote>/feature/rm-*:roadmap/registry.yaml`** into the payload. **`registry`**, **`registry_by_node`**, **`pr_hints`**, and **`git_enrichment`** then reflect that **merged** view. HEAD entries win on duplicate **`node_id`**; remote rows fill gaps.

## Green outline accent (developers vs PMs)

The React outline highlights a row with a **green left accent** when the named current branch (`git branch --show-current`, exposed as `git_workflow.resolved.git_branch_current`) **equals** that row’s **`branch`** value from **`registry_by_node`**.

So the accent means: **your checkout’s current branch matches this row’s registered feature branch** — the usual case for a **developer** on `feature/rm-*`. A **PM** on the **integration branch** typically **does not** get that accent for in-flight feature work (their branch is `dev` / `main`, not `feature/rm-*`), even when overlay shows the row. That is expected: use **status colors**, **Dev column**, and **MR** hints for PM visibility instead.

**Gantt bars:** the same “active feature branch” signal drives a **green bar** when the row is in progress and registered; that **green** is the bar fill (`--bar-in-progress`), not the outline **accent** color (see [pm-workflow.md](../pm-workflow.md) Colors). Selection and dependency-chain highlights use **blue** and **yellow** and override those fills.

**Dev column (outline):** Precedence is **`owner`** (registry) → **forge PR/MR author** (when `git_remote` is configured) → **author of the latest commit on the remote-tracking branch** (`refs/remotes/<remote>/<branch>`, when that ref exists after `git fetch`) → **local `git config user.name`** only when **current branch equals** that row’s registered `branch` (developer convenience on `feature/rm-*`) → branch string / `—`. Git does not record “who checked out” a branch; remote tip author is a practical proxy for PMs who stay on the integration branch.

## Why HEAD on the integration branch sometimes looks empty

The recommended flow ([registration on integration](../git-workflow.md#registration-commit-mandatory), then `feature/rm-*`) puts active rows **on the integration branch** after push — **`git pull`** on **`dev`** / **`main`** is often enough.

If a team still registers **only** on **`feature/rm-<codename>`** (legacy), the integration branch does not contain that commit until merge, so the **on-disk** file at **`dev`** can still show **`entries: []`** while work proceeds on the feature branch.

**Overlay path:** configure **Git remote** in Settings, run **Test Git**, keep **“Merge registry from remote feature branches”** on (default for new GUI profiles), and rely on periodic **`git fetch`** so `refs/remotes/<remote>/feature/rm-*` exist — see [registry-hydration-remote-refs.md](registry-hydration-remote-refs.md). You do **not** need to check out each feature branch to see registry-driven status, owners, and enrichment.

## Optional: checkout / second worktree

Checking out **`feature/rm-*`**, using a **second worktree**, or pointing the GUI at another clone where that branch is **HEAD** is useful when you want to inspect the **exact** committed `registry.yaml` and roadmap files as they exist on that branch, or when developing on that branch. It is **not** required for day-to-day PM monitoring when overlay is enabled.

## References

- [registry-hydration-remote-refs.md](registry-hydration-remote-refs.md) — overlay, fetch cadence, `registry_overlay` payload metadata.
- [pm-workflow.md](../pm-workflow.md), [git-workflow.md](../git-workflow.md), [dev-workflow.md](../dev-workflow.md).
