"""Private-name coupling census over ``tests/`` (lean-code census, measurement 1).

Per test function (``test_*``) count four implementation-coupling signals:

* ``private``   -- reads a ``_``-prefixed attribute of a ``specy_road`` module, or
                   uses a ``_``-prefixed name imported from one.
* ``patch``     -- ``monkeypatch.setattr`` on a ``_``-prefixed target
                   (module object + ``"_name"`` or a dotted ``"specy_road..._name"``).
* ``callrec``   -- asserts on mock call records (``call_count``, ``assert_called*``,
                   ``mock_calls``) or on a locally recorded call list (a name
                   containing ``call``/``seen``/``recorded``).
* ``log``       -- reads ``caplog`` in an assertion or in a test body.

Usage: ``python scripts/census/private_coupling.py [--flagged] [tests_dir]``.
Prints a per-file table (markdown) and, with ``--flagged``, one line per flagged
test (``file::test  categories``) to feed the hand-classified sample.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

CALLREC_RE = re.compile(r"(call|seen|recorded|invocations)", re.I)
MOCK_ATTRS = {"call_count", "mock_calls", "call_args", "call_args_list"}


def _specy_bindings(tree: ast.AST) -> tuple[set[str], set[str]]:
    """Names bound to specy_road modules, and private names imported from them."""
    mods: set[str] = set()
    privs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("specy_road"):
                    mods.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("specy_road"):
            for a in node.names:
                local = a.asname or a.name
                if a.name.startswith("_") and not a.name.startswith("__"):
                    privs.add(local)
                else:
                    mods.add(local)  # submodule or public object; attr reads of _x still count
    return mods, privs


def _classify(fn: ast.FunctionDef, mods: set[str], privs: set[str]) -> set[str]:
    cats: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_") and not node.attr.startswith("__"):
            if isinstance(node.value, ast.Name) and node.value.id in mods:
                cats.add("private")
        if isinstance(node, ast.Name) and node.id in privs:
            cats.add("private")
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "setattr" and len(node.args) >= 2:
                t, n = node.args[0], node.args[1]
                if isinstance(t, ast.Constant) and isinstance(t.value, str):
                    if t.value.startswith("specy_road") and t.value.rsplit(".", 1)[-1].startswith("_"):
                        cats.add("patch")
                elif isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith("_"):
                    if isinstance(t, ast.Name) and t.id in mods:
                        cats.add("patch")
            if isinstance(f, ast.Attribute) and f.attr.startswith("assert_called"):
                cats.add("callrec")
        if isinstance(node, ast.Assert):
            src = ast.unparse(node.test)
            if any(a in src for a in MOCK_ATTRS) or any(
                CALLREC_RE.search(n.id) for n in ast.walk(node.test) if isinstance(n, ast.Name)
            ):
                cats.add("callrec")
            if "caplog" in src:
                cats.add("log")
    return cats


def scan_file(path: Path) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods, privs = _specy_bindings(tree)
    helpers: dict[str, set[str]] = {}
    tests: dict[str, set[str]] = {}
    for node in tree.body:
        fns = [node] if isinstance(node, ast.FunctionDef) else []
        if isinstance(node, ast.ClassDef):
            fns = [n for n in node.body if isinstance(n, ast.FunctionDef)]
        for fn in fns:
            (tests if fn.name.startswith("test_") else helpers)[fn.name] = _classify(fn, mods, privs)
    # One level of indirection: a test calling a flagged local helper inherits "private" via helper.
    for node in tree.body:
        fns = [node] if isinstance(node, ast.FunctionDef) else []
        if isinstance(node, ast.ClassDef):
            fns = [n for n in node.body if isinstance(n, ast.FunctionDef)]
        for fn in fns:
            if not fn.name.startswith("test_"):
                continue
            for c in ast.walk(fn):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in helpers:
                    if "private" in helpers[c.func.id] or "patch" in helpers[c.func.id]:
                        tests[fn.name].add("via_helper")
    return tests


def main(argv: list[str]) -> int:
    flagged = "--flagged" in argv
    args = [a for a in argv if not a.startswith("--")]
    root = Path(args[0]) if args else Path("tests")
    cats = ("private", "patch", "callrec", "log", "via_helper")
    rows = []
    totals = {c: 0 for c in cats} | {"tests": 0, "any": 0}
    for path in sorted(root.glob("test_*.py")):
        tests = scan_file(path)
        if not tests:
            continue
        counts = {c: sum(1 for s in tests.values() if c in s) for c in cats}
        direct = sum(1 for s in tests.values() if s & {"private", "patch", "callrec", "log"})
        rows.append((path.name, len(tests), counts, direct))
        totals["tests"] += len(tests)
        totals["any"] += direct
        for c in cats:
            totals[c] += counts[c]
        if flagged:
            for name, s in tests.items():
                if s:
                    print(f"{path.name}::{name}\t{','.join(sorted(s))}")
    if flagged:
        return 0
    print("| file | tests | private | patch | callrec | log | any direct | share | via helper |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, n, c, direct in sorted(rows, key=lambda r: -r[3]):
        print(f"| {name} | {n} | {c['private']} | {c['patch']} | {c['callrec']} | {c['log']} | {direct} | {direct / n:.0%} | {c['via_helper']} |")
    t = totals
    print(f"| **total** | {t['tests']} | {t['private']} | {t['patch']} | {t['callrec']} | {t['log']} | {t['any']} | {t['any'] / t['tests']:.0%} | {t['via_helper']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
