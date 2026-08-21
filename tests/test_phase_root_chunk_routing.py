"""A phase root gets its own chunk instead of being packed into a sibling's.

A phase has no phase *ancestor*, so it used to skip the router's locality pass
and land in whichever chunk had room. Every node added underneath it then
followed it there, so one misrouted phase root pulled its whole subtree into a
file named after an unrelated phase.
"""

from __future__ import annotations

import json
from pathlib import Path

from roadmap_chunk_router_pick import pick_target_chunk
from roadmap_chunk_utils import phase_root_chunk_rel


def _fixture(root: Path, chunks: dict[str, list[dict]]) -> None:
    (root / "roadmap").mkdir(parents=True, exist_ok=True)
    for rel, nodes in chunks.items():
        p = root / "roadmap" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"nodes": nodes}, indent=2) + "\n", encoding="utf-8")
    (root / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": list(chunks)}, indent=2) + "\n",
        encoding="utf-8",
    )


def _phase(nid: str) -> dict:
    return {"id": nid, "type": "phase", "parent_id": None, "title": nid}


def test_phase_root_chunk_rel_follows_the_existing_chunk_directory(tmp_path: Path) -> None:
    _fixture(tmp_path, {"phases/M1.json": [_phase("M1")]})
    assert phase_root_chunk_rel(tmp_path, _phase("M2")) == "phases/M2.json"


def test_phase_root_chunk_rel_skips_non_phase_nodes(tmp_path: Path) -> None:
    _fixture(tmp_path, {"phases/M1.json": [_phase("M1")]})
    milestone = {"id": "M1.1", "type": "milestone", "parent_id": "M1", "title": "m"}
    assert phase_root_chunk_rel(tmp_path, milestone) is None


def test_phase_root_chunk_rel_yields_when_the_name_is_taken(tmp_path: Path) -> None:
    _fixture(tmp_path, {"phases/M1.json": [_phase("M1")], "phases/M2.json": [_phase("M2")]})
    assert phase_root_chunk_rel(tmp_path, _phase("M2")) is None


def test_phase_root_chunk_rel_yields_to_an_unincluded_file_on_disk(tmp_path: Path) -> None:
    """A dropped `includes` line must not turn into silent data loss.

    Nodes in an unincluded chunk are absent from the merged graph, so writing a
    fresh chunk over them validates cleanly and the atomic rollback never fires.
    """
    _fixture(tmp_path, {"phases/M1.json": [_phase("M1")]})
    orphan = tmp_path / "roadmap" / "phases" / "M2.json"
    orphan.write_text(
        json.dumps({"nodes": [_phase("M2"), {"id": "M2.1", "type": "milestone",
                                             "parent_id": "M2", "title": "m"}]}),
        encoding="utf-8",
    )
    assert phase_root_chunk_rel(tmp_path, _phase("M2")) is None

    decision = pick_target_chunk(tmp_path, None, None, _phase("M2"))
    assert decision.chunk_path != orphan
    assert [n["id"] for n in json.loads(orphan.read_text())["nodes"]] == ["M2", "M2.1"]


def test_new_phase_routes_to_its_own_chunk_even_when_room_exists(tmp_path: Path) -> None:
    _fixture(tmp_path, {"phases/M1.json": [_phase("M1")]})
    decision = pick_target_chunk(tmp_path, None, None, _phase("M2"))
    assert decision.is_new_chunk is True
    assert decision.chunk_rel == "phases/M2.json"


def test_explicit_chunk_hint_still_wins_for_a_phase(tmp_path: Path) -> None:
    _fixture(tmp_path, {"phases/M1.json": [_phase("M1")]})
    decision = pick_target_chunk(tmp_path, None, "phases/M1.json", _phase("M2"))
    assert decision.is_new_chunk is False
    assert decision.chunk_rel == "phases/M1.json"


def test_subtree_follows_the_phase_into_its_own_chunk(tmp_path: Path) -> None:
    _fixture(
        tmp_path,
        {"phases/M1.json": [_phase("M1")], "phases/M2.json": [_phase("M2")]},
    )
    milestone = {"id": "M2.1", "type": "milestone", "parent_id": "M2", "title": "m"}
    decision = pick_target_chunk(tmp_path, "M2", None, milestone)
    assert decision.chunk_rel == "phases/M2.json"
