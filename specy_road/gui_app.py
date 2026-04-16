"""FastAPI server for the PM Gantt SPA.

Includes roadmap CRUD, planning files, and settings endpoints.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def _scripts_dir() -> Path:
    """Locate bundled roadmap Python modules (``bundled_scripts/``)."""
    env = os.environ.get("SPECY_ROAD_SCRIPTS")
    if env:
        p = Path(env).resolve()
        if p.is_dir():
            return p
    pkg = Path(__file__).resolve().parent
    bundled = pkg / "bundled_scripts"
    if bundled.is_dir():
        return bundled
    raise RuntimeError(
        "Cannot locate bundled_scripts/ (roadmap modules). "
        "Reinstall specy-road, "
        "or set SPECY_ROAD_SCRIPTS to that directory.",
    )


_SCRIPTS = _scripts_dir()
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from specy_road.gui_app_api import make_api_router  # noqa: E402

_PKG_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _PKG_DIR / "pm_gantt_static"


def create_app() -> FastAPI:
    app = FastAPI(title="specy-road PM Gantt API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(make_api_router())

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
