"""Tests for gate nodes and effective ancestor dependencies in do-next."""

from __future__ import annotations

import do_next_task as dnt

_NK_PREREQ = "11111111-1111-4111-8111-111111111111"
_NK_GATE = "55555555-5555-4555-8555-555555555555"

_BASE_NODE = {
    "id": "M1.1",
    "node_key": "22222222-2222-4222-8222-222222222222",
    "type": "milestone",
    "title": "Example",
    "codename": "example",
    "execution_milestone": "Agentic-led",
    "status": "Not Started",
    "dependencies": [],
    "touch_zones": [],
}


def _reg(*node_ids: str) -> dict:
    return {
        "version": 1,
        "entries": [{"node_id": nid, "codename": nid} for nid in node_ids],
    }


def test_available_respects_effective_ancestor_dependencies() -> None:
    """Prerequisites listed only on a phase block descendant leaves (inherited deps)."""
    k_phase = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    k_leaf = "22222222-2222-4222-8222-222222222222"
    phase = {
        "id": "M0",
        "node_key": k_phase,
        "type": "phase",
        "title": "Phase",
        "parent_id": None,
        "sibling_order": 0,
        "status": "Not Started",
        "dependencies": [_NK_PREREQ],
        "planning_dir": "planning/p.md",
    }
    prereq = {
        "id": "M0.0",
        "node_key": _NK_PREREQ,
        "type": "milestone",
        "title": "Prereq",
        "parent_id": "M0",
        "codename": "prereq",
        "execution_milestone": "Human-led",
        "status": "Not Started",
        "dependencies": [],
        "planning_dir": "planning/p2.md",
    }
    leaf = {
        **_BASE_NODE,
        "id": "M0.1",
        "node_key": k_leaf,
        "parent_id": "M0",
        "dependencies": [],
        "codename": "leaf-node",
    }
    assert dnt._available([phase, prereq, leaf], _reg(), {}) == []
    prereq_done = {**prereq, "status": "Complete"}
    result = dnt._available([phase, prereq_done, leaf], _reg(), {})
    assert len(result) == 1
    assert result[0]["id"] == "M0.1"


def test_available_gate_incomplete_blocks_descendant_leaf() -> None:
    k_phase = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    k_leaf = "22222222-2222-4222-8222-222222222222"
    phase = {
        "id": "M0",
        "node_key": k_phase,
        "type": "phase",
        "title": "Phase",
        "parent_id": None,
        "sibling_order": 0,
        "status": "Not Started",
        "dependencies": [_NK_GATE],
        "planning_dir": "planning/p.md",
    }
    gate = {
        "id": "M0.1",
        "node_key": _NK_GATE,
        "type": "gate",
        "title": "Approval gate",
        "parent_id": "M0",
        "sibling_order": 0,
        "status": "Not Started",
        "planning_dir": "planning/g.md",
    }
    leaf = {
        **_BASE_NODE,
        "id": "M0.2",
        "node_key": k_leaf,
        "parent_id": "M0",
        "sibling_order": 1,
        "dependencies": [],
        "codename": "leaf-node",
    }
    assert dnt._available([phase, gate, leaf], _reg(), {}) == []


def test_available_gate_complete_allows_descendant_leaf() -> None:
    k_phase = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"
    k_leaf = "22222222-2222-4222-8222-222222222222"
    phase = {
        "id": "M0",
        "node_key": k_phase,
        "type": "phase",
        "title": "Phase",
        "parent_id": None,
        "sibling_order": 0,
        "status": "Not Started",
        "dependencies": [_NK_GATE],
        "planning_dir": "planning/p.md",
    }
    gate = {
        "id": "M0.1",
        "node_key": _NK_GATE,
        "type": "gate",
        "title": "Approval gate",
        "parent_id": "M0",
        "sibling_order": 0,
        "status": "Complete",
        "planning_dir": "planning/g.md",
    }
    leaf = {
        **_BASE_NODE,
        "id": "M0.2",
        "node_key": k_leaf,
        "parent_id": "M0",
        "sibling_order": 1,
        "dependencies": [],
        "codename": "leaf-node",
    }
    result = dnt._available([phase, gate, leaf], _reg(), {})
    assert len(result) == 1
    assert result[0]["id"] == "M0.2"


def test_available_excludes_type_gate_even_if_agentic() -> None:
    gate = {
        "id": "M0.1",
        "node_key": _NK_GATE,
        "type": "gate",
        "title": "G",
        "parent_id": "M0",
        "codename": "gate-c",
        "execution_milestone": "Agentic-led",
        "status": "Not Started",
        "dependencies": [],
        "planning_dir": "planning/g.md",
    }
    phase = {
        "id": "M0",
        "node_key": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        "type": "phase",
        "title": "Phase",
        "parent_id": None,
        "dependencies": [],
        "planning_dir": "planning/p.md",
    }
    assert dnt._available([phase, gate], _reg(), {}) == []
