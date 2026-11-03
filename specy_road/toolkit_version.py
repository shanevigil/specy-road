"""The running specy-road build string for ``--version`` and audit records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road import __version__
from specy_road.git_subprocess import head_sha, run, working_tree_clean
from specy_road.runtime_paths import git_root, specy_road_package_dir


def _toolkit_git_root() -> Path | None:
    """The git root when this install is the toolkit's own checkout, not a wheel in another repo."""
    pkg = specy_road_package_dir()
    root = git_root(pkg)
    if root is None or pkg.parent.resolve() != root.resolve():
        return None
    try:
        init_rel = (pkg / "__init__.py").relative_to(root).as_posix()
    except ValueError:
        return None
    if not run(["ls-files", "--error-unmatch", init_rel], root).ok:
        return None
    return root


def running_toolkit_version() -> str:
    """Semver from :data:`specy_road.__version__`, plus checkout identity when applicable."""
    root = _toolkit_git_root()
    if root is None:
        return __version__
    sha = head_sha(root)
    if not sha:
        return __version__
    label = sha[:12]
    if not working_tree_clean(root):
        label = f"{label}.dirty"
    return f"{__version__}+{label}"


def stamp_review_toolkit_version(data: dict[str, Any]) -> dict[str, Any]:
    if "verdict" not in data or data.get("toolkit_version"):
        return data
    return {**data, "toolkit_version": running_toolkit_version()}
