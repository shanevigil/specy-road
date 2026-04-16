# PM GUI: optional integration-branch fast-forward

## Purpose

The PM Gantt reads merged roadmap **JSON** from the **working tree** at `HEAD`. [`git fetch`](../../specy_road/registry_remote_overlay.py) alone updates remote-tracking refs (used for [registry remote overlay](registry-hydration-remote-refs.md)) but does **not** move `HEAD` or refresh on-disk chunk files when teammates merge into the **integration branch** on the server.

Optional **auto fast-forward** runs (when enabled) on the same throttled cadence as fingerprint polling: **`git fetch <remote>`** then **`git merge --ff-only <remote>/<integration_branch>`**, matching the git half of [`specy_road/bundled_scripts/pm_sync.py`](../../specy_road/bundled_scripts/pm_sync.py).

## Controls

| Mechanism | Meaning |
|-----------|---------|
| **Settings** → `pm_gui.integration_branch_auto_ff` in `~/.specy-road/gui-settings.json` | Default **off**. Per-repo or global via inheritance toggles. |
| **`SPECY_ROAD_GUI_AUTO_INTEGRATION_FF`** | `1` / `true` forces on; `0` / `false` forces off (e.g. CI). |
| **`SPECY_ROAD_GUI_INTEGRATION_FF_INTERVAL_S`** | Throttle (seconds, clamped). If unset, falls back to **`SPECY_ROAD_GUI_REGISTRY_FETCH_INTERVAL_S`**, then **5**. |

Implementation: [`maybe_auto_integration_ff`](../../specy_road/registry_remote_overlay.py). Status for the PM header (why FF did not run, or sync vs `refs/remotes/<remote>/<integration_branch>`): [`describe_integration_branch_auto_ff`](../../specy_road/pm_integration_registry.py), exposed on [`GET /api/roadmap`](../../specy_road/gui_app_routes_core.py) as **`integration_branch_auto_ff`** when the setting is on.

## Safety

- Only runs when **`git branch --show-current`** equals the resolved **integration branch** from [`roadmap/git-workflow.yaml`](../../specy_road/git_workflow_config.py) (and env overrides used by [`resolve_integration_defaults`](../../specy_road/git_workflow_config.py)).
- Requires a **clean** working tree (`git status --porcelain` empty); otherwise skipped.
- **Fast-forward only**; non-ff divergence requires a manual merge/rebase (same as `specy-road pm-sync` failure mode).

## Relation to registry overlay

- **Overlay:** merge `registry.yaml` from **`refs/remotes/<remote>/<integration_branch>`** and from **`refs/remotes/<remote>/feature/rm-*`** without checkout — see [registry-hydration-remote-refs.md](registry-hydration-remote-refs.md). That updates **registry-driven** fields in the PM UI (claims, Dev column, locks) from **`git fetch`** even when auto-ff does not run (e.g. dirty tree).
- **Integration auto-ff:** updates **local** `HEAD` and on-disk roadmap **JSON** for the integration trunk. Use it when you want the **merged graph files** to match the remote without a manual pull; registry visibility does not depend on it when overlay is on.

Both paths share **`_GIT_SYNC_LOCK`** in [`registry_remote_overlay.py`](../../specy_road/registry_remote_overlay.py) so `git fetch` / merge steps do not overlap per repository.
