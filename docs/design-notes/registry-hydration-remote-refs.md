# Registry hydration from remote feature refs (PM GUI)

## Context

The PM Gantt loads [`roadmap/registry.yaml`](../../specy_road/bundled_scripts/roadmap_gui_lib.py) from the **working tree at HEAD**. On the **integration branch**, that file is often empty or stale while active work lives on unmerged **`feature/rm-*`** commits.

## Remote registry overlay (opt-in)

In the PM Gantt **Settings** drawer, configure **Git remote** (GitHub or GitLab: repo slug and token)—always **per resolved project root**, not a shared global—run **Test Git** once successfully, then turn on **“Merge registry from remote feature branches”** (stored under **`pm_gui.registry_remote_overlay`** in [`~/.specy-road/gui-settings.json`](../../specy_road/bundled_scripts/roadmap_gui_settings.py); that flag can follow the **PM GUI** global/per-repo toggle like other `pm_gui.*` options). The server persists **`git_remote_tested_ok`** per repo; changing effective Git remote fields clears that flag. Optional env override: **`SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY=0`** forces off; **`=1`** forces on (e.g. CI) and skips the Test Git gate.

When enabled, [`GET /api/roadmap`](../../specy_road/gui_app_routes_core.py) **merges** registry entries from **remote-tracking** branches without checking them out:

```bash
git show refs/remotes/<remote>/feature/rm-<codename>:roadmap/registry.yaml
```

Implementation: [`specy_road/registry_remote_overlay.py`](../../specy_road/registry_remote_overlay.py).

**Precedence:** entries from **HEAD** win on duplicate **`node_id`**; remote-only rows **fill gaps** so PMs on the integration branch see active claims once **`refs/remotes/.../feature/rm-*`** exist (updated by periodic **`git fetch`** below).

**Limits:** max refs scanned (default **48**, override with **`SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY_MAX_REFS`**), total time budget (default **5s**, **`SPECY_ROAD_GUI_REGISTRY_REMOTE_OVERLAY_BUDGET_S`**), per-`git show` timeout. Invalid YAML on a ref is skipped.

**Payload:** `registry`, `registry_by_node`, `pr_hints`, and `git_enrichment` use the **merged** view. The response may include **`registry_overlay`** (scan counts). **`registry_visibility`** still reflects **HEAD-only** `registry.yaml` for the dismissible banner.

**Fingerprint:** [`/api/roadmap/fingerprint`](../../specy_road/gui_app_routes_core.py) mixes in a hash of remote **`feature/rm-*`** ref tips when overlay is enabled so the UI can refresh after pushes **without** local roadmap file edits.

**Fetch cadence:** When the overlay is active, the server runs a best-effort **`git fetch`** for the configured remote on a cooldown (**5s** by default, **`SPECY_ROAD_GUI_REGISTRY_FETCH_INTERVAL_S`**), aligned with the chart **auto-refresh** interval (often 5s). Set **`SPECY_ROAD_GUI_REGISTRY_AUTO_FETCH=0`** to disable automatic fetch (you must run **`git fetch`** yourself in that case).

**Security / network:** Overlay reads only **local** git objects after fetch; the Git remote **Test Git** call uses the forge HTTPS API (GitHub/GitLab), not arbitrary hosts.

## Remote tip author (always-on enrichment)

Independently of overlay, when a **registry row** (from HEAD or merged overlay) includes a **`branch`**, the API may add **`remote_tip`** enrichment from `git log -1` on `refs/remotes/<remote>/<branch>`—see [pm-gantt-registry-checkout.md](pm-gantt-registry-checkout.md).

See [pm-workflow.md](../pm-workflow.md) for PM-oriented usage.
