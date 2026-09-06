"""Title ↔ codename ↔ planning_dir coupling (PM GUI autosave + CLI --set)."""

from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.roadmap_crud_ops import edit_node_set_pairs
from specy_road.bundled_scripts.roadmap_edit_fields import apply_set, title_to_codename

from tests.test_roadmap_crud import _fixture_repo

_NK = "10000000-0000-4000-8000-000000009901"


def test_apply_set_title_syncs_codename_and_planning_dir() -> None:
    node = {
        "id": "M0",
        "node_key": _NK,
        "title": "First phase — planning and contracts",
        "codename": "first-phase-planning-and-contracts",
        "planning_dir": f"planning/M0_first-phase-planning-and-contracts_{_NK}.md",
    }
    apply_set(
        node,
        "title",
        "First phase — planning and contract",
        all_ids={"M0"},
        all_node_keys={_NK},
        self_id="M0",
    )
    assert node["codename"] == "first-phase-planning-and-contract"
    assert node["planning_dir"] == f"planning/M0_first-phase-planning-and-contract_{_NK}.md"


_NK2 = "20000000-0000-4000-8000-000000000002"


def _hand_picked_node() -> dict:
    """A node whose codename is *not* its title's slug — so a human chose it."""
    return {
        "id": "M0.1",
        "node_key": _NK2,
        "title": "First milestone",
        "codename": "first-deliverable",
        "planning_dir": f"planning/M0.1_first-deliverable_{_NK2}.md",
    }


def _retitle(node: dict, title: str, **kw) -> None:
    apply_set(
        node,
        "title",
        title,
        all_ids={node["id"]},
        all_node_keys={node["node_key"]},
        self_id=node["id"],
        **kw,
    )


def test_a_hand_picked_codename_survives_a_title_edit() -> None:
    """The codename is the branch identity; rewriting it breaks feature/rm-*."""
    node = _hand_picked_node()
    notes: list[str] = []

    _retitle(node, "Renamed milestone title", notify=notes.append)

    assert node["codename"] == "first-deliverable"
    assert node["planning_dir"] == f"planning/M0.1_first-deliverable_{_NK2}.md"
    assert notes and "first-deliverable" in notes[0]
    assert "--sync-codename" in notes[0]


def test_sync_codename_forces_the_rewrite() -> None:
    node = _hand_picked_node()

    _retitle(node, "Renamed milestone title", sync_codename=True)

    assert node["codename"] == "renamed-milestone-title"
    assert node["planning_dir"] == f"planning/M0.1_renamed-milestone-title_{_NK2}.md"


def test_a_missing_codename_is_still_derived() -> None:
    node = _hand_picked_node()
    node.pop("codename")

    _retitle(node, "Renamed milestone title")

    assert node["codename"] == "renamed-milestone-title"


def test_edit_title_renames_planning_file_on_disk(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    old = tmp_path / "planning" / f"M99_unnamed_{_NK}.md"
    assert old.is_file()
    edit_node_set_pairs(
        tmp_path,
        "M99",
        [("title", "Phase Alpha Long Enough")],
    )
    slug = title_to_codename("Phase Alpha Long Enough")
    assert slug == "phase-alpha-long-enough"
    new = tmp_path / "planning" / f"M99_{slug}_{_NK}.md"
    assert new.is_file()
    assert not old.exists()
