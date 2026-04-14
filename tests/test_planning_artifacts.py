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


def _minimal_sheet(_node_id: str, _node_key: str) -> str:
    """Body only; node identity is enforced via filename, not frontmatter."""
    return "# Sheet\n"


def test_normalize_planning_dir() -> None:
    assert (
        normalize_planning_dir("planning/M1.2_x_10000000-0000-4000-8000-000000000001.md/")
        == "planning/M1.2_x_10000000-0000-4000-8000-000000000001.md"
    )
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


def test_collect_planning_errors_missing_file(tmp_path: Path) -> None:
    nodes = [
        {
            "id": "M1",
            "node_key": "10000000-0000-4000-8000-000000000001",
            "planning_dir": "planning/M1_unnamed_10000000-0000-4000-8000-000000000001.md",
        },
    ]
    errs = collect_planning_artifact_errors(tmp_path, nodes)
    assert any("planning file missing" in e for e in errs)


def test_collect_planning_errors_ok_minimal(tmp_path: Path) -> None:
    p = tmp_path / "planning" / "M1_unnamed_10000000-0000-4000-8000-000000000001.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        _minimal_sheet("M1", "10000000-0000-4000-8000-000000000001"),
        encoding="utf-8",
    )
    nodes = [
        {
            "id": "M1",
            "node_key": "10000000-0000-4000-8000-000000000001",
            "planning_dir": "planning/M1_unnamed_10000000-0000-4000-8000-000000000001.md",
        },
    ]
    assert collect_planning_artifact_errors(tmp_path, nodes) == []


def test_collect_planning_errors_ok_legacy_frontmatter_ignored(tmp_path: Path) -> None:
    """Wrong or stale YAML must not fail validation when the filename is canonical."""
    p = tmp_path / "planning" / "M1_unnamed_10000000-0000-4000-8000-000000000001.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        "---\nnode_id: WRONG\nnode_key: 00000000-0000-4000-8000-000000000000\n---\n\n# Sheet\n",
        encoding="utf-8",
    )
    nodes = [
        {
            "id": "M1",
            "node_key": "10000000-0000-4000-8000-000000000001",
            "planning_dir": "planning/M1_unnamed_10000000-0000-4000-8000-000000000001.md",
        },
    ]
    assert collect_planning_artifact_errors(tmp_path, nodes) == []


def test_collect_planning_duplicate_planning_dir(tmp_path: Path) -> None:
    k = "10000000-0000-4000-8000-000000000001"
    k2 = "20000000-0000-4000-8000-000000000002"
    for nid, nk in (("M1", k), ("M2", k2)):
        p = tmp_path / "planning" / f"{nid}_unnamed_{nk}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_minimal_sheet(nid, nk), encoding="utf-8")
    nodes = [
        {
            "id": "M1",
            "node_key": k,
            "planning_dir": f"planning/M1_unnamed_{k}.md",
        },
        {
            "id": "M2",
            "node_key": k2,
            "planning_dir": f"planning/M1_unnamed_{k}.md",
        },
    ]
    errs = collect_planning_artifact_errors(tmp_path, nodes)
    assert any("duplicate planning_dir" in e for e in errs)


def test_collect_planning_orphan_file(tmp_path: Path) -> None:
    planning = tmp_path / "planning"
    planning.mkdir(parents=True)
    (planning / "M9_unnamed_10000000-0000-4000-8000-000000000099.md").write_text(
        _minimal_sheet("M9", "10000000-0000-4000-8000-000000000099"),
        encoding="utf-8",
    )
    nodes: list[dict] = []
    errs = collect_planning_artifact_errors(tmp_path, nodes)
    assert any("orphan planning file" in e for e in errs)


def test_apply_set_planning_dir() -> None:
    node: dict = {
        "id": "M1",
        "type": "milestone",
        "title": "t",
        "node_key": "10000000-0000-4000-8000-000000000001",
    }
    apply_set(
        node,
        "planning_dir",
        "planning/M1_unnamed_10000000-0000-4000-8000-000000000001.md",
        all_ids={"M1"},
        all_node_keys=set(),
        self_id="M1",
    )
    assert node["planning_dir"] == (
        "planning/M1_unnamed_10000000-0000-4000-8000-000000000001.md"
    )
    apply_set(
        node,
        "planning_dir",
        "",
        all_ids={"M1"},
        all_node_keys=set(),
        self_id="M1",
    )
    assert "planning_dir" not in node


def test_apply_set_planning_dir_rejects_non_md() -> None:
    node: dict = {
        "id": "M1",
        "node_key": "10000000-0000-4000-8000-000000000001",
    }
    with pytest.raises(ValueError, match="planning_dir must"):
        apply_set(
            node,
            "planning_dir",
            "planning/M1",
            all_ids={"M1"},
            all_node_keys=set(),
            self_id="M1",
        )
