"""`specy-road indent`, `outdent` and `group-nodes`: re-level siblings in one transaction.

Re-levelling from the CLI meant one `move-node` per node, each validating the
whole roadmap, and there was no way to create a parent and move siblings under
it in one step (M21.2).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts import roadmap_crud_ops, roadmap_outline_group
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


def _deepen_to_the_cap(root: Path) -> None:
    """Hang two siblings at the outline depth cap (8 segments) under M2.1."""
    chain = ["M2.1.1", "M2.1.1.1", "M2.1.1.1.1", "M2.1.1.1.1.1", "M2.1.1.1.1.1.1"]
    ids = [*chain, f"{chain[-1]}.1", f"{chain[-1]}.2"]
    parents = ["M2.1", *chain, chain[-1]]
    extra = [
        task_node(nid, f"20000000-0000-4000-8000-0000000dd0{i:02d}", parent, f"deep-{i}")
        for i, (nid, parent) in enumerate(zip(ids, parents))
    ]
    extra[-1]["sibling_order"] = 1
    chunk = root / "roadmap" / "phases" / "T.json"
    write_json_chunk(chunk, load_json_chunk(chunk) + extra)
    for n in extra:
        (root / n["planning_dir"]).write_text("# sheet\n", encoding="utf-8")


@pytest.mark.parametrize(
    ("arrange", "node_id"),
    [
        (lambda root: _make_gate(root, "M2.1"), "M2.4"),
        (_deepen_to_the_cap, "M2.1.1.1.1.1.1.2"),
    ],
    ids=["gate-above", "depth-cap"],
)
def test_no_sibling_above_that_can_take_the_node_is_the_same_no_op(
    repo: Path, arrange, node_id: str
) -> None:
    arrange(repo)
    before = tree_bytes(repo)

    r = run_cli(repo, "indent", node_id)

    assert r.returncode == 1
    assert "no previous sibling" in r.stderr
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


@pytest.mark.parametrize("rewrite_refs", [False, True], ids=["plain", "rewrite-refs"])
def test_group_into_an_id_a_listed_node_holds(
    repo: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    rewrite_refs: bool,
) -> None:
    """B1: the holder of NEW_ID leaves it in the same transaction, chains included."""
    registry = repo / "roadmap" / "registry.yaml"
    registry.write_text(
        registry.read_text(encoding="utf-8")
        + "  - codename: middle-work\n    node_id: M1.2\n"
        "    branch: feature/rm-middle-work\n",
        encoding="utf-8",
    )
    real = roadmap_crud_ops.validate_at
    validations: list[Path] = []

    def counting(root: Path, **kwargs: object) -> None:
        validations.append(root)
        real(root, **kwargs)

    monkeypatch.setattr(roadmap_crud_ops, "validate_at", counting)
    expected = {
        "M1.1": "M1.2.1",
        "M1.2": "M1.2.2",
        "M1.2.1": "M1.2.2.1",
        "M1.2.2": "M1.2.2.2",
        "M1.2.4": "M1.2.2.4",
        "M1.3": "M1.2.3",
    }
    flags = ["--rewrite-refs"] if rewrite_refs else []

    roadmap_outline_group.main(
        ["group-nodes", "--into-new", "M1.2", "--title", "G", "M1.1", "M1.2", "M1.3",
         *flags, "--repo-root", str(repo)]
    )

    out = capsys.readouterr().out
    assert validations == [repo]
    printed = dict(re.findall(r"(M[\d.]+) -> (M[\d.]+)", out))
    assert printed == expected
    nodes = {n["id"]: n for n in nodes_by_key(repo).values()}
    assert (nodes["M1.2"]["parent_id"], nodes["M1.2"]["title"]) == ("M1", "G")
    for old, new in expected.items():
        sheet = nodes[new]["planning_dir"]
        assert sheet.startswith(f"planning/{new}_")
        assert (repo / sheet).read_text(encoding="utf-8") == f"# {new if rewrite_refs else old}\n"
    # The transient parent id (M1.4, the next free child of M1) reaches nothing.
    assert not [i for i in nodes if i.startswith("M1.4")]
    assert "M1.4" not in out
    assert not [p for p, b in tree_bytes(repo).items() if "M1.4" in p or b"M1.4" in b]
    claims = {e["codename"]: e["node_id"] for e in yaml.safe_load(registry.read_text())["entries"]}
    assert claims["middle-work"] == "M1.2.2"


def test_group_transient_id_names_no_existing_node(repo: Path) -> None:
    """The transient parent id is no node's id or id prefix, wherever that node hangs.

    M1.3 hangs under M2 (an edge-only re-parent keeps its id) with child M1.3.4,
    so M1's direct children stop at M1.2 but M1.3 and M1.3.4 are still taken.
    """
    chunk = repo / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    for n in nodes:
        if n["id"] == "M1.3":
            n["parent_id"], n["sibling_order"] = "M2", 2
    child = task_node("M1.3.4", "20000000-0000-4000-8000-0000000ee001", "M1.3", "far-four")
    write_json_chunk(chunk, [*nodes, child])
    (repo / child["planning_dir"]).write_text("# M1.3.4\n", encoding="utf-8")
    roadmap_crud_ops.validate_at(repo)
    before = ids_by_key(repo)

    id_map = group_nodes(repo, "M1.1", "G", ["M1.1", "M1.2"])

    assert id_map == {
        "M1.1": "M1.1.1",
        "M1.2": "M1.1.2",
        "M1.2.1": "M1.1.2.1",
        "M1.2.2": "M1.1.2.2",
        "M1.2.4": "M1.1.2.4",
    }
    after = nodes_by_key(repo)
    assert (after[NK_A3]["id"], after[NK_A3]["parent_id"]) == ("M1.3", "M2")
    assert after[child["node_key"]]["id"] == "M1.3.4"
    new_key = (set(after) - set(before)).pop()
    assert after[new_key]["id"] == "M1.1"


@pytest.mark.parametrize(
    ("args", "reason"),
    [
        (("--into-new", "M1.4", "M1.1", "M1.1"), "must be distinct"),
        (("--into-new", "M1.4", "M1.1", "M2.1"), "must be siblings"),
        (("--into-new", "M1.4", "M1.1", "M9"), "no roadmap node with id 'M9'"),
        (("--into-new", "M1.3", "M1.1"), "already taken"),
        # A descendant's id is never a direct child id of the common parent.
        (("--into-new", "M1.2.1", "M1.2"), "not a direct child id of M1"),
        (("--into-new", "M1.x", "M1.1"), "malformed"),
        (("--into-new", "M2.9", "M1.1"), "not a direct child id of M1"),
    ],
    ids=["duplicate", "not-siblings", "unknown", "taken", "descendant-id", "malformed", "wrong-parent"],
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


def test_a_renamed_group_sheet_names_neither_temporary_nor_final_id(repo: Path) -> None:
    """B4: the scaffold never contains a display id, so a later ``move-node --id`` cannot leave one."""
    grouped = run_cli(repo, "group-nodes", "--into-new", "M1.9", "--title", "G", "M1.1")
    assert grouped.returncode == 0, grouped.stderr

    moved = run_cli(repo, "move-node", "M1.9", "--to-parent", "M1", "--id", "M1.4")
    assert moved.returncode == 0, moved.stderr

    parent = next(n for n in nodes_by_key(repo).values() if n["id"] == "M1.4")
    text = (repo / parent["planning_dir"]).read_text(encoding="utf-8")
    assert "M1.9" not in text
    assert "M1.4" not in text
    assert "Roadmap chunk: the node this sheet's file name names" in text
