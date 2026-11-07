from __future__ import annotations

from pathlib import Path

from specy_road.bundled_scripts.roadmap_chunk_utils import load_json_chunk, write_json_chunk
from specy_road.bundled_scripts.scaffold_planning import scaffold_planning_for_node

from tests.test_roadmap_crud import crud_fixture_repo


def test_scaffold_restores_missing_planning_file(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    nk991 = "10000000-0000-4000-8000-000000009902"
    rel = f"planning/M99.1_one_{nk991}.md"
    p = tmp_path / rel
    assert p.is_file()
    p.unlink()
    result = scaffold_planning_for_node(tmp_path, "M99.1")
    assert p.is_file()
    assert rel in result["written"]
    text = p.read_text(encoding="utf-8")
    assert "M99.1" not in text
    assert "{{NODE_ID}}" not in text


def test_scaffold_restores_a_missing_gate_sheet_without_the_node_id(tmp_path: Path) -> None:
    crud_fixture_repo(tmp_path)
    nk992 = "10000000-0000-4000-8000-000000009903"
    chunk = tmp_path / "roadmap" / "phases" / "T.json"
    nodes = load_json_chunk(chunk)
    next(n for n in nodes if n["id"] == "M99.2")["type"] = "gate"
    write_json_chunk(chunk, nodes)
    rel = f"planning/M99.2_two_{nk992}.md"
    p = tmp_path / rel
    p.unlink()

    result = scaffold_planning_for_node(tmp_path, "M99.2")

    assert p.is_file()
    assert rel in result["written"]
    text = p.read_text(encoding="utf-8")
    assert "M99.2" not in text
    assert "{{NODE_ID}}" not in text
    assert "Why this gate exists" in text
