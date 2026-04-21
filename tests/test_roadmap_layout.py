"""Tests for scripts/roadmap_layout.py (tree order with sibling_order)."""

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "specy_road" / "bundled_scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from roadmap_layout import (  # noqa: E402
    compute_dependency_steps,
    dependency_edges_detailed,
    ordered_tree_rows,
)


def test_ordered_tree_rows_sibling_order() -> None:
    nodes = [
        {"id": "M1", "type": "phase", "title": "A", "parent_id": None, "sibling_order": 1},
        {"id": "M0", "type": "phase", "title": "B", "parent_id": None, "sibling_order": 0},
    ]
    rows = ordered_tree_rows(nodes)
    ids = [t[0]["id"] for t in rows]
    assert ids == ["M0", "M1"]


def test_ordered_tree_rows_natural_id_tiebreak_same_sibling_order() -> None:
    """Lexical would order M1.10 before M1.2; natural order uses numeric segments."""
    parent = "M1"
    nodes = [
        {"id": parent, "type": "phase", "parent_id": None, "sibling_order": 0},
        {"id": "M1.10", "type": "task", "parent_id": parent, "sibling_order": 0},
        {"id": "M1.2", "type": "task", "parent_id": parent, "sibling_order": 0},
        {"id": "M1.1", "type": "task", "parent_id": parent, "sibling_order": 0},
        {"id": "M1.9", "type": "task", "parent_id": parent, "sibling_order": 0},
    ]
    rows = ordered_tree_rows(nodes)
    ids = [t[0]["id"] for t in rows]
    assert ids[:5] == [parent, "M1.1", "M1.2", "M1.9", "M1.10"]


def test_ordered_tree_rows_natural_nested_segments() -> None:
    root = "M2"
    nodes = [
        {"id": root, "type": "phase", "parent_id": None, "sibling_order": 0},
        {"id": "M2.1.10", "type": "task", "parent_id": root, "sibling_order": 0},
        {"id": "M2.1.2", "type": "task", "parent_id": root, "sibling_order": 0},
        {"id": "M2.1.1", "type": "task", "parent_id": root, "sibling_order": 0},
    ]
    rows = ordered_tree_rows(nodes)
    ids = [t[0]["id"] for t in rows]
    assert ids == [root, "M2.1.1", "M2.1.2", "M2.1.10"]


def test_ordered_tree_rows_sibling_order_overrides_natural_id() -> None:
    """Explicit reorder (sibling_order) wins over natural display id order."""
    parent = "M1"
    nodes = [
        {"id": parent, "type": "phase", "parent_id": None, "sibling_order": 0},
        {"id": "M1.12", "type": "task", "parent_id": parent, "sibling_order": 1},
        {"id": "M1.23", "type": "task", "parent_id": parent, "sibling_order": 0},
    ]
    rows = ordered_tree_rows(nodes)
    ids = [t[0]["id"] for t in rows]
    assert ids == [parent, "M1.23", "M1.12"]


def test_natural_id_sort_key_fallback_lexical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If digit parsing fails, fall back to lexical whole-id key."""

    def boom(run: str) -> int:
        if run == "99":
            raise ValueError("forced")
        return int(run, 10)

    import roadmap_layout as rl

    monkeypatch.setattr(rl, "_digit_run_to_int", boom)
    nid = "M99"
    assert rl.natural_id_sort_key(nid) == ((1, nid),)


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


def test_compute_dependency_steps_m1_playground_shape() -> None:
    """Synthetic graph: phase with chained sibling deps plus a milestone depending on a child (regression for ``compute_dependency_steps``)."""
    k0 = "a1b2c3d4-e5f6-4789-a012-3456789abcde"
    k1 = "b2c3d4e5-f6a7-4890-b123-456789abcdef"
    k11 = "20562f21-a15d-47be-a40f-429397a93a02"
    k12 = "578b7680-8adc-4cb8-bfc7-a4fa42411c61"
    k13 = "1240d0da-6d82-4913-b02f-f4f2b4e67a8d"
    k2 = "ece817c4-3627-4ded-b96d-bb7eccc6fbbd"
    nodes = [
        {
            "id": "M0",
            "node_key": k0,
            "parent_id": None,
            "dependencies": [],
            "sibling_order": 0,
        },
        {
            "id": "M0.1",
            "node_key": k1,
            "parent_id": "M0",
            "dependencies": [],
            "sibling_order": 0,
        },
        {
            "id": "M0.1.1",
            "node_key": k11,
            "parent_id": "M0.1",
            "dependencies": [],
            "sibling_order": 0,
        },
        {
            "id": "M0.1.2",
            "node_key": k12,
            "parent_id": "M0.1",
            "dependencies": [k11],
            "sibling_order": 1,
        },
        {
            "id": "M0.1.3",
            "node_key": k13,
            "parent_id": "M0.1",
            "dependencies": [k12],
            "sibling_order": 2,
        },
        {
            "id": "M0.2",
            "node_key": k2,
            "parent_id": "M0",
            "dependencies": [k1],
            "sibling_order": 1,
        },
    ]
    starts, spans = compute_dependency_steps(nodes)
    assert starts["M0"] == 0 and spans["M0"] == 4
    assert starts["M0.1"] == 0 and spans["M0.1"] == 3
    assert starts["M0.1.1"] == 0 and spans["M0.1.1"] == 1
    assert starts["M0.1.2"] == 1 and spans["M0.1.2"] == 1
    assert starts["M0.1.3"] == 2 and spans["M0.1.3"] == 1
    assert starts["M0.2"] == 3 and spans["M0.2"] == 1
