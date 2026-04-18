#!/usr/bin/env python3
"""Verify pyproject.toml version matches a release tag.

Usage:
    python scripts/check_release_version.py <tag>

Where <tag> is like ``v0.1.0`` or ``v0.1.0-rc1``. Strips the leading
``v`` and compares against ``project.version`` in ``pyproject.toml``.

Exit 0 on match, 1 on mismatch (prints both values).

Used by .github/workflows/release-publish.yml.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path


def read_pyproject_version(repo_root: Path) -> str:
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        raise SystemExit(f"error: pyproject.toml not found at {pyproject}")
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    project = data.get("project", {})
    version = project.get("version")
    if not isinstance(version, str) or not version.strip():
        raise SystemExit("error: project.version missing or empty in pyproject.toml")
    return version.strip()


def normalize_tag(tag: str) -> str:
    """Strip ``refs/tags/`` and ``v`` prefixes from a tag ref."""
    t = tag.strip()
    if t.startswith("refs/tags/"):
        t = t[len("refs/tags/"):]
    if t.startswith("v"):
        t = t[1:]
    return t


# PEP 440 prerelease normalization: tags use 'v0.1.0-rc1' (Git-friendly),
# but PyPI/pyproject use '0.1.0rc1' (no dash). Normalize the tag form to
# the pyproject form for comparison so contributors can write either.
_PRERELEASE_RE = re.compile(r"^([0-9]+\.[0-9]+\.[0-9]+)-([A-Za-z]+[0-9]*)$")


def normalize_for_pep440(version: str) -> str:
    """Convert ``X.Y.Z-rc1`` -> ``X.Y.Zrc1`` (PEP 440); pass through otherwise."""
    m = _PRERELEASE_RE.match(version)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return version


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: check_release_version.py <tag>", file=sys.stderr)
        return 2
    tag = argv[1]
    expected = normalize_for_pep440(normalize_tag(tag))
    actual = read_pyproject_version(Path.cwd())
    if expected == actual:
        print(f"ok: pyproject version {actual!r} matches tag {tag!r}")
        return 0
    print(
        f"error: pyproject version {actual!r} does NOT match tag {tag!r} "
        f"(expected pyproject version to be {expected!r}, normalized to "
        "PEP 440). Bump pyproject.toml's project.version to match the tag, "
        "then re-tag the release commit.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
