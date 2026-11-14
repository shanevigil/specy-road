"""Regressions from the §7 (grind and unattended loops) sandbox run."""

from __future__ import annotations

from specy_road.bundled_scripts.session_plan import compute_session_plan


def _node(nid, key, ntype, parent=None, deps=()):
    return {
        "id": nid,
        "node_key": key,
        "type": ntype,
        "title": nid,
        "status": "Not Started",
        "codename": f"cn-{nid.lower().replace('.', '-')}",
        "dependencies": list(deps),
        "parent_id": parent,
    }


def test_plan_waves_place_leaves_that_depend_on_a_milestone():
    """F7-A: a dependency on a container resolves once its leaves are placed."""
    m11 = "11000000-0000-4000-8000-000000000001"
    nodes = [
        _node("M1", "10000000-0000-4000-8000-000000000001", "phase"),
        _node("M1.1", m11, "milestone", "M1"),
        _node("M1.1.1", "11100000-0000-4000-8000-000000000001", "task", "M1.1"),
        _node("M1.2", "12000000-0000-4000-8000-000000000001", "milestone", "M1"),
        _node("M1.2.1", "12100000-0000-4000-8000-000000000001", "task", "M1.2", [m11]),
        _node("M1.2.2", "12200000-0000-4000-8000-000000000001", "task", "M1.2", [m11]),
    ]
    plan = compute_session_plan(nodes, {"version": 1, "entries": []})
    assert [w.node_ids for w in plan.waves] == [["M1.1.1"], ["M1.2.1", "M1.2.2"]]
    assert plan.ready == ["M1.1.1"]
    assert plan.parallel_batches == [["M1.1.1"]]
