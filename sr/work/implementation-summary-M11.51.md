# Implementation summary — M11.51 `dashboard-safe-saves`

## What changed

- **A1 (safe saves):** `GET /api/planning/file` and `GET /api/workspace/file` now return `content_hash` (sha256 of the file's bytes). `PUT` to either accepts an `X-Base-Content-Hash` header; when the file on disk no longer matches it, the save is refused with `409` and `detail = {message, content_hash, current_content}`, and nothing is written. A successful `PUT` returns the new `content_hash`. A `PUT` without the header writes unconditionally, as before, so scripts and file creation keep working. The client (`gui/pm-gantt/src/api.ts`) records the hash from each read and save per route+path, sends it on the next save, and turns a 409 into `FileChangedOnDiskError`. Every editor that calls `savePlanningFile` / `saveSharedFile` already shows a thrown error's message, so the conflict appears there and no component changed. Because the hash is sent on every later autosave, autosave keeps showing the conflict and never overwrites.
- **A2 (`--read-only`):** `specy-road gui --read-only` sets `SPECY_ROAD_GUI_READ_ONLY=1`; `create_app(read_only=None)` reads it (or takes it explicitly) and installs middleware that refuses every non-GET/HEAD/OPTIONS request under `/api/` with a JSON `403`. That includes POSTs that only test settings (`/llm/test`, `/git/test`, `/archives/preview`, `/research/test`); `/git/test` writes a flag, and the others are refused too so that one rule covers every route.
- **A3 (docs + JSON 404):** `docs/pm-gui.md` gains a *Read-only JSON API* section listing every GET route, the safe-save protocol, and `--read-only`. A catch-all `/api/{rest:path}` (all methods), registered after the API routers and before the SPA fallback, returns a JSON `404` instead of `index.html`.

## Touch zones (confirmed)

Used: `specy_road/gui_app_routes_planning.py`, `specy_road/gui_app_routes_workspace.py`, `specy_road/gui_app.py`, `specy_road/cli.py`, `gui/pm-gantt/src/api.ts`, `tests/`, `docs/pm-gui.md`. No change outside them.

## Known limits / follow-ups (outside the touch zones)

- **The packaged UI bundle is not rebuilt.** `specy_road/pm_gantt_static/` is tracked and outside the touch zones, so the shipped SPA keeps the old client, which sends no hash, until someone runs `npm run build` in `gui/pm-gantt/`. Until then the server-side 409 only protects clients that send the header. The build was verified into a scratch directory, not the tracked one.
- **`--read-only` does not stop the opt-in background sync.** `GET /api/roadmap` and `/roadmap/fingerprint` schedule `git fetch` and integration auto-FF when those **Settings** are on (off by default; `gui_app_routes_core.py`). The docs say so.
- `GET /api/workspace/files` creates `shared/` or `work/` when missing (existing behaviour, left unchanged).
- With built static assets absent, the JSON 404 already came from FastAPI; the catch-all makes it the same with them present.
- An existing route called with an unregistered method (for example `DELETE /api/planning/file`) now gets `404` from the catch-all instead of `405`.

## Verification

- `python -m pytest -n 8 -q` — full suite, 3215 passed, 2 skipped (a serial run exceeded the harness's 20-minute background limit and was stopped, so the parallel run is the one that counts)
- `python -m pytest tests/test_gui_safe_saves.py -q` — 8 passed
- `specy-road file-limits` — OK
- `gui/pm-gantt`: `npm ci`, `npm run lint` (0 errors), `npm test` (184 passed), `npx tsc -b`, `npx vite build --outDir <scratch>`
- Red-green: with `gui_app.py` reverted, all 8 new tests fail; with only the two route files reverted, the 4 A1 tests fail.

## Added

- `BASE_CONTENT_HASH_HEADER` (`gui_app_routes_planning.py`): one name for the `X-Base-Content-Hash` header, shared by both PUT routes.
- `content_hash(p)` (`gui_app_routes_planning.py`): the sha256 of the bytes on disk, returned by the GETs and PUTs and compared on save.
- `require_unchanged_since(p, base_hash)` (`gui_app_routes_planning.py`): the 409 guard both PUT routes call; it skips the check when no header is sent, to keep scripts and creates working.
- `base_hash` header parameter on `api_planning_put` and `_api_workspace_file_put`: receives the client's base hash.
- `READ_ONLY_ENV`, `_SAFE_METHODS`, `_ALL_METHODS`, `_register_read_only_guard` (`gui_app.py`): the read-only switch, the methods it lets through, and the middleware that returns 403.
- `create_app(read_only=None)` parameter: lets tests build a read-only app; `None` falls back to the env var that the CLI sets.
- `api_not_found` catch-all route (`gui_app.py`): the JSON 404 for an unknown `/api/` path.
- `--read-only` flag in `_cmd_gui` (`cli.py`): sets `SPECY_ROAD_GUI_READ_ONLY=1` for the uvicorn subprocess.
- `lastContentHash`, `FileChangedOnDiskError`, `fetchTextFile`, `saveTextFile` (`api.ts`): per-file hash memory, the conflict error the editors display, and one shared read/save path for planning and shared files.
- `tests/test_gui_safe_saves.py`: a stale save refused and a fresh save accepted, on both routes (A1); read-only serves a GET and refuses a PUT, plus read-only from the env var (A2); the JSON 404 for an unknown path with GET and POST (A3).
- Mocks: none.
