"""Dependency satisfaction reads the F-013 rollup, not a parent's own status.

Regression cover for the silent stall reported against v0.1.4-rc2: a phase whose
leaf descendants were all Complete kept its authored ``status`` of
``Not Started``, and because satisfaction read that field, every leaf downstream
of it was permanently unpickable while ``roadmap.md``, ``brief``, and the PM GUI
all reported the phase as Complete. Nothing warned.
"""

from __future__ import annotations

from do_next_available import _available, _statuses_by_node_key, blocked_pick_notice
from roadmap_load import annotate_rollup_status, compute_rollup_status
from session_plan import compute_session_plan

NK = {
    "M1": "30000000-0000-4000-8000-000000000001",
    "M1.1": "30000000-0000-4000-8000-000000000002",
    "M2": "30000000-0000-4000-8000-000000000003",
    "M2.1": "30000000-0000-4000-8000-000000000004",
}


def _graph(*, phase_own_status: str, leaf_status: str = "Complete") -> list[dict]:
    """A finished phase M1, a phase M2, and M2.1 depending on M1."""
    nodes = [
        {
            "id": "M1",
            "node_key": NK["M1"],
            "parent_id": None,
            "type": "phase",
            "title": "Upstream phase",
            "status": phase_own_status,
            "dependencies": [],
        },
        {
            "id": "M1.1",
            "node_key": NK["M1.1"],
            "parent_id": "M1",
            "type": "task",
            "title": "Upstream leaf",
            "codename": "upstream-leaf",
            "status": leaf_status,
            "dependencies": [],
        },
        {
            "id": "M2",
            "node_key": NK["M2"],
            "parent_id": None,
            "type": "phase",
            "title": "Downstream phase",
            "status": "Not Started",
            "dependencies": [],
        },
        {
            "id": "M2.1",
            "node_key": NK["M2.1"],
            "parent_id": "M2",
            "type": "task",
            "title": "Downstream leaf",
            "codename": "downstream-leaf",
            "status": "Not Started",
            "dependencies": [NK["M1"]],
        },
    ]
    return annotate_rollup_status(nodes)


EMPTY_REGISTRY: dict = {"version": 1, "entries": []}


def test_stale_parent_own_status_no_longer_blocks_a_dependent_leaf() -> None:
    nodes = _graph(phase_own_status="Not Started")
    assert next(n for n in nodes if n["id"] == "M1")["status"] == "Not Started"
    assert [n["id"] for n in _available(nodes, EMPTY_REGISTRY)] == ["M2.1"]


def test_dependent_leaf_still_blocked_while_upstream_work_remains() -> None:
    nodes = _graph(phase_own_status="Not Started", leaf_status="Not Started")
    available = [n["id"] for n in _available(nodes, EMPTY_REGISTRY)]
    assert "M2.1" not in available
    assert available == ["M1.1"]


def test_statuses_by_node_key_returns_rollup_for_parents() -> None:
    statuses = _statuses_by_node_key(_graph(phase_own_status="Not Started"))
    assert statuses[NK["M1"]] == "complete"


def test_status_overrides_propagate_up_to_ancestors() -> None:
    """A feature-branch tip that is Complete ahead of its merge satisfies its parent."""
    nodes = _graph(phase_own_status="Not Started", leaf_status="In Progress")
    assert _statuses_by_node_key(nodes)[NK["M1"]] == "in progress"
    overridden = _statuses_by_node_key(nodes, {NK["M1.1"]: "complete"})
    assert overridden[NK["M1"]] == "complete"
    assert [n["id"] for n in _available(
        nodes, EMPTY_REGISTRY, status_overrides={NK["M1.1"]: "complete"}
    )] == ["M2.1"]


def test_compute_rollup_status_accepts_lowercase_overrides() -> None:
    nodes = _graph(phase_own_status="Not Started", leaf_status="Not Started")
    rollup = compute_rollup_status(nodes, {"M1.1": "complete"})
    assert rollup["M1"] == "Complete"


def test_session_plan_schedules_a_leaf_whose_dependency_rolled_up() -> None:
    """``totals.ready`` and the wave layering must agree; they used to not."""
    plan = compute_session_plan(
        _graph(phase_own_status="Not Started"), EMPTY_REGISTRY, under=None
    )
    assert plan.ready == ["M2.1"]
    assert plan.blocked == []
    assert [w.node_ids for w in plan.waves] == [["M2.1"]]
    assert plan.parallel_batches == [["M2.1"]]


def test_blocked_pick_notice_only_fires_for_blocked_leaves() -> None:
    assert blocked_pick_notice({"status": "Not Started"}) is None
    notice = blocked_pick_notice({"status": "Blocked"})
    assert notice is not None
    assert "offered first" in notice
