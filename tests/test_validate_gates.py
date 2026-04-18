"""Tests for ``validate_gates`` (roadmap type gate)."""

from __future__ import annotations

import pytest

from validate_roadmap_gates import validate_gates


def test_validate_gates_rejects_children() -> None:
    kg = "55555555-5555-4555-8555-555555555555"
    nodes = [
        {
            "id": "M0",
            "node_key": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            "type": "phase",
            "title": "P",
            "planning_dir": "planning/p.md",
            "parent_id": None,
        },
        {
            "id": "M0.1",
            "node_key": kg,
            "type": "gate",
            "title": "G",
            "planning_dir": "planning/g.md",
            "parent_id": "M0",
        },
        {
            "id": "M0.1.1",
            "node_key": "66666666-6666-4666-8666-666666666666",
            "type": "task",
            "title": "T",
            "planning_dir": "planning/t.md",
            "parent_id": "M0.1",
        },
    ]
    with pytest.raises(SystemExit):
        validate_gates(nodes)


def test_validate_gates_rejects_parent_not_vision_or_phase() -> None:
    kg = "55555555-5555-4555-8555-555555555555"
    nodes = [
        {
            "id": "M0.1",
            "node_key": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
            "type": "milestone",
            "title": "M",
            "planning_dir": "planning/m.md",
            "parent_id": None,
        },
        {
            "id": "M0.1.1",
            "node_key": kg,
            "type": "gate",
            "title": "G",
            "planning_dir": "planning/g.md",
            "parent_id": "M0.1",
        },
    ]
    with pytest.raises(SystemExit):
        validate_gates(nodes)
