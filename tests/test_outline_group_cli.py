"""`specy-road indent`, `outdent` and `group-nodes`: re-level siblings in one transaction.

Re-levelling from the CLI meant one `move-node` per node, each validating the
whole roadmap, and there was no way to create a parent and move siblings under
it in one step (M21.2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts import roadmap_crud_ops
from specy_road.bundled_scripts.roadmap_chunk_utils import (
    load_json_chunk,
    write_json_chunk,
)
from specy_road.bundled_scripts.roadmap_outline_group import group_nodes
from tests.move_node_helpers import (
    NK_A,
    NK_A1,
    NK_A2,
    NK_A21,
    NK_A22,
    NK_A24,
    NK_A3,
    NK_B4,
    ids_by_key,
    lock_milestone,
    nodes_by_key,
    run_cli,
    set_zones,
    task_node,
    tree_bytes,
    unchanged_except,
    wide_fixture,
)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    wide_fixture(tmp_path)
    return tmp_path


def _make_gate(root: Path, node_id: str) -> None:
    chunk = root / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    for n in nodes:
        if n["id"] == node_id:
            n["type"] = "gate"
    write_json_chunk(chunk, nodes)


@pytest.mark.parametrize(
    ("args", "moved", "new_id", "line"),
    [
        (("indent", "M1.3"), NK_A3, "M1.2.5", "M1.3 -> M1.2.5"),
        (("outdent", "M1.2.4"), NK_A24, "M1.4", "M1.2.4 -> M1.4"),
    ],
    ids=["indent", "outdent"],
)
def test_a_shift_moves_only_the_subtree_and_prints_the_map(
    repo: Path, args: tuple[str, ...], moved: str, new_id: str, line: str
) -> None:
    before = ids_by_key(repo)

    r = run_cli(repo, *args)

    assert r.returncode == 0, r.stderr
    assert line in r.stdout
    after = ids_by_key(repo)
    assert after[moved] == new_id
    assert unchanged_except(before, after, {moved})


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (("indent", "M1.1"), "no previous sibling"),
        (("outdent", "M1"), "already at root"),
        (("indent", "M9"), "no roadmap node with id 'M9'"),
        (("outdent", "M9"), "no roadmap node with id 'M9'"),
    ],
    ids=["indent-first", "outdent-root", "indent-unknown", "outdent-unknown"],
)
def test_a_shift_with_nothing_to_do_exits_1_and_writes_nothing(
    repo: Path, args: tuple[str, ...], message: str
) -> None:
    before = tree_bytes(repo)

    r = run_cli(repo, *args)

    assert r.returncode == 1
    assert message in r.stderr
    assert tree_bytes(repo) == before


def test_indent_under_a_gate_names_the_refusal_not_a_missing_sibling(repo: Path) -> None:
    _make_gate(repo, "M2.1")
    before = tree_bytes(repo)

    r = run_cli(repo, "indent", "M2.4")

    assert r.returncode == 1
    assert "M2.4 cannot nest under M2.1" in r.stderr
    assert tree_bytes(repo) == before


@pytest.mark.parametrize(
    ("locked", "args"),
    [
        (NK_A2, ("indent", "M1.3")),  # the sibling above would gain a node
        (NK_A2, ("outdent", "M1.2.4")),
        (NK_A, ("group-nodes", "--into-new", "M1.4", "--title", "G", "M1.1")),
    ],
    ids=["indent-target", "outdent", "group"],
)
def test_a_locked_milestone_refuses_the_change(
    repo: Path, locked: str, args: tuple[str, ...]
) -> None:
    lock_milestone(repo, locked)
    before = tree_bytes(repo)

    r = run_cli(repo, *args)

    assert r.returncode == 1
    assert "active milestone execution" in r.stderr
    assert tree_bytes(repo) == before


def test_group_builds_the_parent_and_renumbers_in_argument_order(repo: Path) -> None:
    set_zones(repo, {"M1.3": ["docs/M1.3/"]})
    registry = repo / "roadmap" / "registry.yaml"
    before = ids_by_key(repo)

    r = run_cli(
        repo, "group-nodes", "--into-new", "M1.5", "--title", "Inner Group", "M1.3", "M1.2",
    )

    assert r.returncode == 0, r.stderr
    assert "M1.3 -> M1.5.1" in r.stdout
    assert "M1.2.4 -> M1.5.2.4" in r.stdout
    after = ids_by_key(repo)
    moved = {
        NK_A3: "M1.5.1",
        NK_A2: "M1.5.2",
        NK_A21: "M1.5.2.1",
        NK_A22: "M1.5.2.2",
        NK_A24: "M1.5.2.4",
    }
    assert {k: after[k] for k in moved} == moved
    new_key = (set(after) - set(before)).pop()
    parent = nodes_by_key(repo)[new_key]
    assert (parent["id"], parent["parent_id"], parent["type"]) == ("M1.5", "M1", "milestone")
    assert parent["codename"] == "inner-group"
    assert (repo / parent["planning_dir"]).is_file()
    del after[new_key]
    assert unchanged_except(before, after, set(moved))
    # The earliest listed sibling was M1.2, second under M1.
    nodes = nodes_by_key(repo)
    assert nodes[NK_A1]["sibling_order"] < parent["sibling_order"]
    assert nodes[NK_A3]["sibling_order"] < nodes[NK_A2]["sibling_order"]
    # Sheets, zones and claims follow, as for any move.
    assert (repo / f"planning/M1.5.2.2_inner-two_{NK_A22}.md").is_file()
    assert nodes[NK_A3]["touch_zones"] == ["docs/M1.5.1/"]
    claims = {e["codename"]: e["node_id"] for e in yaml.safe_load(registry.read_text())["entries"]}
    assert claims == {"alpha-work": "M1.1", "inner-two": "M1.5.2.2", "inner-four": "M1.5.2.4"}


def test_group_keeps_the_parent_between_the_unlisted_siblings(repo: Path) -> None:
    r = run_cli(repo, "group-nodes", "--into-new", "M1.4", "--title", "G", "M1.2")

    assert r.returncode == 0, r.stderr
    nodes = sorted(
        (n for n in nodes_by_key(repo).values() if n["parent_id"] == "M1"),
        key=lambda n: n["sibling_order"],
    )
    assert [n["id"] for n in nodes] == ["M1.1", "M1.4", "M1.3"]


def test_group_at_the_root_stages_a_new_chunk_and_manifest_entry(repo: Path) -> None:
    """A phase root gets its own chunk, so the manifest joins the same plan."""
    r = run_cli(
        repo, "group-nodes", "--into-new", "M3", "--title", "Top", "--type", "phase", "M1", "M2",
    )

    assert r.returncode == 0, r.stderr
    assert json.loads((repo / "roadmap" / "manifest.json").read_text())["includes"] == [
        "phases/T.json", "phases/M3.json",
    ]
    after = ids_by_key(repo)
    assert (after[NK_A], after[NK_B4]) == ("M3.1", "M3.2.4")
    assert [n["id"] for n in load_json_chunk(repo / "roadmap" / "phases" / "M3.json")] == ["M3"]


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (("--into-new", "M1.4", "M1.1", "M1.1"), "must be distinct"),
        (("--into-new", "M1.4", "M1.1", "M2.1"), "must be siblings"),
        (("--into-new", "M1.4", "M1.1", "M9"), "no roadmap node with id 'M9'"),
        (("--into-new", "M1.3", "M1.1"), "already taken"),
        # A listed sibling's own id is not free: it is still in use until the move.
        (("--into-new", "M1.1", "M1.1"), "already taken"),
        (("--into-new", "M1.x", "M1.1"), "malformed"),
        (("--into-new", "M2.9", "M1.1"), "not a direct child id of M1"),
    ],
    ids=["duplicate", "not-siblings", "unknown", "taken", "own-id", "malformed", "wrong-parent"],
)
def test_a_refused_group_leaves_the_tree_byte_for_byte_unchanged(
    repo: Path, args: tuple[str, ...], reason: str
) -> None:
    before = tree_bytes(repo)

    r = run_cli(repo, "group-nodes", "--title", "G", *args)

    assert r.returncode == 1
    assert reason in r.stderr
    assert tree_bytes(repo) == before


def test_a_group_that_fails_validation_rolls_everything_back(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = tree_bytes(repo)

    def boom(_root: Path) -> None:
        raise ValueError("roadmap: synthetic validation failure")

    monkeypatch.setattr(
        "specy_road.bundled_scripts.roadmap_move_node.run_validate_raise", boom
    )
    with pytest.raises(ValueError, match="synthetic"):
        group_nodes(repo, "M1.4", "G", ["M1.2", "M1.3"])

    assert tree_bytes(repo) == before


def test_grouping_ten_siblings_validates_the_roadmap_once(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunk = repo / "roadmap" / "phases" / "T.json"
    extra = [
        task_node(f"M2.{k}", f"20000000-0000-4000-8000-0000000cc0{k:02d}", "M2", f"wave-{k}")
        for k in range(5, 15)
    ]
    write_json_chunk(chunk, load_json_chunk(chunk) + extra)
    for n in extra:
        (repo / n["planning_dir"]).write_text("# sheet\n", encoding="utf-8")
    real = roadmap_crud_ops.validate_at
    validations: list[Path] = []

    def counting(root: Path, **kwargs: object) -> None:
        validations.append(root)
        real(root, **kwargs)

    monkeypatch.setattr(roadmap_crud_ops, "validate_at", counting)

    id_map = group_nodes(repo, "M2.15", "Wave", [n["id"] for n in extra])

    assert validations == [repo]
    assert id_map == {f"M2.{k}": f"M2.15.{k - 4}" for k in range(5, 15)}
