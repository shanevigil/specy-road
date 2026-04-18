"""Tests for milestone session file IO."""

from __future__ import annotations

from pathlib import Path

from specy_road.milestone_session import (
    read_milestone_session,
    rollup_branch_for_codename,
    write_milestone_session,
)


def test_write_read_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "work" / ".milestone-session.yaml"
    write_milestone_session(
        p,
        parent_node_id="M7",
        parent_codename="my-ms",
        integration_branch="dev",
        remote="origin",
    )
    ms = read_milestone_session(p)
    assert ms is not None
    assert ms.parent_node_id == "M7"
    assert ms.parent_codename == "my-ms"
    assert ms.rollup_branch == "feature/rm-my-ms"
    assert ms.integration_branch == "dev"
    assert ms.remote == "origin"


def test_read_rejects_rollup_mismatch(tmp_path: Path) -> None:
    p = tmp_path / ".milestone-session.yaml"
    p.write_text(
        "version: 1\n"
        "parent_node_id: M7\n"
        "parent_codename: a\n"
        "rollup_branch: feature/rm-wrong\n"
        "integration_branch: dev\n"
        "remote: origin\n",
        encoding="utf-8",
    )
    assert read_milestone_session(p) is None


def test_rollup_branch_for_codename() -> None:
    assert rollup_branch_for_codename("x-y") == "feature/rm-x-y"
