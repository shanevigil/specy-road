"""Indenting a node and then outdenting it restores every node's parent and sibling order.

Through ``apply_indent`` and ``apply_outdent``, the functions the CLI and the PM GUI call, on a
generated outline of two root phases, each with up to two levels of at most three tasks below it
(at most 26 nodes, so the one chunk stays under the roadmap line limit; three children let a moved
node have a sibling after it). A node with a sibling above it is indented under that sibling and
outdented back. No domain exclusions.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from specy_road.roadmap_load import load_roadmap
from specy_road.roadmap_outline_ops import apply_indent, apply_outdent, ordered_sibling_ids
from tests.helpers import REPO, SCHEMAS
from tests.move_node_helpers import phase_node, task_node
from tests.support.roadmap import roadmap_repo


def subtrees(depth: int) -> st.SearchStrategy[list]:
    """A node's children, each a list of its own children, ``depth`` levels deep at most."""
    if depth == 0:
        return st.just([])
    return st.lists(subtrees(depth - 1), max_size=3)


@pytest.fixture(scope="module")
def template(tmp_path_factory) -> Path:
    """Schemas and constraints a roadmap write validates against, copied once."""
    root = tmp_path_factory.mktemp("outline-template")
    shutil.copytree(SCHEMAS, root / "schemas")
    shutil.copytree(REPO / "constraints", root / "constraints")
    (root / "shared").mkdir()
    (root / "shared" / "README.md").write_text("# Shared\n", encoding="utf-8")
    return root


def write_outline(root: Path, phases: list[list]) -> list[str]:
    """Write the outline; return the ids of nodes that have a sibling above."""
    nodes: list[dict] = []
    movable: list[str] = []

    def add(children: list[list], parent: str) -> None:
        for order, grandchildren in enumerate(children):
            nid = f"{parent}.{order + 1}"
            key = f"30000000-0000-4000-8000-{len(nodes):012d}"
            node = task_node(nid, key, parent, f"work-{len(nodes)}")
            node["sibling_order"] = order
            nodes.append(node)
            movable.extend([nid] if order else [])
            add(grandchildren, nid)

    for order, children in enumerate(phases):
        nid = f"M{order + 1}"
        nodes.append(phase_node(nid, f"30000000-0000-4000-8000-{len(nodes):012d}", order))
        movable.extend([nid] if order else [])
        add(children, nid)
    roadmap_repo(root, nodes)
    return movable


def shape(root: Path) -> dict[str, tuple[str | None, int]]:
    """Each node's parent key and its position among that parent's children, by node key."""
    nodes = load_roadmap(root)["nodes"]
    by_id = {n["id"]: n for n in nodes}
    out: dict[str, tuple[str | None, int]] = {}
    for parent in [None, *by_id]:
        for index, nid in enumerate(ordered_sibling_ids(nodes, parent, by_id)):
            out[by_id[nid]["node_key"]] = (by_id[parent]["node_key"] if parent else None, index)
    return out


@given(phases=st.lists(subtrees(2), min_size=2, max_size=2), pick=st.integers(0, 63))
def test_indent_then_outdent_restores_parent_and_sibling_order(
    tmp_path_factory, template: Path, phases: list[list], pick: int
) -> None:
    """Indent a node under the sibling above, outdent it back: the outline is as it was."""
    root = tmp_path_factory.mktemp("outline")
    shutil.copytree(template, root, dirs_exist_ok=True)
    movable = write_outline(root, phases)
    node_id = movable[pick % len(movable)]
    before = shape(root)

    moved = apply_indent(root, node_id)
    assert moved is not None, node_id
    assert apply_outdent(root, moved.get(node_id, node_id)) is not None

    assert shape(root) == before
