#!/usr/bin/env python3
"""Fail when tests gain a new import or reference of a private specy_road name.

Tests that reach into ``_private`` helpers couple the suite to implementation
details. This gate records every such reference as ``<test file>: <dotted name>``
in ``constraints/test-private-imports-baseline.txt`` and fails on new entries.

Detected via ``ast``: ``from specy_road.mod import _name``, ``import specy_road.mod._name``,
``specy_road.mod._name`` attribute access, and ``monkeypatch.setattr("specy_road.mod._name", ..)``
or ``mock.patch(...)`` targets. Aliases such as ``import mod as _m`` are fine.

Usage: ``python scripts/check_test_private_imports.py [--update-baseline]``
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

PACKAGE = "specy_road"
STRING_TARGET_RE = re.compile(rf"^{PACKAGE}(\.\w+)*\._\w+$")


def _is_private(name: str) -> bool:
    return name.startswith("_") and not name.startswith("__")


def _dotted(node: ast.AST) -> str | None:
    """Rebuild a dotted name from an Attribute/Name chain, else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _import_from_refs(node: ast.ImportFrom) -> set[str]:
    module = node.module or ""
    if module != PACKAGE and not module.startswith(PACKAGE + "."):
        return set()
    return {f"{module}.{a.name}" for a in node.names if _is_private(a.name)}


def _import_refs(node: ast.Import) -> set[str]:
    return {
        a.name
        for a in node.names
        if a.name.startswith(PACKAGE) and any(_is_private(p) for p in a.name.split("."))
    }


def _attribute_ref(node: ast.Attribute) -> str | None:
    if not _is_private(node.attr):
        return None
    dotted = _dotted(node)
    return dotted if dotted and dotted.startswith(PACKAGE + ".") else None


def _patch_target(node: ast.Call) -> str | None:
    """First string argument of monkeypatch.setattr(...) / mock.patch(...)."""
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name not in {"setattr", "patch"} or not node.args:
        return None
    target = getattr(node.args[0], "value", None)
    return target if isinstance(target, str) and STRING_TARGET_RE.match(target) else None


def find_private_refs(source: str, filename: str) -> set[str]:
    """Return dotted private names referenced in one test module."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source, filename=filename)):
        if isinstance(node, ast.ImportFrom):
            found |= _import_from_refs(node)
        elif isinstance(node, ast.Import):
            found |= _import_refs(node)
        elif isinstance(node, ast.Attribute):
            found.add(_attribute_ref(node) or "")
        elif isinstance(node, ast.Call):
            found.add(_patch_target(node) or "")
    found.discard("")
    return found


def scan(tests_dir: Path) -> set[str]:
    entries: set[str] = set()
    root = tests_dir.parent
    for path in sorted(tests_dir.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        for name in find_private_refs(path.read_text(encoding="utf-8"), rel):
            entries.add(f"{rel}: {name}")
    return entries


def load_baseline(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def write_baseline(path: Path, entries: set[str]) -> None:
    header = ("# Private specy_road names referenced from tests (file: dotted name).\n"
              "# Gate: scripts/check_test_private_imports.py; shrink as tests go public.\n")
    path.write_text(header + "".join(f"{e}\n" for e in sorted(entries)), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tests-dir", default=Path("tests"), type=Path)
    parser.add_argument(
        "--baseline", default=Path("constraints/test-private-imports-baseline.txt"), type=Path
    )
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args(argv)

    current = scan(args.tests_dir)
    if args.update_baseline:
        write_baseline(args.baseline, current)
        print(f"wrote {len(current)} entries to {args.baseline}")
        return 0

    baseline = load_baseline(args.baseline)
    new = sorted(current - baseline)
    stale = sorted(baseline - current)
    print(f"private references in tests: {len(current)} current, "
          f"{len(baseline)} baselined, {len(new)} new")
    for entry in stale:
        print(f"  stale baseline entry (no longer referenced): {entry}")
    for entry in new:
        print(f"  NEW PRIVATE REFERENCE: {entry}")
    if new:
        print("Test through the public API instead, or (deliberately) run: "
              "python scripts/check_test_private_imports.py --update-baseline")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
