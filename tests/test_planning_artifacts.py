"""Tests for planning_dir validation and markdown helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from planning_artifacts import (
    collect_planning_artifact_errors,
    normalize_planning_dir,
    split_frontmatter,
)
from roadmap_edit_fields import apply_set


def test_normalize_planning_dir() -> None:
    assert normalize_planning_dir("planning/M1.2/") == "planning/M1.2"
    assert normalize_planning_dir("foo/bar") == "foo/bar"
    with pytest.raises(ValueError):
        normalize_planning_dir("../escape")
    with pytest.raises(ValueError):
        normalize_planning_dir("")
    with pytest.raises(ValueError):
        normalize_planning_dir("a/../b")


def test_split_frontmatter() -> None:
    fm, body = split_frontmatter("---\na: 1\n---\n\nHello")
    assert fm == {"a": 1}
    assert body.strip() == "Hello"
    assert split_frontmatter("no front")[0] == {}


def test_collect_planning_errors_missing_files(tmp_path: Path) -> None:
    d = tmp_path / "planning" / "M1"
    d.mkdir(parents=True)
    nodes = [{"id": "M1", "planning_dir": "planning/M1"}]
    errs = collect_planning_artifact_errors(tmp_path, nodes)
    assert len(errs) >= 2
    assert any("missing overview.md" in e for e in errs)
    assert any("missing plan.md" in e for e in errs)


def test_collect_planning_errors_ok_minimal(tmp_path: Path) -> None:
    d = tmp_path / "planning" / "M1"
    d.mkdir(parents=True)
    (d / "overview.md").write_text("# s", encoding="utf-8")
    (d / "plan.md").write_text("# p", encoding="utf-8")
    nodes = [{"id": "M1", "planning_dir": "planning/M1"}]
    assert collect_planning_artifact_errors(tmp_path, nodes) == []


def test_collect_planning_duplicate_planning_dir(tmp_path: Path) -> None:
    d = tmp_path / "planning" / "M1"
    d.mkdir(parents=True)
    (d / "overview.md").write_text("# s", encoding="utf-8")
    (d / "plan.md").write_text("# p", encoding="utf-8")
    nodes = [
        {"id": "M1", "planning_dir": "planning/M1"},
        {"id": "M2", "planning_dir": "planning/M1"},
    ]
    errs = collect_planning_artifact_errors(tmp_path, nodes)
    assert any("duplicate planning_dir" in e for e in errs)


def test_collect_planning_task_file_wrong_owner(tmp_path: Path) -> None:
    d = tmp_path / "planning" / "M1"
    (d / "tasks").mkdir(parents=True)
    (d / "overview.md").write_text("# s", encoding="utf-8")
    (d / "plan.md").write_text("# p", encoding="utf-8")
    (d / "tasks" / "t.md").write_text(
        "---\nnode_id: M9.9\n---\n\nx",
        encoding="utf-8",
    )
    nodes = [{"id": "M1", "planning_dir": "planning/M1"}, {"id": "M9.9", "parent_id": None}]
    errs = collect_planning_artifact_errors(tmp_path, nodes)
    assert any("M9.9" in e and "descendant" in e for e in errs)


def test_collect_planning_orphan_task_md(tmp_path: Path) -> None:
    d = tmp_path / "planning" / "M2" / "tasks"
    d.mkdir(parents=True)
    (d / "orphan.md").write_text("---\nnode_id: M1\n---\n", encoding="utf-8")
    nodes = [{"id": "M1", "planning_dir": "planning/M1"}]
    (tmp_path / "planning" / "M1").mkdir(parents=True)
    (tmp_path / "planning" / "M1" / "overview.md").write_text("# s", encoding="utf-8")
    (tmp_path / "planning" / "M1" / "plan.md").write_text("# p", encoding="utf-8")
    errs = collect_planning_artifact_errors(tmp_path, nodes)
    assert any("orphan task markdown" in e for e in errs)


def test_apply_set_planning_dir() -> None:
    node: dict = {"id": "M1", "type": "milestone", "title": "t"}
    apply_set(
        node,
        "planning_dir",
        "planning/M1",
        all_ids={"M1"},
        all_node_keys=set(),
        self_id="M1",
    )
    assert node["planning_dir"] == "planning/M1"
    apply_set(
        node,
        "planning_dir",
        "",
        all_ids={"M1"},
        all_node_keys=set(),
        self_id="M1",
    )
    assert "planning_dir" not in node
