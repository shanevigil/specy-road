"""Tests for display id renumbering and outline move."""

from __future__ import annotations

from roadmap_outline_renumber import renumber_display_ids_inplace
from roadmap_layout import (
    compute_depths,
    dependency_inheritance_display,
    effective_dependency_keys,
)


def test_renumber_display_ids_small_tree() -> None:
    nodes = [
        {
            "id": "M0",
            "node_key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "parent_id": None,
            "dependencies": [],
            "sibling_order": 0,
        },
        {
            "id": "M0.1",
            "node_key": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "parent_id": "M0",
            "dependencies": [],
            "sibling_order": 0,
        },
    ]
    renumber_display_ids_inplace(nodes)
    assert nodes[0]["id"] == "M0"
    assert nodes[1]["id"] == "M0.1"


def test_effective_dependency_includes_ancestor() -> None:
    kx = "30000000-0000-4000-8000-000000000001"
    k0 = "10000000-0000-4000-8000-000000000001"
    k1 = "10000000-0000-4000-8000-000000000002"
    k2 = "10000000-0000-4000-8000-000000000003"
    nodes = [
        {
            "id": "MX",
            "node_key": kx,
            "parent_id": None,
            "dependencies": [],
        },
        {
            "id": "M0",
            "node_key": k0,
            "parent_id": None,
            "dependencies": [kx],
        },
        {
            "id": "M0.1",
            "node_key": k1,
            "parent_id": "M0",
            "dependencies": [],
        },
        {
            "id": "M0.1.1",
            "node_key": k2,
            "parent_id": "M0.1",
            "dependencies": [],
        },
    ]
    eff = effective_dependency_keys(nodes)
    assert kx in eff[k2]
    depths = compute_depths(nodes)
    assert depths["M0.1.1"] >= 1


def test_dependency_inheritance_display_splits_explicit() -> None:
    kx = "30000000-0000-4000-8000-000000000001"
    k0 = "10000000-0000-4000-8000-000000000001"
    k1 = "10000000-0000-4000-8000-000000000002"
    k2 = "10000000-0000-4000-8000-000000000003"
    nodes = [
        {
            "id": "MX",
            "node_key": kx,
            "parent_id": None,
            "dependencies": [],
        },
        {
            "id": "M0",
            "node_key": k0,
            "parent_id": None,
            "dependencies": [kx],
        },
        {
            "id": "M0.1",
            "node_key": k1,
            "parent_id": "M0",
            "dependencies": [],
        },
        {
            "id": "M0.1.1",
            "node_key": k2,
            "parent_id": "M0.1",
            "dependencies": [kx],
        },
    ]
    inh = dependency_inheritance_display(nodes)
    assert inh["M0.1.1"]["explicit"] == ["MX"]
    assert inh["M0.1.1"]["inherited"] == []
    assert inh["M0.1"]["explicit"] == []
    assert inh["M0.1"]["inherited"] == ["MX"]
