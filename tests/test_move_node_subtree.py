"""`specy-road move-node` renumbers only the moved subtree by default.

Moving one leaf used to renumber the whole outline, renaming siblings' and other
milestones' ids, sheets and claims. ``--renumber-outline`` keeps that form.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.decisions import read_decisions, write_decisions
from specy_road.history_events import RENUMBERED, diff_snapshots, snapshot
from tests.move_node_helpers import (
    base_fixture,
    NK_A2,
    NK_A21,
    NK_A22,
    NK_A24,
    NK_B4,
    ids_by_key,
    commit_project,
    git,
    nodes_by_key,
    run_cli,
    run_move_node,
    set_zones,
    sheet_names,
    tree_bytes,
    unchanged_except,
    wide_fixture,
)


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        # Default: one past M2's highest child (M2.4); nothing else moves.
        ((), {NK_A22: "M2.5", NK_A24: "M1.2.4", NK_B4: "M2.4"}),
        # Today's whole-outline renumber closes the gaps around the move.
        (("--renumber-outline",), {NK_A22: "M2.3", NK_A24: "M1.2.2", NK_B4: "M2.2"}),
    ],
    ids=["subtree-only", "renumber-outline"],
)
def test_moving_a_leaf_out_of_the_middle_of_a_milestone(
    tmp_path: Path, flags: tuple[str, ...], expected: dict[str, str]
) -> None:
    wide_fixture(tmp_path)
    before = ids_by_key(tmp_path)
    before_sheets = sheet_names(tmp_path)

    r = run_move_node(tmp_path, "--repo-root", str(tmp_path), "M1.2.2", "--to-parent", "M2", *flags)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "roadmap" / "decisions.yaml").is_file()

    after = ids_by_key(tmp_path)
    assert {k: after[k] for k in expected} == expected
    if not flags:
        assert unchanged_except(before, after, {NK_A22})
        assert before_sheets - sheet_names(tmp_path) == {f"M1.2.2_inner-two_{NK_A22}.md"}
        assert "M1.2.2 -> M2.5" in r.stdout
        assert "M1.2.4 ->" not in r.stdout


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        # A chosen free id under the new parent.
        (("M1.2.2", "--id", "M2.3"), {NK_A22: "M2.3"}),
        # The lowest gap under M2 (M2.1 and M2.4 exist).
        (("M1.2.2", "--fill-gaps"), {NK_A22: "M2.2"}),
        # A subtree's descendants follow the chosen id, keeping their gaps.
        (
            ("M1.2", "--id", "M2.2"),
            {NK_A2: "M2.2", NK_A21: "M2.2.1", NK_A22: "M2.2.2", NK_A24: "M2.2.4"},
        ),
    ],
    ids=["id", "fill-gaps", "subtree-id"],
)
def test_a_move_can_take_a_chosen_or_lowest_free_id(
    tmp_path: Path, args: tuple[str, ...], expected: dict[str, str]
) -> None:
    wide_fixture(tmp_path)
    before = ids_by_key(tmp_path)

    r = run_move_node(tmp_path, "--repo-root", str(tmp_path), "--to-parent", "M2", *args)
    assert r.returncode == 0, r.stderr

    after = ids_by_key(tmp_path)
    assert {k: after[k] for k in expected} == expected
    assert unchanged_except(before, after, set(expected))


@pytest.mark.parametrize(
    ("flags", "reason"),
    [
        (("--id", "M2.4"), "already taken"),
        (("--id", "M2.x"), "malformed"),
        (("--id", "m2.2"), "malformed"),
        (("--id", "M1.5"), "not a direct child id of M2"),
        (("--id", "M2.2.1"), "not a direct child id of M2"),
        (("--id", "M2.2", "--fill-gaps"), "--id (new_id) and --fill-gaps (fill_gaps) are mutually exclusive"),
        (("--id", "M2.2", "--renumber-outline"), "--id (new_id) and --renumber-outline (renumber_outline) are mutually exclusive"),
        (("--fill-gaps", "--renumber-outline"), "--fill-gaps (fill_gaps) and --renumber-outline (renumber_outline) are mutually exclusive"),
    ],
    ids=[
        "taken", "malformed", "lowercase", "wrong-parent", "too-deep",
        "id-with-fill-gaps", "id-with-renumber", "fill-gaps-with-renumber",
    ],
)
def test_a_bad_chosen_id_is_refused_and_writes_nothing(
    tmp_path: Path, flags: tuple[str, ...], reason: str
) -> None:
    wide_fixture(tmp_path)
    files = [tmp_path / "roadmap" / "phases" / "T.json", tmp_path / "roadmap" / "registry.yaml"]
    before = ([f.read_bytes() for f in files], sheet_names(tmp_path))

    r = run_move_node(tmp_path, "--repo-root", str(tmp_path), "M1.2.2", "--to-parent", "M2", *flags)

    assert r.returncode == 1
    assert reason in r.stderr
    assert ([f.read_bytes() for f in files], sheet_names(tmp_path)) == before


def test_moving_m0_at_the_root_with_fill_gaps_keeps_m0(tmp_path: Path) -> None:
    """The root base comes from the whole graph, so the moved M0 stays M0."""
    wide_fixture(tmp_path)
    root = ("--repo-root", str(tmp_path))
    assert run_move_node(tmp_path, *root, "M2", "--to-parent", "null", "--id", "M0").returncode == 0
    before = ids_by_key(tmp_path)

    r = run_move_node(tmp_path, *root, "M0", "--to-parent", "null", "--fill-gaps")

    assert r.returncode == 0, r.stderr
    assert ids_by_key(tmp_path) == before
    assert before[NK_B4] == "M0.4"


def test_a_subtree_move_renumbers_only_its_descendants(tmp_path: Path) -> None:
    wide_fixture(tmp_path)
    before_nodes = load_roadmap(tmp_path)["nodes"]
    before_sheets = sheet_names(tmp_path)
    before = ids_by_key(tmp_path)

    r = run_move_node(tmp_path, "--repo-root", str(tmp_path), "M1.2", "--to-parent", "M2")
    assert r.returncode == 0, r.stderr

    after = ids_by_key(tmp_path)
    moved = {NK_A2: "M2.5", NK_A21: "M2.5.1", NK_A22: "M2.5.2", NK_A24: "M2.5.4"}
    assert {k: after[k] for k in moved} == moved
    assert unchanged_except(before, after, set(moved))
    assert nodes_by_key(tmp_path)[NK_A24]["parent_id"] == "M2.5"
    # Only the moved subtree's sheets were renamed.
    assert before_sheets - sheet_names(tmp_path) == {
        f"M1.2_unnamed_{NK_A2}.md",
        f"M1.2.1_inner-one_{NK_A21}.md",
        f"M1.2.2_inner-two_{NK_A22}.md",
        f"M1.2.4_inner-four_{NK_A24}.md",
    }
    # History records a renumbering for the subtree and nothing else.
    events = diff_snapshots(
        snapshot(before_nodes), snapshot(load_roadmap(tmp_path)["nodes"]), {}
    )
    assert {e["node_key"] for e in events if e["kind"] == RENUMBERED} == set(moved)


def test_a_claimed_moved_leaf_keeps_its_claim_under_the_new_id(tmp_path: Path) -> None:
    wide_fixture(tmp_path)

    r = run_move_node(tmp_path, "--repo-root", str(tmp_path), "M1.2.2", "--to-parent", "M2")
    assert r.returncode == 0, r.stderr

    entries = yaml.safe_load((tmp_path / "roadmap" / "registry.yaml").read_text(encoding="utf-8"))
    claims = {e["codename"]: e["node_id"] for e in entries["entries"]}
    # The moved claim follows its node; the others keep their ids.
    assert claims == {"alpha-work": "M1.1", "inner-two": "M2.5", "inner-four": "M1.2.4"}


def test_a_subtree_move_rewrites_nothing_outside_the_subtree(tmp_path: Path) -> None:
    """Zones, sheets and claims outside the subtree stay as written.

    Includes zones that name a moved id as a whole segment and as a substring:
    only the subtree's own zones and its claims follow the new ids.
    """
    wide_fixture(tmp_path)
    set_zones(tmp_path, {
        "M1.3": ["docs/M1.2/", "src/M1.2.2x/", "M1.2.2", "notes/M1.2-old.md"],
        "M2.1": ["shared/M1.2.4/api.md"],
        "M1.2.4": ["docs/M1.2.4/", "docs/M1.3/"],
    })
    registry = tmp_path / "roadmap" / "registry.yaml"
    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    zones = {"alpha-work": ["docs/M1.2/"], "inner-four": ["docs/M1.2.4/"]}
    for entry in data["entries"]:
        entry["touch_zones"] = zones.get(entry["codename"], [])
    registry.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    moved = {NK_A2, NK_A21, NK_A22, NK_A24}
    # sibling_order is left out: the old parent's siblings are re-packed (order
    # kept), which changes no id, zone, sheet or claim.
    fields = ("id", "parent_id", "touch_zones", "planning_dir")

    def outside(nodes: dict[str, dict]) -> dict[str, dict]:
        return {k: {f: n[f] for f in fields} for k, n in nodes.items() if k not in moved}

    nodes_before = outside(nodes_by_key(tmp_path))
    sheets_before = {
        k: (tmp_path / n["planning_dir"]).read_bytes() for k, n in nodes_before.items()
    }

    r = run_move_node(tmp_path, "--repo-root", str(tmp_path), "M1.2", "--to-parent", "M2")
    assert r.returncode == 0, r.stderr

    after = nodes_by_key(tmp_path)
    assert outside(after) == nodes_before
    assert {
        k: (tmp_path / after[k]["planning_dir"]).read_bytes() for k in nodes_before
    } == sheets_before
    claims = {
        e["codename"]: e
        for e in yaml.safe_load(registry.read_text(encoding="utf-8"))["entries"]
    }
    assert claims["alpha-work"]["node_id"] == "M1.1"
    assert claims["alpha-work"]["touch_zones"] == ["docs/M1.2/"]
    # The subtree's own zones and claims follow it; a zone naming M1.3 does not.
    assert after[NK_A24]["touch_zones"] == ["docs/M2.5.4/", "docs/M1.3/"]
    assert claims["inner-four"]["node_id"] == "M2.5.4"
    assert claims["inner-four"]["touch_zones"] == ["docs/M2.5.4/"]


def test_a_move_rewrites_zones_naming_the_moved_sheet_in_both_forms(tmp_path: Path) -> None:
    """A zone naming the node's own sheet follows the rename, as does a docs/<old id>/ zone."""
    top, root = tmp_path, tmp_path / "sr"
    wide_fixture(root)
    old = f"planning/M1.2.2_inner-two_{NK_A22}.md"
    set_zones(root, {"M1.2.2": [old, f"sr/{old}", "docs/M1.2.2/"]})
    registry = root / "roadmap" / "registry.yaml"
    data = yaml.safe_load(registry.read_text(encoding="utf-8"))
    for entry in data["entries"]:
        if entry["codename"] == "inner-two":
            entry["touch_zones"] = [old, f"sr/{old}", "docs/M1.2.2/"]
    registry.write_text(yaml.dump(data, sort_keys=False), encoding="utf-8")
    commit_project(top, root)

    r = run_move_node(root, "--repo-root", str(root), "M1.2.2", "--to-parent", "M2")
    assert r.returncode == 0, r.stderr

    new = f"planning/M2.5_inner-two_{NK_A22}.md"
    expected = [new, f"sr/{new}", "docs/M2.5/"]
    assert nodes_by_key(root)[NK_A22]["touch_zones"] == expected
    claims = {e["codename"]: e for e in yaml.safe_load(registry.read_text(encoding="utf-8"))["entries"]}
    assert claims["inner-two"]["touch_zones"] == expected
    for _ in ("unstaged", "staged"):
        v = run_cli(root, "validate")
        assert v.returncode == 0, v.stderr
        assert "names a planning sheet" not in v.stdout + v.stderr
        git(top, "add", "-A")


def _entry(eid: str, kind: str, node: str, *, status: str = "open", summary: str | None = None) -> dict:
    entry: dict = {
        "id": eid,
        "kind": kind,
        "summary": summary or eid,
        "asked": "2020-01-01",
        "status": status,
        "node": node,
    }
    if kind != "preference":
        entry.update(
            why_now="why",
            options=[{"label": "a", "effect": "b"}],
            recommendation="a",
            recommendation_reason="r",
            default_if_unanswered="a",
        )
    if status == "closed":
        entry.update(answer="a", closed="2020-01-02")
    return entry


def _nodes_of(root: Path) -> dict[str, dict]:
    doc = read_decisions(root / "roadmap" / "decisions.yaml")
    return {e["id"]: e for e in doc["entries"]}


def test_a_move_rewrites_decision_nodes_on_moved_ids_only(tmp_path: Path) -> None:
    """Open, closed and preference entries on moved ids follow; an unmoved id stays."""
    wide_fixture(tmp_path)
    write_decisions(tmp_path / "roadmap" / "decisions.yaml", {"version": 1, "entries": [
        _entry("Dopen", "decision", "M1.2.2", summary="keep M1.2.2"),
        _entry("Dclosed", "decision", "M1.2.4", status="closed", summary="keep M1.2.4"),
        _entry("Pmove", "preference", "M1.2", summary="keep M1.2"),
        _entry("Dstay", "decision", "M2.4", summary="keep M2.4"),
    ]})

    r = run_move_node(tmp_path, "--repo-root", str(tmp_path), "M1.2", "--to-parent", "M2")
    assert r.returncode == 0, r.stderr

    by_id = _nodes_of(tmp_path)
    assert {i: by_id[i]["node"] for i in by_id} == {
        "Dopen": "M2.5.2", "Dclosed": "M2.5.4", "Pmove": "M2.5", "Dstay": "M2.4",
    }
    assert by_id["Dopen"]["summary"] == "keep M1.2.2"
    assert by_id["Dclosed"]["summary"] == "keep M1.2.4"
    assert by_id["Pmove"]["summary"] == "keep M1.2"


def test_a_move_leaves_an_unmatched_ledger_byte_for_byte(tmp_path: Path) -> None:
    wide_fixture(tmp_path)
    path = tmp_path / "roadmap" / "decisions.yaml"
    write_decisions(path, {"version": 1, "entries": [_entry("Dstay", "decision", "M2.4")]})
    before = path.read_bytes()

    r = run_move_node(tmp_path, "--repo-root", str(tmp_path), "M1.2.2", "--to-parent", "M2")

    assert r.returncode == 0, r.stderr
    assert path.read_bytes() == before


def test_renumber_outline_swaps_decision_nodes_in_one_lookup(tmp_path: Path) -> None:
    """Each ledger node is replaced once, so a swap does not apply the map twice."""
    base_fixture(tmp_path)
    write_decisions(tmp_path / "roadmap" / "decisions.yaml", {"version": 1, "entries": [
        _entry("Da", "decision", "M1", summary="was M1"),
        _entry("Db", "decision", "M2", summary="was M2"),
        _entry("Dc", "preference", "M1.1", summary="was M1.1"),
        _entry("Dd", "preference", "M2.1", summary="was M2.1"),
    ]})

    r = run_move_node(
        tmp_path, "--repo-root", str(tmp_path),
        "M2", "--to-parent", "null", "--index", "0", "--renumber-outline",
    )
    assert r.returncode == 0, r.stderr

    by_id = _nodes_of(tmp_path)
    assert {i: by_id[i]["node"] for i in ("Da", "Db", "Dc", "Dd")} == {
        "Da": "M2", "Db": "M1", "Dc": "M2.1", "Dd": "M1.1",
    }
    assert by_id["Da"]["summary"] == "was M1"
    assert by_id["Dd"]["summary"] == "was M2.1"


def test_a_renumber_outline_swap_rewrites_a_yaml_aliased_entry_once(tmp_path: Path) -> None:
    """A YAML alias is the same mapping twice; the swap uses the node it had when loaded."""
    base_fixture(tmp_path)
    path = tmp_path / "roadmap" / "decisions.yaml"
    path.write_text(
        "version: 1\n"
        "entries:\n"
        "  - &from_m1\n"
        "    id: Da\n"
        "    kind: decision\n"
        "    summary: was M1\n"
        "    asked: '2020-01-01'\n"
        "    status: open\n"
        "    node: M1\n"
        "    why_now: why\n"
        "    options:\n"
        "      - {label: a, effect: b}\n"
        "    recommendation: a\n"
        "    recommendation_reason: r\n"
        "    default_if_unanswered: a\n"
        "  - *from_m1\n"
        "  - &from_m2\n"
        "    id: Db\n"
        "    kind: decision\n"
        "    summary: was M2\n"
        "    asked: '2020-01-01'\n"
        "    status: open\n"
        "    node: M2\n"
        "    why_now: why\n"
        "    options:\n"
        "      - {label: a, effect: b}\n"
        "    recommendation: a\n"
        "    recommendation_reason: r\n"
        "    default_if_unanswered: a\n"
        "  - *from_m2\n",
        encoding="utf-8",
    )
    loaded = read_decisions(path)
    assert loaded["entries"][0] is loaded["entries"][1]
    assert loaded["entries"][2] is loaded["entries"][3]

    r = run_move_node(
        tmp_path, "--repo-root", str(tmp_path),
        "M2", "--to-parent", "null", "--index", "0", "--renumber-outline",
    )
    assert r.returncode == 0, r.stderr

    entries = read_decisions(path)["entries"]
    assert [e["node"] for e in entries] == ["M2", "M2", "M1", "M1"]
    assert [e["id"] for e in entries] == ["Da", "Da", "Db", "Db"]
    assert [e["summary"] for e in entries] == ["was M1", "was M1", "was M2", "was M2"]


# Text that is not a decisions document. Falsy roots are the class read_decisions
# would replace with an empty ledger before a schema check.
_INVALID_LEDGER_TEXT = {
    "yaml": "version: [\n",
    "sequence": "- not-a-mapping\n",
    "empty": "",
    "empty_sequence": "[]\n",
    "empty_mapping": "{}\n",
    "null": "null\n",
    "false": "false\n",
    "zero": "0\n",
}


@pytest.mark.parametrize(
    "kind",
    ["validation", *_INVALID_LEDGER_TEXT, "utf8", "unreadable"],
)
def test_a_refused_move_leaves_the_tree_byte_for_byte_unchanged(tmp_path: Path, kind: str) -> None:
    wide_fixture(tmp_path)
    ledger = tmp_path / "roadmap" / "decisions.yaml"
    if kind in _INVALID_LEDGER_TEXT:
        ledger.write_text(_INVALID_LEDGER_TEXT[kind], encoding="utf-8")
    elif kind == "utf8":
        ledger.write_bytes(b"\xff\xfe not utf-8")
    elif kind == "unreadable":
        ledger.write_text("version: 1\nentries: []\n", encoding="utf-8")
    else:
        write_decisions(ledger, {"version": 1, "entries": [_entry("Dopen", "decision", "M1.2.2")]})
        chunk = tmp_path / "roadmap" / "phases" / "T.json"
        nodes = load_json_chunk(chunk)
        title = next(n["title"] for n in nodes if n["id"] == "M1.1")
        for n in nodes:
            if n["id"] == "M1.3":
                n["title"] = title
        write_json_chunk(chunk, nodes)
    before = tree_bytes(tmp_path)
    if kind == "unreadable":
        ledger.chmod(0)
    try:
        r = run_move_node(tmp_path, "--repo-root", str(tmp_path), "M1.2.2", "--to-parent", "M2")
    finally:
        if kind == "unreadable":
            ledger.chmod(0o644)

    assert r.returncode == 1
    assert tree_bytes(tmp_path) == before
    if kind == "validation":
        assert "duplicate title" in r.stderr
    else:
        assert "roadmap/decisions.yaml" in r.stderr
