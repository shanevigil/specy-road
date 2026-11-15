"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from tests.helpers import REPO
import tomllib

def _declared_package_data() -> list[str]:
    with (REPO / "pyproject.toml").open("rb") as f:
        cfg = tomllib.load(f)
    return cfg["tool"]["setuptools"]["package-data"]["specy_road"]
