"""Title ↔ codename ↔ planning_dir coupling (PM GUI autosave + CLI --set)."""

from __future__ import annotations

from pathlib import Path

from roadmap_crud_ops import edit_node_set_pairs
from roadmap_edit_fields import apply_set, title_to_codename

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


def test_apply_set_title_overwrites_stale_codename() -> None:
    """Migrated or legacy codename must not stay when title implies a different slug."""
    nk = "20000000-0000-4000-8000-000000000002"
    node = {
        "id": "M0.1",
        "node_key": nk,
        "title": "First milestone",
        "codename": "first-deliverable",
        "planning_dir": f"planning/M0.1_first-deliverable_{nk}.md",
    }
    apply_set(
        node,
        "title",
        "Renamed milestone title",
        all_ids={"M0.1"},
        all_node_keys={nk},
        self_id="M0.1",
    )
    assert node["codename"] == "renamed-milestone-title"
    assert node["planning_dir"] == f"planning/M0.1_renamed-milestone-title_{nk}.md"


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
