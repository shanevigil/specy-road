"""Public outline scenarios: indent, outdent and reparent, including refusals.

These call ``apply_indent``, ``apply_outdent`` and ``move_node_outline`` — the
functions the CLI and the PM GUI both use — so a later fold of the CRUD modules
still has a green check that does not reach into private names.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from specy_road.bundled_scripts.roadmap_outline_ops import (
    apply_indent,
    apply_outdent,
    move_node_outline,
)
from tests.move_node_helpers import (
    NK_A3,
    NK_A24,
    ids_by_key,
    nodes_by_key,
    tree_bytes,
    unchanged_except,
    wide_fixture,
)


def set_type(root: Path, node_id: str, node_type: str) -> None:
    """Rewrite one node's ``type`` in the fixture chunk."""
    chunk = root / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    for item in nodes:
        if item["id"] == node_id:
            item["type"] = node_type
    write_json_chunk(chunk, nodes)


def _key(root: Path, node_id: str) -> str:
    return next(key for key, node in nodes_by_key(root).items() if node["id"] == node_id)


def test_indent_nests_the_node_under_the_previous_sibling(tmp_path: Path) -> None:
    wide_fixture(tmp_path)
    before = ids_by_key(tmp_path)

    mapping = apply_indent(tmp_path, "M1.3")

    assert mapping is not None
    assert mapping["M1.3"] == "M1.2.5"
    moved = nodes_by_key(tmp_path)[NK_A3]
    assert moved["id"] == "M1.2.5"
    assert moved["parent_id"] == "M1.2"
    assert unchanged_except(before, ids_by_key(tmp_path), {NK_A3})


def test_outdent_places_the_node_after_its_former_parent(tmp_path: Path) -> None:
    wide_fixture(tmp_path)
    before = ids_by_key(tmp_path)

    mapping = apply_outdent(tmp_path, "M1.2.4")

    assert mapping is not None
    assert mapping["M1.2.4"] == "M1.4"
    moved = nodes_by_key(tmp_path)[NK_A24]
    assert moved["id"] == "M1.4"
    assert moved["parent_id"] == "M1"
    assert unchanged_except(before, ids_by_key(tmp_path), {NK_A24})


def test_reparent_moves_the_node_under_the_named_parent(tmp_path: Path) -> None:
    wide_fixture(tmp_path)

    mapping = move_node_outline(tmp_path, NK_A3, "M2", 0)

    moved = nodes_by_key(tmp_path)[NK_A3]
    assert moved["parent_id"] == "M2"
    assert moved["sibling_order"] == 0
    assert moved["id"] == mapping["M1.3"]
    assert moved["id"].startswith("M2.")


@pytest.mark.parametrize(
    ("arrange", "shift", "node_id"),
    [
        (lambda root: None, apply_indent, "M1.1"),
        (lambda root: None, apply_outdent, "M1"),
        (lambda root: set_type(root, "M1.2", "gate"), apply_indent, "M1.3"),
        (lambda root: set_type(root, "M1.2.2", "gate"), apply_indent, "M1.2.2"),
    ],
    ids=["indent-first", "outdent-root", "indent-under-gate", "indent-gate-under-task"],
)
def test_a_shift_that_cannot_happen_writes_nothing(
    tmp_path: Path, arrange, shift, node_id: str
) -> None:
    wide_fixture(tmp_path)
    arrange(tmp_path)
    before = tree_bytes(tmp_path)

    assert shift(tmp_path, node_id) is None

    assert tree_bytes(tmp_path) == before


@pytest.mark.parametrize("shift", [apply_indent, apply_outdent], ids=["indent", "outdent"])
def test_a_shift_of_an_unknown_id_raises(tmp_path: Path, shift) -> None:
    wide_fixture(tmp_path)
    before = tree_bytes(tmp_path)

    with pytest.raises(ValueError, match="unknown node id"):
        shift(tmp_path, "M9")

    assert tree_bytes(tmp_path) == before


def test_reparent_of_an_unknown_node_raises(tmp_path: Path) -> None:
    wide_fixture(tmp_path)
    before = tree_bytes(tmp_path)

    with pytest.raises(ValueError, match="unknown node_key"):
        move_node_outline(tmp_path, "00000000-0000-4000-8000-000000000099", "M2", 0)

    assert tree_bytes(tmp_path) == before


@pytest.mark.parametrize(
    ("node_id", "parent", "index", "message"),
    [
        ("M1.1", "M9", 0, "unknown new_parent_id"),
        ("M1", "M1", 0, "cannot move node under itself"),
        ("M1", "M1.1", 0, "cannot move node under its descendant"),
        ("M1.1", "M2", 99, "new_index out of range"),
    ],
)
def test_reparent_validation_error_leaves_the_tree(
    tmp_path: Path, node_id: str, parent: str, index: int, message: str
) -> None:
    wide_fixture(tmp_path)
    before = tree_bytes(tmp_path)

    with pytest.raises(ValueError, match=message):
        move_node_outline(tmp_path, _key(tmp_path, node_id), parent, index)

    assert tree_bytes(tmp_path) == before


@pytest.mark.parametrize(
    ("arrange", "node_id", "parent", "message"),
    [
        (
            lambda root: set_type(root, "M2", "gate"),
            "M1.1",
            "M2",
            "cannot move node under a gate",
        ),
        (
            lambda root: set_type(root, "M1.1", "gate"),
            "M1.1",
            None,
            "gate must have a vision, phase, or milestone parent",
        ),
        (
            lambda root: set_type(root, "M1.2.1", "gate"),
            "M1.2.1",
            "M1.3",
            "direct child of vision, phase, or milestone",
        ),
    ],
    ids=["under-gate", "gate-at-root", "gate-under-task"],
)
def test_reparent_refuses_an_illegal_gate_move(
    tmp_path: Path, arrange, node_id: str, parent: str | None, message: str
) -> None:
    wide_fixture(tmp_path)
    arrange(tmp_path)
    before = tree_bytes(tmp_path)

    with pytest.raises(ValueError, match=message):
        move_node_outline(tmp_path, _key(tmp_path, node_id), parent, 0)

    assert tree_bytes(tmp_path) == before
