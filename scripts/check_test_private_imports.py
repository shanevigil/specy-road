#!/usr/bin/env python3
"""Fail when tests gain a new import or reference of a private specy_road name.

Tests that reach into ``_private`` helpers couple the suite to implementation
details. This gate records every such reference as ``<test file>: <dotted name>``
in ``constraints/test-private-imports-baseline.txt`` and fails on new entries.

Detected via ``ast``: ``from specy_road.mod import _name``, ``import specy_road.mod._name``,
``specy_road.mod._name`` attribute access, and ``monkeypatch.setattr("specy_road.mod._name", ..)``
or ``mock.patch(...)`` targets. Import aliases (``import specy_road.mod as m``,
``from specy_road import mod``) are resolved, so ``m._name`` and
``monkeypatch.setattr(m, "_name", ..)`` / ``mock.patch.object(m, "_name")`` count too;
a private alias name itself (``import mod as _m``) is fine.

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


def _in_package(name: str) -> bool:
    return name == PACKAGE or name.startswith(PACKAGE + ".")


def _dotted(node: ast.AST, aliases: dict[str, str]) -> str | None:
    """Rebuild a dotted name from an Attribute/Name chain (root alias resolved), else None."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(aliases.get(node.id, node.id))
    return ".".join(reversed(parts))


def _aliases(tree: ast.AST) -> dict[str, str]:
    """Local names that imports bind to specy_road modules or objects."""
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bound.update({a.asname: a.name for a in node.names if a.asname and _in_package(a.name)})
        elif isinstance(node, ast.ImportFrom) and _in_package(node.module or ""):
            bound.update({a.asname or a.name: f"{node.module}.{a.name}" for a in node.names})
    return bound


def _import_from_refs(node: ast.ImportFrom) -> set[str]:
    module = node.module or ""
    if not _in_package(module):
        return set()
    return {f"{module}.{a.name}" for a in node.names if _is_private(a.name)}


def _import_refs(node: ast.Import) -> set[str]:
    return {
        a.name
        for a in node.names
        if a.name.startswith(PACKAGE) and any(_is_private(p) for p in a.name.split("."))
    }


def _attribute_ref(node: ast.Attribute, aliases: dict[str, str]) -> str | None:
    if not _is_private(node.attr):
        return None
    dotted = _dotted(node, aliases)
    return dotted if dotted and dotted.startswith(PACKAGE + ".") else None


def _patch_target(node: ast.Call, aliases: dict[str, str]) -> str | None:
    """Target of setattr(...) / mock.patch(...) / patch.object(...): string or (owner, "_name")."""
    func = node.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    args = node.args
    if name not in {"setattr", "patch", "object"} or not args:
        return None
    target = getattr(args[0], "value", None)
    if isinstance(target, str):
        return target if STRING_TARGET_RE.match(target) else None
    attr = getattr(args[1], "value", None) if len(args) > 1 else None
    owner = _dotted(args[0], aliases)
    if isinstance(attr, str) and _is_private(attr) and owner and owner.startswith(PACKAGE + "."):
        return f"{owner}.{attr}"
    return None


def find_private_refs(source: str, filename: str) -> set[str]:
    """Return dotted private names referenced in one test module."""
    found: set[str] = set()
    tree = ast.parse(source, filename=filename)
    aliases = _aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            found |= _import_from_refs(node)
        elif isinstance(node, ast.Import):
            found |= _import_refs(node)
        elif isinstance(node, ast.Attribute):
            found.add(_attribute_ref(node, aliases) or "")
        elif isinstance(node, ast.Call):
            found.add(_patch_target(node, aliases) or "")
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
