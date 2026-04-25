# Registry hydration from remote feature refs (PM GUI)

## Context

The PM Gantt loads [`roadmap/registry.yaml`](../../specy_road/bundled_scripts/roadmap_gui_lib.py) from the **working tree at HEAD**. With the default `do-next-available-task` flow, active claims are committed and pushed on the integration branch first, so `HEAD` usually already reflects in-progress work after `git pull`. Remote overlay exists to fill visibility gaps when local HEAD is behind or when teams still use feature-only registration patterns.

### Integration-branch registration (recommended)

The default **`specy-road do-next-available-task`** flow **commits `registry.yaml` on the integration branch** before creating `feature/rm-*`. After **`git pull`** (or auto-ff), **HEAD** already contains active rows — PMs see claims without depending on overlay. **Overlay** remains useful for **feature-only** registration (older or manual flows), or when a developer has not pushed the integration branch yet.

## Remote registry overlay (default on; gated)

In the PM Gantt **Settings** drawer, configure **Git remote** (GitHub or GitLab: repo slug and token)—always **per resolved project root**, not a shared global—and run **Test Git** once successfully. **“Merge registry from remote feature branches”** (**`pm_gui.registry_remote_overlay`** in [`~/.specy-road/gui-settings.json`](../../specy_road/bundled_scripts/roadmap_gui_settings.py)) defaults to **on** for new GUI profiles so PMs on the integration branch see in-flight claims after **`git fetch`**. You can turn it off per repo; the flag can follow the **PM GUI** global/per-repo toggle like other `pm_gui.*` options. The server persists **`git_remote_tested_ok`** per repo; changing effective Git remote fields clears that flag. Optional env override: **`SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY=0`** forces off; **`=1`** forces on (e.g. CI) and skips the Test Git gate.

**Local-first response:** `GET /api/roadmap` returns the outline and registry **from the current working tree and last-known remote-tracking refs** without blocking on a `git fetch` in the same request. Best-effort `git fetch` and integration-branch auto-FF run **after** the response (via background tasks). The merged registry and PR/MR hints can **lag by one refresh** until the next `GET /api/roadmap` after fetch completes. The JSON may include **`sync: { "scheduled": true }`** when deferred sync was queued.

When enabled, [`GET /api/roadmap`](../../specy_road/gui_app_routes_core.py) **merges** registry entries from **remote-tracking** refs without checking them out:

```bash
git show refs/remotes/<remote>/<integration_branch>:roadmap/registry.yaml
git show refs/remotes/<remote>/feature/rm-<codename>:roadmap/registry.yaml
```

Implementation: [`specy_road/registry_remote_overlay.py`](../../specy_road/registry_remote_overlay.py) (integration ref + feature refs); fingerprint material for integration vs feature refs: [`specy_road/pm_integration_registry.py`](../../specy_road/pm_integration_registry.py).

**Precedence:** entries from **HEAD** win on duplicate **`node_id`**; then **`refs/remotes/<remote>/<integration_branch>`** fills gaps; then **`refs/remotes/.../feature/rm-*`** fills remaining gaps. That way claims that exist **only** on the remote integration branch (e.g. after `do-next-available-task` registration before a local `git pull`) still appear in the PM API after **`git fetch`**, without requiring a dirty-tree fast-forward.

**Limits:** max refs scanned (default **48**, override with **`SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY_MAX_REFS`**), total time budget (default **5s**, **`SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY_BUDGET_S`**), per-`git show` timeout. Invalid YAML on a ref is skipped.

**Payload:** `registry`, `registry_by_node`, `pr_hints`, and `git_enrichment` use the **merged** view when overlay is active. The response may include **`registry_overlay`** (scan counts) plus **`registry_overlay.last_auto_fetch_attempt`** (`ok`, `reason`, `step`, `error`, timestamp) so PMs can see when background `git fetch` failed.

When integration auto-ff is enabled, **`integration_branch_auto_ff`** may also include **`last_auto_ff_attempt`** with the same status shape (`ok`, `reason`, `step`, `error`, timestamp). Failures remain best-effort (the API still responds), but metadata and logs now surface stale-sync causes.

**Fingerprints:** Both `GET /api/roadmap` and [`/api/roadmap/fingerprint`](../../specy_road/gui_app_routes_core.py) return a **narrow** `fingerprint` (for `X-PM-Gui-Fingerprint` on mutating requests) and a **broad** `view_fingerprint` that includes remote **`feature/rm-*`** tips and the **`roadmap/registry.yaml`** blob (or integration ref tip) on **`refs/remotes/<remote>/<integration_branch>`** when overlay is enabled. The **PM Gantt** compares **`view_fingerprint`** on the polling interval (and once shortly after first paint) to reload the view after remote-only registry / ref changes **without** local file edits. The narrow token does not track ref-only changes by design (see `specy_road/pm_gui_fingerprint.py`).

**Fetch cadence:** When the overlay is active, a best-effort **`git fetch`** for the configured remote still runs on a cooldown (**5s** by default, **`SPECY_ROAD_GUI_REGISTRY_FETCH_INTERVAL_S`**) and is **not** synchronous with building the `GET /api/roadmap` body; it is triggered from the same **deferred** path as the GUI’s fingerprint polling. Set **`SPECY_ROAD_GUI_REGISTRY_AUTO_FETCH=0`** to disable automatic fetch (you must run **`git fetch`** yourself in that case).

**Security / network:** Overlay reads only **local** git objects after fetch; the Git remote **Test Git** call uses the forge HTTPS API (GitHub/GitLab), not arbitrary hosts.

## Remote tip author (always-on enrichment)

Independently of overlay, when a **registry row** (from HEAD or merged overlay) includes a **`branch`**, the API may add **`remote_tip`** enrichment from `git log -1` on `refs/remotes/<remote>/<branch>`—see [pm-gantt-registry-checkout.md](pm-gantt-registry-checkout.md).

See [pm-workflow.md](../pm-workflow.md) for PM-oriented usage.
