# PM Gantt: registry visibility vs git checkout

## Invariant (today)

- The FastAPI **`GET /api/roadmap`** handler loads `roadmap/registry.yaml` with [`load_registry()`](../../specy_road/bundled_scripts/roadmap_gui_lib.py) from the **repository root** resolved for the GUI ([`get_repo_root()`](../../specy_road/gui_app_helpers.py): `SPECY_ROAD_REPO_ROOT`, else roadmap discovery from cwd).
- The React outline highlights a row with a **green left accent** when the named current branch (`git branch --show-current`, exposed as `git_workflow.resolved.git_branch_current`) **equals** that row’s **`branch`** value from **`registry_by_node`**, which is derived only from that on-disk registry file.

So the accent means: **this working tree’s `registry.yaml` claims this node is active on the branch you have checked out** — not “someone, somewhere, has registered this milestone.”

**Dev column (outline):** Precedence is **`owner`** (registry) → **forge PR/MR author** (when `git_remote` is configured) → **author of the latest commit on the remote-tracking branch** (`refs/remotes/<remote>/<branch>`, when that ref exists after `git fetch`) → **local `git config user.name`** only when **current branch equals** that row’s registered `branch` (developer convenience on `feature/rm-*`) → branch string / `—`. Git does not record “who checked out” a branch; remote tip author is a practical proxy for PMs who stay on the integration branch.

**Registry rows on integration branch:** with **Settings → “Merge registry from remote feature branches”** (or env `SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY=1`), the server merges registry YAML from remote-tracking **`feature/rm-*`** refs into `registry_by_node` so PMs do not need to check out each feature branch. Requires **`git fetch`** so those refs exist. See [registry-hydration-remote-refs.md](registry-hydration-remote-refs.md).

## Why integration-branch checkouts look empty

The [first-commit registration](../git-workflow.md#first-commit-registration-mandatory) workflow adds `roadmap/registry.yaml` on **`feature/rm-<codename>`** before implementation. The integration branch (e.g. `dev`) does not contain that commit until merge. A PM who runs the GUI with **`dev`** checked out therefore sees **`entries: []`** (or stale rows) and **no** green accent for the task that is actually in progress on the feature branch.

This is expected given **HEAD-based** registry loading; it is easy to misread as “nothing active.”

## What we ship in specy-road (v1)

- **`registry_visibility`** on `/api/roadmap` (unless **`SPECY_ROAD_GUI_REGISTRY_VISIBILITY=0`**): flags include whether you are on the configured integration branch, how many local registry entries exist, and how many **`refs/remotes/<remote>/feature/rm-*`** refs exist (local cache after `git fetch`).
- **In-product copy**: dismissible informational banner when **integration branch + empty local registry + at least one remote feature ref**; tooltip text for the git workflow control and **row `title`** on green-accent rows explaining the rule.
- **Docs**: [pm-workflow.md](../pm-workflow.md), [dev-workflow.md](../dev-workflow.md), [git-workflow.md](../git-workflow.md).

## How a PM on `dev` can see active M.x work

1. **`git fetch`** so remote-tracking **`feature/rm-*`** refs exist.
2. **Check out the feature branch** in this clone, **or** use a **second worktree** (recommended for “monitor on `dev`, implement elsewhere”), **or** point **`SPECY_ROAD_REPO_ROOT`** / `specy-road gui --repo-root` at a clone where that branch is **HEAD**.
3. Reload the PM Gantt; `registry.yaml` at **that** HEAD shows the row and the green accent when the branch names match.

If the team needs registry merged into the integration-branch view **without** switching branches, that is a separate product decision: optional merge from **`git show <ref>:roadmap/registry.yaml`** (precedence rules, caps, opt-in flag). It is **not** required for registry schema or `specy-road validate`, which always operate on files in the tree under `--repo-root`. See [registry-hydration-remote-refs.md](registry-hydration-remote-refs.md).

## Options considered (longer term)

| Approach | Notes |
|----------|--------|
| Document + banner (shipped) | Aligns UX with the HEAD-based model; no merge semantics. |
| Second worktree / checkout | Operationally correct; always shows the true file. |
| Opt-in merge from remote `feature/rm-*` refs | Surfaces in-flight rows on integration branch; needs precedence, performance limits, and explicit opt-in. |
| “Watch branch” in GUI settings | Explicit but overlaps with worktrees; more API surface. |
