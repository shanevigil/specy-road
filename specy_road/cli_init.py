"""`specy-road init` helpers (PM-facing optional installs)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def specy_road_repo_root_for_editable_install() -> Path | None:
    """If ``specy_road`` is from a source checkout, return that repo root.

    Used to run ``pip install -e ".[gui-next]"`` so contributors do not
    pull a PyPI wheel over their editable tree.
    """
    import specy_road

    pkg_dir = Path(specy_road.__file__).resolve().parent
    candidate = pkg_dir.parent
    pyproject = candidate / "pyproject.toml"
    if not pyproject.is_file():
        return None
    try:
        text = pyproject.read_text(encoding="utf-8")
    except OSError:
        return None
    if 'name = "specy-road"' not in text and "name='specy-road'" not in text:
        return None
    return candidate


def build_install_gui_command() -> tuple[list[str], Path | None]:
    """Return argv for ``python -m pip install ...`` and optional cwd."""
    repo = specy_road_repo_root_for_editable_install()
    base = [sys.executable, "-m", "pip", "install"]
    if repo is not None:
        return base + ["-e", ".[gui-next]"], repo
    return base + ["specy-road[gui-next]"], None


def run_install_gui(*, dry_run: bool) -> None:
    cmd, cwd = build_install_gui_command()
    if dry_run:
        suffix = f" (cwd={cwd})" if cwd is not None else ""
        print(f"Would run: {' '.join(cmd)}{suffix}")
        return
    subprocess.check_call(cmd, cwd=cwd)
