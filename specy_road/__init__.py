"""specy-road package (CLI and shared helpers)."""

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_UNKNOWN_VERSION = "0.0.0+unknown"


def _version_from_adjacent_pyproject() -> str | None:
    """If this ``specy_road`` package lives under a repo root, read declared version there.

    Prefer this over ``importlib.metadata`` when both exist so editable checkouts
    stay aligned with ``pyproject.toml`` even if install metadata was not refreshed.
    """
    repo_root = Path(__file__).resolve().parent.parent
    path = repo_root / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except OSError:
        return None
    project = data.get("project", {})
    if project.get("name") != "specy-road":
        return None
    raw = project.get("version")
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


_pyproject_version = _version_from_adjacent_pyproject()
if _pyproject_version is not None:
    __version__ = _pyproject_version
else:
    try:
        __version__ = version("specy-road")
    except PackageNotFoundError:
        __version__ = _UNKNOWN_VERSION
