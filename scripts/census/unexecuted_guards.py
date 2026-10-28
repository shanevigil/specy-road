"""Defensive lines in ``specy_road/`` that no test executed (census measurement 4).

Combines ``.coverage`` (executed lines) with an AST scan for the guard shapes:

* ``except``   -- an ``except ...:`` handler line
* ``raise``    -- a ``raise`` statement
* ``return``   -- ``return`` / ``return None`` sitting directly in an ``if`` body (early-return guard)
* ``is-none``  -- an ``if`` whose test contains ``x is None`` / ``x is not None``
* ``isinst``   -- an ``if`` whose test contains an ``isinstance(...)`` call

Usage: ``python scripts/census/unexecuted_guards.py [.coverage] [--list] [--module NAME]``.
Default prints a per-module count table; ``--list`` prints one line per unexecuted guard.
"""

from __future__ import annotations

import ast
import sys
from collections import Counter, defaultdict
from pathlib import Path

from coverage import CoverageData

KINDS = ("except", "raise", "return", "is-none", "isinst")


def _has(node: ast.AST, pred) -> bool:
    return any(pred(n) for n in ast.walk(node))


def guard_lines(src: str) -> dict[int, str]:
    """Line -> guard kind for one source file (first kind wins per line)."""
    out: dict[int, str] = {}
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            out.setdefault(node.lineno, "except")
        elif isinstance(node, ast.Raise):
            out.setdefault(node.lineno, "raise")
        elif isinstance(node, ast.If):
            t = node.test
            if _has(t, lambda n: isinstance(n, ast.Compare) and any(isinstance(o, (ast.Is, ast.IsNot)) for o in n.ops)
                    and any(isinstance(c, ast.Constant) and c.value is None for c in n.comparators)):
                out.setdefault(node.lineno, "is-none")
            elif _has(t, lambda n: isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "isinstance"):
                out.setdefault(node.lineno, "isinst")
            for stmt in node.body:
                if isinstance(stmt, ast.Return) and (stmt.value is None or (isinstance(stmt.value, ast.Constant) and stmt.value.value is None)):
                    out.setdefault(stmt.lineno, "return")
    return out


def main(argv: list[str]) -> int:
    listing = "--list" in argv
    only = argv[argv.index("--module") + 1] if "--module" in argv else None
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--module")]
    data = CoverageData(args[0] if args else ".coverage")
    data.read()
    executed: dict[str, set[int]] = {}
    for f in data.measured_files():
        executed[str(Path(f).resolve())] = set(data.lines(f) or ())
    per_module: dict[str, Counter] = defaultdict(Counter)
    totals: dict[str, Counter] = defaultdict(Counter)
    rows: list[tuple[str, int, str, str]] = []
    for path in sorted(Path("specy_road").rglob("*.py")):
        mod = path.as_posix()
        if only and only not in mod:
            continue
        src = path.read_text(encoding="utf-8")
        ran = executed.get(str(path.resolve()), set())
        lines = src.splitlines()
        for line, kind in guard_lines(src).items():
            totals[mod][kind] += 1
            if line not in ran:
                per_module[mod][kind] += 1
                rows.append((mod, line, kind, lines[line - 1].strip()))
    if listing:
        for mod, line, kind, text in rows:
            print(f"{mod}:{line}\t{kind}\t{text}")
        return 0
    grand = Counter()
    grand_tot = Counter()
    print("| module | " + " | ".join(f"{k} (of)" for k in KINDS) + " | unexecuted guards |")
    print("|---|" + "---:|" * (len(KINDS) + 1))
    for mod in sorted(per_module, key=lambda m: -sum(per_module[m].values())):
        c, t = per_module[mod], totals[mod]
        grand.update(c)
        grand_tot.update(t)
        print(f"| {mod.removeprefix('specy_road/')} | " + " | ".join(f"{c[k]} ({t[k]})" for k in KINDS) + f" | {sum(c.values())} |")
    for mod in totals:
        if mod not in per_module:
            grand_tot.update(totals[mod])
    print("| **total** | " + " | ".join(f"{grand[k]} ({grand_tot[k]})" for k in KINDS) + f" | {sum(grand.values())} |")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
