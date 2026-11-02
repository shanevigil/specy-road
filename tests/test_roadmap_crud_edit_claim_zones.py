"""`edit-node --set touch_zones=` keeps an active claim's zones in step (M10.14).

Pickup copies a leaf's zones into its registry row, and the review packet and
the finish implementation check read that row first. Before this, widening a
claimed leaf's zones with edit-node left the row behind, so the packet kept
flagging files that were now in zone and finish could refuse.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.review_repo_helpers import git, make_review_repo

from specy_road.bundled_scripts import review_packet as rp
from specy_road.bundled_scripts import roadmap_chunk_router
from specy_road.bundled_scripts.roadmap_crud_ops import cmd_edit, edit_node_set_pairs
from specy_road.finish_implementation_check import implementation_gate_error
from specy_road.registry_yaml import read_registry, registry_path


def _edit(repo: Path, *sets: str) -> None:
    cmd_edit(SimpleNamespace(repo_root=str(repo), node_id="M1.1", set=list(sets), sync_codename=False))


def _claim(repo: Path) -> dict:
    return read_registry(registry_path(repo))["entries"][0]


def test_edit_rewrites_claim_zones_and_names_the_claim(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    _edit(repo, "touch_zones=src", "touch_zones=docs")
    assert _claim(repo)["touch_zones"] == ["src", "docs"]
    err = capsys.readouterr().err
    notes = [ln for ln in err.splitlines() if "claim" in ln]
    assert notes == ["[note] updated claim 'thing' in roadmap/registry.yaml: touch_zones now match M1.1"]


def test_edit_without_zones_leaves_the_claim_alone(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    before = registry_path(repo).read_bytes()
    _edit(repo, "title=Renamed thing")
    assert registry_path(repo).read_bytes() == before
    assert "claim" not in capsys.readouterr().err


def test_edit_of_an_unclaimed_node_leaves_the_registry_alone(tmp_path: Path, capsys) -> None:
    repo = make_review_repo(tmp_path)
    reg = registry_path(repo)
    reg.write_text("version: 1\nentries: []\n", encoding="utf-8")
    before = reg.read_bytes()
    _edit(repo, "touch_zones=lib")
    assert reg.read_bytes() == before
    assert "claim" not in capsys.readouterr().err


def test_rejected_edit_rolls_the_claim_back(tmp_path: Path, monkeypatch) -> None:
    repo = make_review_repo(tmp_path)
    before = registry_path(repo).read_bytes()

    def reject(*_a, **_k):
        raise ValueError("rejected")

    monkeypatch.setattr(roadmap_chunk_router, "write_node_update", reject)
    with pytest.raises(ValueError, match="rejected"):
        edit_node_set_pairs(repo, "M1.1", [("touch_zones", "lib")])
    assert registry_path(repo).read_bytes() == before


def test_packet_reads_widened_zones(tmp_path: Path) -> None:
    """A2: the coordinator widens the zones on dev; the packet stops flagging docs/x.md."""
    repo = make_review_repo(tmp_path)
    git(repo, "checkout", "-q", "dev")
    assert "- `docs/x.md`  **← outside touch zones**" in rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    _edit(repo, "touch_zones=src", "touch_zones=docs")
    git(repo, "commit", "-qam", "widen M1.1 zones")
    text = rp.build_packet(repo, "M1.1", ref=None, verify_cmds=[])
    assert "- `docs/x.md`\n" in text
    assert "outside the touch zones" not in text


def test_finish_check_reads_edited_zones(tmp_path: Path) -> None:
    """A2/A3: the finish gate judges the claim's new zones, and its hint says why edit-node suffices."""
    repo = make_review_repo(tmp_path)
    _edit(repo, "touch_zones=lib")
    error = implementation_gate_error(
        repo, node_id="M1.1", zones=_claim(repo)["touch_zones"], remote="origin", integration_branch="dev"
    )
    assert error is not None and "('lib')" in error
    assert "edit-node also rewrites this claim's registry row" in error
