# Implementation summary — M11.51 `dashboard-safe-saves`

## What changed

- **A1 (safe saves):** `GET /api/planning/file` and `GET /api/workspace/file` now return `content_hash` (sha256 of the file's bytes). `PUT` to either accepts an `X-Base-Content-Hash` header; when the file on disk no longer matches it, the save is refused with `409` and `detail = {message, content_hash, current_content}`, and nothing is written. A successful `PUT` returns the new `content_hash`. A `PUT` without the header writes unconditionally, as before, so scripts and file creation keep working. The client (`gui/pm-gantt/src/api.ts`) records the hash from each read and save per route+path, sends it on the next save, and turns a 409 into `FileChangedOnDiskError`. Every editor that calls `savePlanningFile` / `saveSharedFile` already shows a thrown error's message, so the conflict appears there and no component changed. Because the hash is sent on every later autosave, autosave keeps showing the conflict and never overwrites.
- **A2 (`--read-only`):** `specy-road gui --read-only` sets `SPECY_ROAD_GUI_READ_ONLY=1`; `create_app(read_only=None)` reads it (or takes it explicitly) and installs middleware that refuses every non-GET/HEAD/OPTIONS request under `/api/` with a JSON `403`. That includes POSTs that only test settings (`/llm/test`, `/git/test`, `/archives/preview`, `/research/test`); `/git/test` writes a flag, and the others are refused too so that one rule covers every route.
- **A3 (docs + JSON 404):** `docs/pm-gui.md` gains a *Read-only JSON API* section listing every GET route, the safe-save protocol, and `--read-only`. A catch-all `/api/{rest:path}` (all methods), registered after the API routers and before the SPA fallback, returns a JSON `404` instead of `index.html`.

## Review round 1 (Codex Sol block) — fixes

- **F1, packaged UI rebuilt:** ran `npm ci && npm run lint && npm test && npm run build` in `gui/pm-gantt/`. The rebuilt `specy_road/pm_gantt_static/` is committed: every content-hashed chunk was renamed because the index chunk changed, and `index.html` was updated. The new index chunk is 94 KB, well under CI's 900 KB budget. **Served-dashboard check:** uvicorn ran the worktree app against a scratch copy of the dogfood fixture, and headless Chromium (Python Playwright 1.64.1 in a scratch venv) opened **Vision**. The script then changed `vision.md` on disk and typed in the editor. The PUT carried `X-Base-Content-Hash` equal to the GET's `content_hash`, the server answered `409`, the footer showed "vision.md changed on disk since you opened it; your save was not written…", and the disk edit was kept. The footer prefixes the message with `FileChangedOnDiskError:` because `VisionDrawer` renders `String(e)`; the component is outside the touch zones, so it is left as is.
- **F2, one snapshot per read:** `read_snapshot(p)` reads the bytes once and returns the text, with the same `\r\n`/`\r` → `\n` translation `read_text` gave before, and the sha256 of those bytes. Both GET routes use it, and so does the 409 payload in `require_unchanged_since`, so `current_content` and `content_hash` there also describe one version. The regression test `test_get_content_and_hash_come_from_one_snapshot` patches `Path.read_text`/`read_bytes` to write the file right after the request's first read of it. It then asserts that the GET's content and hash both describe the original, and that a PUT with that hash gets `409` and leaves the disk edit in place.

## Touch zones (confirmed)

Used: `specy_road/gui_app_routes_planning.py`, `specy_road/gui_app_routes_workspace.py`, `specy_road/gui_app.py`, `specy_road/cli.py`, `gui/pm-gantt/src/api.ts`, `specy_road/pm_gantt_static/` (added to the touch zones for F1), `tests/`, `docs/pm-gui.md`. No change outside them.

## Known limits / follow-ups (outside the touch zones)
- **`--read-only` does not stop the opt-in background sync.** `GET /api/roadmap` and `/roadmap/fingerprint` schedule `git fetch` and integration auto-FF when those **Settings** are on (off by default; `gui_app_routes_core.py`). The docs say so.
- `GET /api/workspace/files` creates `shared/` or `work/` when missing (existing behaviour, left unchanged).
- With built static assets absent, the JSON 404 already came from FastAPI; the catch-all makes it the same with them present.
- An existing route called with an unregistered method (for example `DELETE /api/planning/file`) now gets `404` from the catch-all instead of `405`.

## Verification

- `python -m pytest -n 8 -q` — full suite, 3217 passed, 2 skipped in round 1 (3215 before; a serial run exceeded the harness's 20-minute background limit and was stopped, so the parallel run is the one that counts)
- `python -m pytest tests/test_gui_safe_saves.py -q` — 10 passed (round 1)
- Served-dashboard stale-save check (Playwright against uvicorn, see F1) — PASS
- `specy-road file-limits` — OK
- `gui/pm-gantt`: `npm ci`, `npm run lint` (0 errors), `npm test` (184 passed), `npm run build` (into the tracked `specy_road/pm_gantt_static/`, round 1)
- Red-green: with `gui_app.py` reverted, all 8 original tests fail; with only the two route files reverted, the 4 A1 tests fail; with the route files at `808d64fd` (separate reads), the 2 snapshot tests fail.

## Added

- `BASE_CONTENT_HASH_HEADER` (`gui_app_routes_planning.py`): one name for the `X-Base-Content-Hash` header, shared by both PUT routes.
- `content_hash(p)` (`gui_app_routes_planning.py`): the sha256 of the bytes on disk, returned by the PUTs after a write.
- `read_snapshot(p)` (`gui_app_routes_planning.py`, round 1): text and hash from one byte read, used by both GETs and the 409 payload (F2).
- `require_unchanged_since(p, base_hash)` (`gui_app_routes_planning.py`): the 409 guard both PUT routes call; it skips the check when no header is sent, to keep scripts and creates working.
- `base_hash` header parameter on `api_planning_put` and `_api_workspace_file_put`: receives the client's base hash.
- `READ_ONLY_ENV`, `_SAFE_METHODS`, `_ALL_METHODS`, `_register_read_only_guard` (`gui_app.py`): the read-only switch, the methods it lets through, and the middleware that returns 403.
- `create_app(read_only=None)` parameter: lets tests build a read-only app; `None` falls back to the env var that the CLI sets.
- `api_not_found` catch-all route (`gui_app.py`): the JSON 404 for an unknown `/api/` path.
- `--read-only` flag in `_cmd_gui` (`cli.py`): sets `SPECY_ROAD_GUI_READ_ONLY=1` for the uvicorn subprocess.
- `lastContentHash`, `FileChangedOnDiskError`, `fetchTextFile`, `saveTextFile` (`api.ts`): per-file hash memory, the conflict error the editors display, and one shared read/save path for planning and shared files.
- `tests/test_gui_safe_saves.py`: a stale save refused and a fresh save accepted, on both routes (A1); read-only serves a GET and refuses a PUT, plus read-only from the env var (A2); the JSON 404 for an unknown path with GET and POST (A3).
- `test_get_content_and_hash_come_from_one_snapshot` (round 1, both routes): the F2 regression, through the public API.
- Rebuilt `specy_road/pm_gantt_static/` (round 1): the shipped UI with the hash-aware client (F1).
- Mocks: the snapshot test patches `Path.read_text`/`Path.read_bytes` (stdlib, inside a scoped `MonkeyPatch.context()`) to simulate an editor writing mid-request; no private names are patched.
