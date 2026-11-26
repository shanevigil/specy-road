"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from specy_road.bundled_scripts.roadmap_crud_argparse import build_parser

def crud(repo: Path, *argv: str) -> None:
    """Shared test helper."""
    ns = build_parser().parse_args(["--repo-root", str(repo), *argv])
    ns.func(ns)
