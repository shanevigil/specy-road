"""`specy-road move-node` renumbers only the moved subtree by default.

Moving one leaf used to renumber the whole outline, renaming siblings' and other
milestones' ids, sheets and claims. ``--renumber-outline`` keeps that form.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.history_events import RENUMBERED, diff_snapshots, snapshot
from tests.move_node_helpers import (
    NK_A2,
    NK_A21,
    NK_A22,
    NK_A24,
    NK_B4,
    ids_by_key,
    nodes_by_key,
    run_move_node,
    set_zones,
    sheet_names,
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
        (("--id", "M2.2", "--fill-gaps"), "mutually exclusive"),
        (("--id", "M2.2", "--renumber-outline"), "cannot be combined with --renumber-outline"),
        (("--fill-gaps", "--renumber-outline"), "cannot be combined with --renumber-outline"),
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
