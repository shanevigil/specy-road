"""Tests for specy_road.milestone_subtree."""

from __future__ import annotations

from specy_road.milestone_subtree import (
    children_by_parent_id,
    filter_available_under_parent,
    leaf_ids_under_parent,
    structural_leaf_ids,
    subtree_node_ids,
)


def _node(
    nid: str,
    *,
    parent_id: str | None = None,
) -> dict:
    return {"id": nid, "parent_id": parent_id}


def test_structural_leaf_ids_simple() -> None:
    nodes = [
        _node("M1", parent_id=None),
        _node("M1.1", parent_id="M1"),
        _node("M1.2", parent_id="M1"),
    ]
    assert structural_leaf_ids(nodes) == {"M1.1", "M1.2"}


def test_subtree_node_ids_includes_root_and_descendants() -> None:
    nodes = [
        _node("M7", parent_id=None),
        _node("M7.1", parent_id="M7"),
        _node("M7.1.1", parent_id="M7.1"),
        _node("M8", parent_id=None),
    ]
    assert subtree_node_ids("M7", nodes) == {"M7", "M7.1", "M7.1.1"}
    assert subtree_node_ids("missing", nodes) == set()


def test_leaf_ids_under_parent() -> None:
    nodes = [
        _node("M7", parent_id=None),
        _node("M7.1", parent_id="M7"),
        _node("M7.2", parent_id="M7"),
        _node("M8", parent_id=None),
    ]
    assert leaf_ids_under_parent("M7", nodes) == {"M7.1", "M7.2"}


def test_filter_available_under_parent_preserves_order() -> None:
    nodes = [
        _node("M7", parent_id=None),
        _node("M7.1", parent_id="M7"),
        _node("M7.2", parent_id="M7"),
    ]
    available = [
        {"id": "M7.2", "title": "b"},
        {"id": "M8.1", "title": "x"},
        {"id": "M7.1", "title": "a"},
    ]
    out = filter_available_under_parent(available, "M7", nodes)
    assert [n["id"] for n in out] == ["M7.2", "M7.1"]


def test_children_by_parent_id() -> None:
    nodes = [
        _node("R", parent_id=None),
        _node("A", parent_id="R"),
        _node("B", parent_id="R"),
    ]
    m = children_by_parent_id(nodes)
    assert set(m.get(None, [])) == {"R"}
    assert set(m.get("R", [])) == {"A", "B"}
