"""FastAPI server for the PM Gantt SPA.

Includes roadmap CRUD, planning files, and settings endpoints.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles


from specy_road.gui_app_api import make_api_router  # noqa: E402
from specy_road.gui_app_routes_workers import register_worker_routes

_PKG_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _PKG_DIR / "pm_gantt_static"

READ_ONLY_ENV = "SPECY_ROAD_GUI_READ_ONLY"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def _register_read_only_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def refuse_writes(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method not in _SAFE_METHODS and request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=403,
                content={"detail": "server is read-only (specy-road gui --read-only)"},
            )
        return await call_next(request)


def create_app(read_only: bool | None = None) -> FastAPI:
    if read_only is None:
        read_only = os.environ.get(READ_ONLY_ENV) == "1"
    app = FastAPI(title="specy-road PM Gantt API", version="1.0.0")
    if read_only:
        _register_read_only_guard(app)
    app.add_middleware(
        CORSMiddleware,
        # Loopback only. The built UI is served from this same origin, so the
        # regex exists for the Vite dev server. With `allow_origins=["*"]` and
        # credentials, Starlette echoes back whichever Origin asked, so any
        # page the user had open could read `/api/settings` — which carries
        # their LLM and git tokens.
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(make_api_router())
    workers = APIRouter(prefix="/api")
    register_worker_routes(workers)
    app.include_router(workers)

    # Registered before the SPA fallback so scripts get JSON, not the HTML shell.
    @app.api_route("/api/{rest:path}", methods=_ALL_METHODS, include_in_schema=False)
    def api_not_found(rest: str) -> None:
        raise HTTPException(status_code=404, detail=f"no API route /api/{rest}")

    if _STATIC_DIR.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=_STATIC_DIR / "assets"),
            name="assets",
        )

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            index = _STATIC_DIR / "index.html"
            if full_path == "" or full_path == "/":
                return FileResponse(index)
            target = (_STATIC_DIR / full_path).resolve()
            try:
                target.relative_to(_STATIC_DIR.resolve())
            except ValueError:
                return FileResponse(index)
            if target.is_file():
                return FileResponse(target)
            return FileResponse(index)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("SPECY_ROAD_GUI_HOST", "127.0.0.1")
    port = int(os.environ.get("SPECY_ROAD_GUI_PORT", "8765"))
    uvicorn.run(
        "specy_road.gui_app:app",
        host=host,
        port=port,
        reload=os.environ.get("SPECY_ROAD_GUI_RELOAD") == "1",
    )


if __name__ == "__main__":
    main()
