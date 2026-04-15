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

Implementation: [`maybe_auto_integration_ff`](../../specy_road/registry_remote_overlay.py).

## Safety

- Only runs when **`git branch --show-current`** equals the resolved **integration branch** from [`roadmap/git-workflow.yaml`](../../specy_road/git_workflow_config.py) (and env overrides used by [`resolve_integration_defaults`](../../specy_road/git_workflow_config.py)).
- Requires a **clean** working tree (`git status --porcelain` empty); otherwise skipped.
- **Fast-forward only**; non-ff divergence requires a manual merge/rebase (same as `specy-road pm-sync` failure mode).

## Relation to registry overlay

- **Overlay:** merge `registry.yaml` from **`refs/remotes/<remote>/feature/rm-*`** without checkout — see [registry-hydration-remote-refs.md](registry-hydration-remote-refs.md).
- **Integration auto-ff:** updates **local** `HEAD` and files for the integration trunk. Use one or both depending on whether you need remote feature registry rows vs. an up-to-date working tree for merged roadmap JSON.

Both paths share **`_GIT_SYNC_LOCK`** in [`registry_remote_overlay.py`](../../specy_road/registry_remote_overlay.py) so `git fetch` / merge steps do not overlap per repository.
