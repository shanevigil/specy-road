"""Tests for roadmap_gui_tree parent helpers."""

from __future__ import annotations

from roadmap_gui_tree import (
    can_indent_outline,
    can_outdent_outline,
    indent_parent_id,
    is_ancestor,
    outdent_parent_id,
)


def _nodes():
    return [
        {"id": "M0", "parent_id": None, "sibling_order": 0},
        {"id": "M0.1", "parent_id": "M0", "sibling_order": 0},
        {"id": "M0.1.1", "parent_id": "M0.1", "sibling_order": 0},
    ]


def _nodes_two_under_m0():
    """M0.1 and M0.2 are siblings under M0."""
    return [
        {"id": "M0", "parent_id": None, "sibling_order": 0},
        {"id": "M0.1", "parent_id": "M0", "sibling_order": 0},
        {"id": "M0.2", "parent_id": "M0", "sibling_order": 1},
    ]


def _nodes_nested_siblings():
    """Two siblings under M0.1 for indent-under-sibling tests."""
    return [
        {"id": "M0", "parent_id": None, "sibling_order": 0},
        {"id": "M0.1", "parent_id": "M0", "sibling_order": 0},
        {"id": "M0.1.1", "parent_id": "M0.1", "sibling_order": 0},
        {"id": "M0.1.2", "parent_id": "M0.1", "sibling_order": 1},
    ]


def test_outdent_parent_id() -> None:
    by_id = {n["id"]: n for n in _nodes()}
    assert outdent_parent_id(by_id, "M0") is None
    assert outdent_parent_id(by_id, "M0.1") == ""
    assert outdent_parent_id(by_id, "M0.1.1") == "M0"


def test_indent_parent_id_no_previous_sibling() -> None:
    """First (or only) child under a parent cannot indent."""
    by_id = {n["id"]: n for n in _nodes()}
    assert indent_parent_id(by_id, "M0") is None
    assert indent_parent_id(by_id, "M0.1") is None
    assert indent_parent_id(by_id, "M0.1.1") is None


def test_indent_parent_id_under_sibling() -> None:
    by_id = {n["id"]: n for n in _nodes_nested_siblings()}
    assert indent_parent_id(by_id, "M0.1.1") is None
    assert indent_parent_id(by_id, "M0.1.2") == "M0.1.1"


def test_indent_second_root_under_first() -> None:
    by_id = {n["id"]: n for n in _nodes_two_under_m0()}
    assert indent_parent_id(by_id, "M0.2") == "M0.1"


def test_can_outdent_outline() -> None:
    by_id = {n["id"]: n for n in _nodes()}
    assert can_outdent_outline(by_id, "M0") is False
    assert can_outdent_outline(by_id, "M0.1") is True
    assert can_outdent_outline(by_id, "M0.1.1") is True


def test_can_indent_outline_depth() -> None:
    nodes = _nodes_nested_siblings()
    by_id = {n["id"]: n for n in nodes}
    assert can_indent_outline(nodes, by_id, "M0.1.2") is True


def test_is_ancestor() -> None:
    by_id = {n["id"]: n for n in _nodes()}
    assert is_ancestor(by_id, "M0", "M0.1.1") is True
    assert is_ancestor(by_id, "M0.1.1", "M0") is False
