"""Hand-built graph lookups outside RoadmapIndex may only become fewer.

``RoadmapIndex`` (specy_road/bundled_scripts/roadmap_index.py) answers lookups by
display id and by node_key. Every other place that builds its own map or scans
the node list is counted here, against a committed baseline that may only be
lowered. There is no target number: a module switches to the index when a change
touches it anyway.

A *lookup subscript* is ``x["id"]`` or ``x["node_key"]``. The counted patterns:

1. a dict comprehension whose key is a lookup subscript
   (``{n["id"]: n for n in nodes}``);
2. ``next()`` over a generator expression whose condition compares a lookup
   subscript (``next(n for n in nodes if n["id"] == wanted)``);
3. a ``for`` loop whose body has an ``if`` comparing a lookup subscript, and
   that ``if`` returns or breaks (a linear search written out).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "specy_road"
INDEX_MODULE = PACKAGE / "bundled_scripts" / "roadmap_index.py"

#: Lower this when the count falls; never raise it.
BASELINE = 68

LOOKUP_FIELDS = {"id", "node_key"}


def _is_lookup(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and node.slice.value in LOOKUP_FIELDS
    )


def _compares_lookup(tree: ast.AST) -> bool:
    return any(
        isinstance(c, ast.Compare) and any(map(_is_lookup, [c.left, *c.comparators]))
        for c in ast.walk(tree)
    )


def _is_counted(node: ast.AST) -> bool:
    if isinstance(node, ast.DictComp):
        return _is_lookup(node.key)
    if isinstance(node, ast.Call):
        gen = node.args[0] if node.args else None
        return (
            isinstance(node.func, ast.Name) and node.func.id == "next"
            and isinstance(gen, ast.GeneratorExp)
            and any(_compares_lookup(cond) for comp in gen.generators for cond in comp.ifs)
        )
    if isinstance(node, ast.For):
        return any(
            isinstance(stmt, ast.If) and _compares_lookup(stmt.test)
            and any(isinstance(s, (ast.Return, ast.Break)) for s in stmt.body)
            for stmt in node.body
        )
    return False


def count_lookups(source: str) -> int:
    """Number of counted lookup patterns in one module's source."""
    return sum(map(_is_counted, ast.walk(ast.parse(source))))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('{n["id"]: n for n in nodes}', 1),
        ('{n["node_key"]: n["id"] for n in nodes if n.get("node_key")}', 1),
        ('next(n for n in nodes if n["id"] == wanted)', 1),
        ("for n in nodes:\n    if n['node_key'] == k:\n        break", 1),
        ("def f(nodes):\n    for n in nodes:\n        if n['id'] == 'x':\n            return n", 1),
        ('{n["title"]: n for n in nodes}', 0),
        ("for n in nodes:\n    if n['id'] == 'x':\n        print(n)", 0),
    ],
)
def test_counter_matches_each_pattern(source: str, expected: int) -> None:
    """Each pattern counts once; a lookup by another field, or a loop that only reads, does not."""
    assert count_lookups(source) == expected


def test_graph_lookups_outside_the_index_only_shrink() -> None:
    """The package total stays at the committed baseline; a new hand-built lookup fails."""
    per_file = {
        path.relative_to(REPO).as_posix(): count_lookups(path.read_text(encoding="utf-8"))
        for path in sorted(PACKAGE.rglob("*.py"))
        if path != INDEX_MODULE
    }
    total = sum(per_file.values())
    hits = "\n".join(f"  {p}: {n}" for p, n in per_file.items() if n)
    assert total <= BASELINE, (
        f"{total} hand-built graph lookups, baseline {BASELINE}. Use RoadmapIndex "
        f"(roadmap_index.py) instead of a new one.\n{hits}"
    )
    assert total == BASELINE, f"the count fell to {total}: lower BASELINE to {total}."
