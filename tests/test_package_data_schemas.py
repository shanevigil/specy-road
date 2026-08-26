"""Every toolkit-owned schema must be declared in package-data.

Unlike ``<repo_root>/schemas/``, which each consumer repo owns and upgrades by
hand, these ship inside the wheel and are the copy the toolkit validates
against. A schema missing from ``package-data`` is invisible from an editable
checkout and only breaks for pip-installed users — the same silent-drop failure
that shipped the scaffold without its ``.gitignore``.
"""

from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "specy_road"
SCHEMAS = PKG / "schemas"


def _declared_package_data() -> list[str]:
    with (REPO / "pyproject.toml").open("rb") as f:
        cfg = tomllib.load(f)
    return cfg["tool"]["setuptools"]["package-data"]["specy_road"]


def _bundled_schemas() -> list[str]:
    if not SCHEMAS.is_dir():
        return []
    return [p.relative_to(PKG).as_posix() for p in sorted(SCHEMAS.rglob("*.json"))]


def test_bundled_schemas_are_covered_by_package_data() -> None:
    patterns = _declared_package_data()
    uncovered = [
        rel
        for rel in _bundled_schemas()
        if not any(fnmatch.fnmatch(rel, pat) for pat in patterns)
    ]
    assert not uncovered, (
        "these bundled schemas are not covered by [tool.setuptools.package-data] "
        f"and would be dropped from the wheel: {uncovered}"
    )


def test_the_archive_schema_is_one_of_them() -> None:
    """Guards the guard: a rename must not quietly empty the check above."""
    assert "schemas/archive.schema.json" in _bundled_schemas()


def test_the_archive_schema_loads_and_is_the_one_the_code_uses() -> None:
    from specy_road.archive_index import (
        bundled_archive_schema,
        bundled_archive_schema_path,
    )

    assert bundled_archive_schema_path() == SCHEMAS / "archive.schema.json"
    assert bundled_archive_schema()["title"].startswith("specy-road")
