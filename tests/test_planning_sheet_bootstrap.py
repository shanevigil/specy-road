"""Tests for planning_sheet_bootstrap (new-node planning file creation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from planning_artifacts import expected_planning_rel, resolve_planning_path
from planning_sheet_bootstrap import (
    ensure_planning_sheet_for_new_node,
    remove_planning_sheet_if_present,
    render_feature_sheet_template,
)


def test_render_feature_sheet_template_substitutes_node_id() -> None:
    text = render_feature_sheet_template("M9.9")
    assert "M9.9" in text
    assert "{{NODE_ID}}" not in text


def test_ensure_planning_sheet_creates_file_and_sets_planning_dir(tmp_path: Path) -> None:
    (tmp_path / "planning").mkdir(parents=True)
    nk = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    node: dict = {
        "id": "M1.1",
        "node_key": nk,
        "type": "task",
        "title": "Example task",
    }
    ensure_planning_sheet_for_new_node(tmp_path, node)
    assert "planning_dir" in node
    pd = node["planning_dir"]
    p = resolve_planning_path(tmp_path, pd)
    assert p.is_file()
    body = p.read_text(encoding="utf-8")
    assert "M1.1" in body
    assert "{{NODE_ID}}" not in body


def test_ensure_planning_sheet_noop_for_unknown_type(tmp_path: Path) -> None:
    node: dict = {"id": "X1", "node_key": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee", "type": "foo"}
    ensure_planning_sheet_for_new_node(tmp_path, node)
    assert "planning_dir" not in node


def test_ensure_planning_sheet_raises_when_planning_path_is_directory(tmp_path: Path) -> None:
    nk = "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff"
    node: dict = {
        "id": "M2.2",
        "node_key": nk,
        "type": "task",
        "title": "T",
    }
    rel = expected_planning_rel(node)
    d = tmp_path / rel
    d.mkdir(parents=True)
    with pytest.raises(ValueError, match="directory"):
        ensure_planning_sheet_for_new_node(tmp_path, node)


def test_remove_planning_sheet_if_present(tmp_path: Path) -> None:
    nk = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    node: dict = {
        "id": "M1.1",
        "node_key": nk,
        "type": "task",
        "title": "Example task",
        "codename": "ex",
    }
    rel = expected_planning_rel(node)
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# x\n", encoding="utf-8")
    remove_planning_sheet_if_present(tmp_path, rel)
    assert not p.is_file()
