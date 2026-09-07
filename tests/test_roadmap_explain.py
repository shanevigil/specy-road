"""`why-blocked` and `list-gates` (findings 36 and 37)."""

from __future__ import annotations

from specy_road.bundled_scripts.roadmap_explain import explain, open_gates


def _node(nid, key, *, type_="task", status="Not Started", parent=None,
          deps=None, codename=None, title=None):
    return {
        "id": nid,
        "node_key": key,
        "type": type_,
        "title": title or f"title {nid}",
        "status": status,
        "parent_id": parent,
        "dependencies": list(deps or []),
        "codename": codename if codename is not None else f"cn-{key}",
    }


def _chain_graph():
    """M1.3 waits on M1.2, which waits on M1.1 — a two-hop chain."""
    return [
        _node("M1", "phase-one", type_="phase", codename=""),
        _node("M1.1", "alpha", parent="M1"),
        _node("M1.2", "beta", parent="M1", deps=["alpha"]),
        _node("M1.3", "gamma", parent="M1", deps=["beta"]),
    ]


def _reg(*entries):
    return {"version": 1, "entries": list(entries)}


# ---------------------------------------------------------------------------
# why-blocked
# ---------------------------------------------------------------------------


def test_the_chain_is_transitive_not_just_the_immediate_dependency():
    """The actionable item is at the bottom, which --plan does not show."""
    exp = explain(_chain_graph(), _reg(), "M1.3")

    assert exp.state == "blocked"
    assert [d.node_id for d in exp.waiting_on] == ["M1.2"]
    assert [d.node_id for d in exp.waiting_on[0].waiting_on] == ["M1.1"]


def test_a_completed_hop_drops_out_of_the_chain():
    nodes = _chain_graph()
    next(n for n in nodes if n["id"] == "M1.1")["status"] = "Complete"

    exp = explain(nodes, _reg(), "M1.3")

    assert [d.node_id for d in exp.waiting_on] == ["M1.2"]
    assert exp.waiting_on[0].waiting_on == []


def test_ready_when_every_dependency_is_complete():
    nodes = _chain_graph()
    for nid in ("M1.1", "M1.2"):
        next(n for n in nodes if n["id"] == nid)["status"] = "Complete"

    exp = explain(nodes, _reg(), "M1.3")

    assert exp.state == "ready"
    assert exp.waiting_on == []


def test_a_gate_in_the_chain_is_reported_as_gated():
    nodes = [
        _node("M1", "phase-one", type_="phase", codename=""),
        _node("M1.1", "signoff", type_="gate", parent="M1"),
        _node("M1.2", "beta", parent="M1", deps=["signoff"]),
    ]

    exp = explain(nodes, _reg(), "M1.2")

    assert exp.state == "gated"
    assert exp.waiting_on[0].is_gate is True


def test_a_claimed_node_reports_the_branch_holding_it():
    nodes = _chain_graph()
    reg = _reg({"node_id": "M1.1", "codename": "alpha", "branch": "feature/rm-alpha"})

    exp = explain(nodes, reg, "M1.1")

    assert exp.state == "active"
    assert "feature/rm-alpha" in exp.summary


def test_a_dependency_claimed_elsewhere_shows_its_branch_in_the_chain():
    nodes = _chain_graph()
    reg = _reg({"node_id": "M1.1", "codename": "alpha", "branch": "feature/rm-alpha"})

    exp = explain(nodes, reg, "M1.3")

    deepest = exp.waiting_on[0].waiting_on[0]
    assert deepest.node_id == "M1.1"
    assert deepest.claimed_by == "feature/rm-alpha"


def test_a_parent_is_a_container_not_a_missing_codename():
    """Checked before the codename, or the parent reports the wrong reason."""
    exp = explain(_chain_graph(), _reg(), "M1")

    assert exp.state == "container"
    assert "rolls up" in exp.summary


def test_a_leaf_without_a_codename_says_so():
    nodes = _chain_graph()
    next(n for n in nodes if n["id"] == "M1.1")["codename"] = ""

    exp = explain(nodes, _reg(), "M1.1")

    assert exp.state == "needs_codename"
    assert "edit-node M1.1" in exp.summary


def test_a_complete_node_is_closed():
    nodes = _chain_graph()
    next(n for n in nodes if n["id"] == "M1.1")["status"] = "Complete"

    assert explain(nodes, _reg(), "M1.1").state == "closed"


def test_an_unknown_id_is_reported_rather_than_crashing():
    exp = explain(_chain_graph(), _reg(), "M9.9")

    assert exp.state == "unknown"
    assert "M9.9" in exp.summary


def test_a_dependency_cycle_terminates():
    """validate rejects cycles, but this command gets run *because* things are odd."""
    nodes = [
        _node("M1", "phase-one", type_="phase", codename=""),
        _node("M1.1", "alpha", parent="M1", deps=["beta"]),
        _node("M1.2", "beta", parent="M1", deps=["alpha"]),
    ]

    exp = explain(nodes, _reg(), "M1.1")

    assert exp.state == "blocked"
    assert [d.node_id for d in exp.waiting_on] == ["M1.2"]


# ---------------------------------------------------------------------------
# list-gates
# ---------------------------------------------------------------------------


def _gate_graph():
    return [
        _node("M1", "phase-one", type_="phase", codename=""),
        _node("M1.1", "signoff", type_="gate", parent="M1"),
        _node("M1.2", "beta", parent="M1", deps=["signoff"]),
        _node("M2", "phase-two", type_="phase", codename=""),
        _node("M2.1", "gamma", parent="M2", deps=["signoff"]),
    ]


def test_open_gates_list_what_they_block():
    gates = open_gates(_gate_graph())

    assert [g.node_id for g in gates] == ["M1.1"]
    assert gates[0].blocks == ["M1.2", "M2.1"]


def test_a_complete_gate_is_not_listed():
    nodes = _gate_graph()
    next(n for n in nodes if n["id"] == "M1.1")["status"] = "Complete"

    assert open_gates(nodes) == []


def test_under_scopes_by_the_blocked_work_not_by_where_the_gate_lives():
    """A phase is routinely held by a gate defined somewhere else."""
    gates = open_gates(_gate_graph(), under="M2")

    assert [g.node_id for g in gates] == ["M1.1"]
    assert gates[0].blocks == ["M2.1"]


def test_under_a_phase_with_nothing_gated_returns_nothing():
    nodes = _gate_graph()
    next(n for n in nodes if n["id"] == "M2.1")["dependencies"] = []

    assert open_gates(nodes, under="M2") == []
