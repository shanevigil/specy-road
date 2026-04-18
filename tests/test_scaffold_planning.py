from __future__ import annotations

from pathlib import Path

from scaffold_planning import scaffold_planning_for_node

from tests.test_roadmap_crud import _fixture_repo


def test_scaffold_restores_missing_planning_file(tmp_path: Path) -> None:
    _fixture_repo(tmp_path)
    nk991 = "10000000-0000-4000-8000-000000009902"
    rel = f"planning/M99.1_one_{nk991}.md"
    p = tmp_path / rel
    assert p.is_file()
    p.unlink()
    result = scaffold_planning_for_node(tmp_path, "M99.1")
    assert p.is_file()
    assert rel in result["written"]
    text = p.read_text(encoding="utf-8")
    assert "M99.1" in text
    assert "{{NODE_ID}}" not in text
