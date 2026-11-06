# PM Gantt UI — production architecture

The supported **PM dashboard** is a **FastAPI** server plus a **prebuilt React** single-page app. There is no alternate GUI tree in this repository.

## What ships

- **Server:** [`specy_road/gui_app.py`](../specy_road/gui_app.py) — JSON API for roadmap, planning files, and settings; serves the static UI from [`specy_road/pm_gantt_static/`](../specy_road/pm_gantt_static/) (package data in [`pyproject.toml`](../pyproject.toml)).
- **Frontend sources:** [`gui/pm-gantt/`](../gui/pm-gantt/) — Vite + React + TypeScript. Production assets are produced with `npm run build`, which writes into `specy_road/pm_gantt_static/` for inclusion in the wheel.
- **CLI:** `specy-road gui` starts Uvicorn with the FastAPI app. Install optional dependencies with `pip install 'specy-road[gui]'` or `'specy-road[gui-next]'` (same dependency sets; see `pyproject.toml`).

- **Archive drawer:** the toolbar's **Archive** button lists archived subtrees, offers eligible ones, and restores them. Routes live in [`specy_road/gui_app_routes_archive.py`](../specy_road/gui_app_routes_archive.py); every write carries the usual `X-PM-Gui-Fingerprint` token because archiving moves roadmap files. Two preferences under **Settings → Completed work** control the default Hide Complete state (a view filter) and auto-archiving (which moves files). See [Archiving](archiving.md).
- **Workers drawer:** the header's **Workers** button shows what each worker did, step by step, without reading the JSONL. It reads the worker records and event logs under the **main** worktree's `work/.workers/` (gitignored; see [Orchestration workers](orchestration-workers.md)) and **never writes** there: no stall sweep, no `sync --ack`. Workers are grouped by leaf; each row shows its attempt, harness/model, state and total cost (`$?` when no `usage` event reported one, never `$0`). Selecting a worker shows:
  - a **phase bar** for the latest turn — delegated → launched → first output → turn end → acked, each segment sized by its share of the known total and listed with its seconds (`unknown` when a boundary event is missing); the same numbers as `specy-road worker timeline`;
  - the worker's **usage** totals (the same sums as `specy-road worker usage`);
  - the **event list**, with tool-call lines (Claude's `(tool use)`, Cursor's `tool call …`, Codex's command/file/MCP/web-search items) labelled `tool`, and **stall markers** on `stalled` events plus a `stalled ×N` badge when any exist.

  Routes, both read-only, in [`specy_road/gui_app_routes_workers.py`](../specy_road/gui_app_routes_workers.py): `GET /api/workers` (one row per worker: id, node, harness, model, state, attempt, flags, last event, total cost) and `GET /api/workers/{id}/events` (that row plus `events`, `phases` in seconds and `usage` totals; 404 for an unknown id). The drawer reloads when opened and on **Refresh**.
- **Last worked column:** the outline shows when each leaf was last worked on, **derived from git history** (no stored file) via the `activity` map on `GET /api/roadmap`; see [Archiving](archiving.md#last-worked-on).

## Read-only JSON API

Scripts may read the dashboard's state through these `GET` routes (all under `/api/`):

| Route | Returns |
| --- | --- |
| `/health` | `{"status": "ok"}` |
| `/repo` | repo root and settings id |
| `/roadmap`, `/roadmap/fingerprint` | the graph with rollups and activity; the polling fingerprints |
| `/governance-completion`, `/git-workflow-status` | vision/constitution completeness; branch and registry status |
| `/planning/{node_id}/artifacts` | the node's planning sheet path and its ancestors' |
| `/planning/file?path=…`, `/workspace/file?path=…` | `{path, content, content_hash}` for a planning file or a `shared/` file |
| `/workspace/files?prefix=shared\|work` | file listing |
| `/settings`, `/publish/status` | GUI settings (secrets masked); publish status |
| `/archives`, `/archives/{id}`, `/archives/{id}/nodes` | archived subtrees |
| `/brainstorm/sessions`, `/brainstorm/session` | brainstorm sessions |
| `/workers`, `/workers/{id}/events` | worker rows and event logs |

An unknown `/api/…` path returns a JSON `404` (`{"detail": "no API route …"}`), never the HTML shell.

- **Safe saves:** `content_hash` is the sha256 of the file's bytes. Send it back as `X-Base-Content-Hash` on `PUT` to the same route; if the file changed on disk since, the save is refused with `409` and `detail.current_content` / `detail.content_hash`, and nothing is written. The UI sends it automatically and shows the conflict instead of overwriting. A `PUT` without the header writes unconditionally, as before.
- **Publish** (`POST /api/publish`): regenerates `roadmap.md` and `roadmap-context.md` from the graph before committing, so the pushed commit passes `export --check` and `digest --check`. It refuses with `400`, before staging anything, when the graph does not validate or no git remote is configured (`/publish/status` then reports `blocked_reason: "no_remote"`).
- **`specy-road gui --read-only`:** serves every `GET` and refuses every other method under `/api/` with `403`, including POSTs that only test settings. It does not switch off the opt-in background `git fetch` / integration auto-FF that `GET /api/roadmap` schedules (**Settings**; off by default).

## How to use it and install it

- **End-user install + everyday usage** (consumer-side; `specy-road gui`):
  [install-and-usage.md](install-and-usage.md).
- **Day-to-day PM usage** (browser workflow, what you see in the UI):
  [pm-workflow.md](pm-workflow.md).
- **Rebuilding the SPA from source** (toolkit contributors only): see
  [contributor-guide.md](contributor-guide.md) (section *PM Gantt UI build
  & install*).

Contributors editing React code: rebuild from `gui/pm-gantt/` or use the
Vite dev server with a separate Uvicorn process; details are in
[contributor-guide.md](contributor-guide.md).

## Historical note

The older Streamlit-based dashboard was removed. The toolkit standard is the stack above only.
