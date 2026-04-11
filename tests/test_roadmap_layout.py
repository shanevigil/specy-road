"""Tests for scripts/roadmap_layout.py (tree order with sibling_order)."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "specy_road" / "bundled_scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from roadmap_layout import dependency_edges_detailed, ordered_tree_rows  # noqa: E402


def test_ordered_tree_rows_sibling_order() -> None:
    nodes = [
        {"id": "M1", "type": "phase", "title": "A", "parent_id": None, "sibling_order": 1},
        {"id": "M0", "type": "phase", "title": "B", "parent_id": None, "sibling_order": 0},
    ]
    rows = ordered_tree_rows(nodes)
    ids = [t[0]["id"] for t in rows]
    assert ids == ["M0", "M1"]


def test_dependency_edges_detailed_marks_inherited() -> None:
    k0 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    k1 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
    k2 = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
    # M0 explicitly depends on M1 (k2); M0.1 inherits that dep without storing it.
    nodes = [
        {
            "id": "M0",
            "node_key": k0,
            "type": "phase",
            "title": "root",
            "parent_id": None,
            "dependencies": [k2],
        },
        {
            "id": "M0.1",
            "node_key": k1,
            "type": "task",
            "title": "child",
            "parent_id": "M0",
            "dependencies": [],
        },
        {
            "id": "M1",
            "node_key": k2,
            "type": "task",
            "title": "other",
            "parent_id": None,
            "dependencies": [],
        },
    ]
    edges = dependency_edges_detailed(nodes)
    by_to = {(e["from"], e["to"]): e["kind"] for e in edges}
    assert by_to.get(("M1", "M0")) == "explicit"
    assert by_to.get(("M1", "M0.1")) == "inherited"
