"""Tests for do_next_prompt."""

from __future__ import annotations

from pathlib import Path

import do_next_prompt as dnp


def test_write_agent_prompt_includes_leaf_execution_contract(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    brief_path = repo_root / "work" / "brief-M1.1.md"
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief_path.write_text("# brief\n", encoding="utf-8")

    nodes = [
        {
            "id": "M1",
            "type": "phase",
            "title": "Parent",
            "status": "In Progress",
            "node_key": "11111111-1111-4111-8111-111111111111",
        },
        {
            "id": "M1.1",
            "type": "milestone",
            "title": "Leaf",
            "status": "Not Started",
            "parent_id": "M1",
            "codename": "leaf-node",
            "node_key": "22222222-2222-4222-8222-222222222222",
        },
    ]
    out = dnp.write_agent_prompt(
        nodes[1],
        nodes,
        brief_path,
        repo_root=repo_root,
        work_dir=repo_root / "work",
        on_complete="pr",
    )
    text = out.read_text(encoding="utf-8")
    assert "## Execution Target" in text
    assert "**Execution Target (leaf):** `M1.1`" in text
    assert "## Ancestor Context Chain" in text
    assert "## Derived Rollup Semantics" in text
