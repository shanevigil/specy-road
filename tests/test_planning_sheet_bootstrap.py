from __future__ import annotations

from pathlib import Path

import pytest

from planning_artifacts import expected_planning_rel, resolve_planning_path
from planning_sheet_bootstrap import (
    ensure_planning_sheet_for_new_node,
    feature_sheet_level2_titles,
    gate_sheet_level2_titles,
    planning_review_expected_shape_block,
    remove_planning_sheet_if_present,
    render_feature_sheet_template,
    render_planning_sheet_template,
)


def test_render_feature_sheet_template_substitutes_node_id() -> None:
    text = render_feature_sheet_template("M9.9")
    assert "M9.9" in text
    assert "{{NODE_ID}}" not in text


def test_render_planning_sheet_template_gate_sections() -> None:
    text = render_planning_sheet_template("M0.1", node_type="gate")
    assert "M0.1" in text
    assert "{{NODE_ID}}" not in text
    assert "Why this gate exists" in text
    assert "Criteria to clear" in text
    assert "Intent" not in text


def test_planning_review_expected_shape_block_gate() -> None:
    block = planning_review_expected_shape_block("gate")
    assert "gate planning sheet" in block
    assert "Why this gate exists" in block


def test_gate_sheet_level2_titles_match_template() -> None:
    titles = gate_sheet_level2_titles()
    assert titles == (
        "Why this gate exists",
        "Criteria to clear",
        "Decisions and notes",
        "Resolution",
        "References",
    )


def test_ensure_planning_sheet_gate_writes_gate_template(tmp_path: Path) -> None:
    nk = "cccccccc-dddd-4eee-8fff-000000000001"
    node: dict = {
        "id": "M3.1",
        "node_key": nk,
        "type": "gate",
        "title": "Approval hold",
    }
    ensure_planning_sheet_for_new_node(tmp_path, node)
    pd = node["planning_dir"]
    body = resolve_planning_path(tmp_path, pd).read_text(encoding="utf-8")
    assert "Why this gate exists" in body
    assert "Intent" not in body


def test_feature_sheet_level2_titles_match_scaffold_template() -> None:
    titles = feature_sheet_level2_titles()
    assert titles == (
        "Intent",
        "Approach",
        "Tasks / checklist",
        "References",
    )


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
