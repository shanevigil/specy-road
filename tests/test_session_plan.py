"""Tests for the grind-session plan analysis engine (``session_plan``)."""

from __future__ import annotations

from session_plan import compute_session_plan, session_plan_to_dict


def _leaf(nid, key, *, status="Not Started", deps=None, codename=None, ntype="task", parent=None):
    return {
        "id": nid,
        "node_key": key,
        "type": ntype,
        "title": nid,
        "status": status,
        "codename": codename if codename is not None else f"cn-{nid.lower().replace('.', '-')}",
        "dependencies": list(deps or []),
        "parent_id": parent,
    }


# node_key helpers (valid-ish UUID4 shapes)
K = {
    "M10.3": "10300000-0000-4000-8000-000000000003",
    "M10.4": "10400000-0000-4000-8000-000000000004",
    "M10.5": "10500000-0000-4000-8000-000000000005",
    "M11.1": "11100000-0000-4000-8000-000000000001",
}


def _chain_nodes():
    """M10.3, M10.4 ready; M10.5 deps {10.3,10.4}; M11.1 deps {10.5}."""
    return [
        _leaf("M10.3", K["M10.3"]),
        _leaf("M10.4", K["M10.4"]),
        _leaf("M10.5", K["M10.5"], deps=[K["M10.3"], K["M10.4"]]),
        _leaf("M11.1", K["M11.1"], deps=[K["M10.5"]]),
    ]


def _empty_reg():
    return {"version": 1, "entries": []}


def test_ready_blocked_and_waves_for_dependency_chain():
    nodes = _chain_nodes()
    plan = compute_session_plan(nodes, _empty_reg())

    assert set(plan.ready) == {"M10.3", "M10.4"}
    blocked_by = {b.node_id: b for b in plan.blocked}
    assert set(blocked_by) == {"M10.5", "M11.1"}
    assert blocked_by["M10.5"].waiting_on == ["M10.3", "M10.4"]
    assert blocked_by["M10.5"].reason == "dependency"
    assert blocked_by["M11.1"].waiting_on == ["M10.5"]

    wave_ids = [w.node_ids for w in plan.waves]
    assert wave_ids == [["M10.3", "M10.4"], ["M10.5"], ["M11.1"]]
    # Only wave 0 is dispatchable now; later waves are gated by predecessors.
    assert plan.parallel_batches[0] == ["M10.3", "M10.4"]


def test_completing_upstream_unlocks_downstream():
    nodes = _chain_nodes()
    for n in nodes:
        if n["id"] in ("M10.3", "M10.4", "M10.5"):
            n["status"] = "Complete"
    plan = compute_session_plan(nodes, _empty_reg())
    assert plan.ready == ["M11.1"]
    assert plan.blocked == []
    assert set(plan.closed) == {"M10.3", "M10.4", "M10.5"}
    assert [w.node_ids for w in plan.waves] == [["M11.1"]]


def test_gate_dependency_marks_leaf_gated():
    gate_key = "9a9a0000-0000-4000-8000-000000000000"
    nodes = [
        {
            "id": "G1",
            "node_key": gate_key,
            "type": "gate",
            "title": "Human gate",
            "status": "Not Started",
            "dependencies": [],
            "parent_id": None,
        },
        _leaf("M5.1", "50100000-0000-4000-8000-000000000001", deps=[gate_key]),
        _leaf("M5.2", "50200000-0000-4000-8000-000000000002"),
    ]
    plan = compute_session_plan(nodes, _empty_reg())
    assert set(plan.ready) == {"M5.2"}
    gated = {b.node_id: b for b in plan.blocked if b.reason == "gate"}
    assert "M5.1" in gated
    assert gated["M5.1"].waiting_on == ["G1"]
    assert plan.gated == ["M5.1"]
    assert plan.gates_open == ["G1"]
    # Gated leaf must NOT appear in any numbered wave.
    all_wave_ids = {nid for w in plan.waves for nid in w.node_ids}
    assert "M5.1" not in all_wave_ids
    assert "M5.2" in all_wave_ids


def test_claimed_leaf_is_active_not_ready_but_keeps_downstream_blocked():
    nodes = _chain_nodes()
    reg = {
        "version": 1,
        "entries": [
            {"codename": "cn-m10-3", "node_id": "M10.3", "branch": "feature/rm-cn-m10-3"},
        ],
    }
    plan = compute_session_plan(nodes, reg)
    assert "M10.3" not in plan.ready
    assert "M10.3" in plan.active
    assert "M10.4" in plan.ready
    # M10.5 still blocked (M10.3 in flight, not Complete); waves still include it later.
    blocked_ids = {b.node_id for b in plan.blocked}
    assert "M10.5" in blocked_ids
    wave_ids = [w.node_ids for w in plan.waves]
    # M10.3 (active) + M10.4 (ready) share wave 0; M10.5 wave 1; M11.1 wave 2.
    assert wave_ids == [["M10.3", "M10.4"], ["M10.5"], ["M11.1"]]
    # parallel_batches excludes the claimed leaf from the dispatch-now set.
    assert plan.parallel_batches[0] == ["M10.4"]


def test_under_filter_restricts_scope():
    nodes = [
        {"id": "M10", "node_key": "aa", "type": "phase", "title": "M10",
         "status": "Not Started", "dependencies": [], "parent_id": None, "codename": "m10"},
        _leaf("M10.3", K["M10.3"], parent="M10"),
        {"id": "M11", "node_key": "bb", "type": "phase", "title": "M11",
         "status": "Not Started", "dependencies": [], "parent_id": None, "codename": "m11"},
        _leaf("M11.1", K["M11.1"], parent="M11"),
    ]
    plan = compute_session_plan(nodes, _empty_reg(), under="M10")
    assert plan.ready == ["M10.3"]
    assert "M11.1" not in plan.ready
    assert all("M11" not in nid for w in plan.waves for nid in w.node_ids)


def test_missing_codename_leaf_reported_separately():
    nodes = [_leaf("M1.1", "c1c10000-0000-4000-8000-000000000001", codename="")]
    plan = compute_session_plan(nodes, _empty_reg())
    assert plan.ready == []
    assert plan.needs_codename == ["M1.1"]


def test_to_dict_is_json_serializable():
    import json

    plan = compute_session_plan(_chain_nodes(), _empty_reg())
    d = session_plan_to_dict(plan)
    s = json.dumps(d)  # must not raise
    assert json.loads(s)["totals"]["ready"] == 2
    assert d["blocked"][0]["waiting_on"]
