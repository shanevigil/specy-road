"""Argparse for ``specy-road init`` (project vs gui)."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_specy_road_init_parser() -> argparse.ArgumentParser:
    """Parser for ``specy-road init project|gui ...``."""
    p = argparse.ArgumentParser(
        prog="specy-road init",
        description="Initialize a consumer project layout or optional PM GUI tooling.",
    )
    sub = p.add_subparsers(dest="init_cmd", required=True)
    pr = sub.add_parser(
        "project",
        help="Scaffold constitution/, roadmap/, shared/, constraints/, schemas/, planning/, work/, AGENTS.md",
    )
    pr.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=None,
        help="Target repository root (default: git toplevel or cwd)",
    )
    pr.add_argument(
        "--dry-run",
        action="store_true",
        help="Print paths that would be written; do not create files",
    )
    pr.add_argument(
        "--force",
        action="store_true",
        help="Overwrite template files; required if roadmap/manifest.json already exists",
    )
    pg = sub.add_parser(
        "gui",
        help="Install FastAPI/uvicorn (gui-next) and optionally build the Vite SPA",
    )
    mode = pg.add_mutually_exclusive_group(required=False)
    mode.add_argument(
        "--install-gui",
        action="store_true",
        help="pip install --upgrade …[gui-next], then npm build in gui/pm-gantt when present",
    )
    mode.add_argument(
        "--reinstall-gui",
        action="store_true",
        help="Like --install-gui but pip uses --force-reinstall",
    )
    pg.add_argument(
        "--build-gui",
        action="store_true",
        help="Only rebuild the SPA (npm). Use without --install-gui to skip pip",
    )
    pg.add_argument(
        "--skip-npm-build",
        action="store_true",
        help="With --install-gui / --reinstall-gui: skip npm after pip",
    )
    pg.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands that would be run",
    )
    return p
