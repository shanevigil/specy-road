"""Tests for roadmap_gui_tree parent helpers."""

from __future__ import annotations

from roadmap_gui_tree import indent_parent_id, is_ancestor, outdent_parent_id


def _nodes():
    return [
        {"id": "M0", "parent_id": None},
        {"id": "M0.1", "parent_id": "M0"},
        {"id": "M0.1.1", "parent_id": "M0.1"},
    ]


def _rows():
    return [
        ({"id": "M0", "parent_id": None}, 0),
        ({"id": "M0.1", "parent_id": "M0"}, 1),
        ({"id": "M0.1.1", "parent_id": "M0.1"}, 2),
    ]


def test_outdent_parent_id() -> None:
    by_id = {n["id"]: n for n in _nodes()}
    assert outdent_parent_id(by_id, "M0") is None
    assert outdent_parent_id(by_id, "M0.1") == ""
    assert outdent_parent_id(by_id, "M0.1.1") == "M0"


def test_indent_parent_id() -> None:
    by_id = {n["id"]: n for n in _nodes()}
    rows = _rows()
    assert indent_parent_id(rows, by_id, "M0") is None
    assert indent_parent_id(rows, by_id, "M0.1") == "M0"
    assert indent_parent_id(rows, by_id, "M0.1.1") == "M0.1"


def test_is_ancestor() -> None:
    by_id = {n["id"]: n for n in _nodes()}
    assert is_ancestor(by_id, "M0", "M0.1.1") is True
    assert is_ancestor(by_id, "M0.1.1", "M0") is False
