"""Tests for milestone subtree PM lock."""

from __future__ import annotations

import pytest

from specy_road.milestone_lock import (
    assert_pm_nodes_not_milestone_locked,
    locked_node_ids,
    milestone_lock_parent_ids,
)


def _me(state: str) -> dict:
    return {
        "state": state,
        "rollup_branch": "feature/rm-parent",
        "integration_branch": "dev",
        "remote": "origin",
    }


def test_milestone_lock_parent_ids_active() -> None:
    nodes = [
        {
            "id": "M1",
            "parent_id": None,
            "milestone_execution": _me("active"),
        },
        {"id": "M1.1", "parent_id": "M1"},
    ]
    assert milestone_lock_parent_ids(nodes) == ["M1"]


def test_locked_node_ids_includes_subtree() -> None:
    nodes = [
        {"id": "M1", "parent_id": None, "milestone_execution": _me("pending_mr")},
        {"id": "M1.1", "parent_id": "M1"},
        {"id": "M1.2", "parent_id": "M1"},
        {"id": "M2", "parent_id": None},
    ]
    locked = locked_node_ids(nodes)
    assert "M1" in locked and "M1.1" in locked and "M1.2" in locked
    assert "M2" not in locked


def test_assert_unlocked_closed_parent_allows_child() -> None:
    nodes = [
        {"id": "M1", "parent_id": None, "milestone_execution": _me("closed")},
        {"id": "M1.1", "parent_id": "M1"},
    ]
    assert_pm_nodes_not_milestone_locked(nodes, "M1.1")


def test_assert_locked_child_raises() -> None:
    nodes = [
        {"id": "M1", "parent_id": None, "milestone_execution": _me("active")},
        {"id": "M1.1", "parent_id": "M1"},
    ]
    with pytest.raises(ValueError, match="inside milestone subtree"):
        assert_pm_nodes_not_milestone_locked(nodes, "M1.1")
