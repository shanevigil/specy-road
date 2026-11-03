"""The running specy-road build string for ``--version`` and audit records."""

from __future__ import annotations

from specy_road import __version__
from specy_road.git_subprocess import head_sha, working_tree_clean
from specy_road.runtime_paths import git_root, specy_road_package_dir


def running_toolkit_version() -> str:
    """Semver from :data:`specy_road.__version__`, plus checkout identity when applicable."""
    root = git_root(specy_road_package_dir())
    if root is None:
        return __version__
    sha = head_sha(root)
    if not sha:
        return __version__
    label = sha[:12]
    if not working_tree_clean(root):
        label = f"{label}.dirty"
    return f"{__version__}+{label}"
