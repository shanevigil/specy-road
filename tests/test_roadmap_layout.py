"""Tests for scripts/roadmap_layout.py (tree order with sibling_order)."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from roadmap_layout import ordered_tree_rows  # noqa: E402


def test_ordered_tree_rows_sibling_order() -> None:
    nodes = [
        {"id": "M1", "type": "phase", "title": "A", "parent_id": None, "sibling_order": 1},
        {"id": "M0", "type": "phase", "title": "B", "parent_id": None, "sibling_order": 0},
    ]
    rows = ordered_tree_rows(nodes)
    ids = [t[0]["id"] for t in rows]
    assert ids == ["M0", "M1"]
