"""Tests for advisory review_node script."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import review_node

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture()
def tiny_repo(tmp_path: Path) -> Path:
    shutil.copytree(REPO / "schemas", tmp_path / "schemas")
    shutil.copytree(REPO / "constraints", tmp_path / "constraints")
    (tmp_path / "roadmap" / "phases").mkdir(parents=True)
    (tmp_path / "shared").mkdir(parents=True)
    (tmp_path / "shared" / "README.md").write_text("# S\n", encoding="utf-8")
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )
    (tmp_path / "roadmap" / "roadmap.yaml").write_text(
        "version: 1\nincludes:\n  - phases/T.yaml\n",
        encoding="utf-8",
    )
    (tmp_path / "roadmap" / "phases" / "T.yaml").write_text(
        """
nodes:
  - id: M99
    parent_id: null
    type: phase
    title: P
    codename: null
    execution_milestone: Human-led
    status: Complete
    touch_zones: []
    dependencies: []
    parallel_tracks: 1
  - id: M99.1
    parent_id: M99
    type: task
    title: One
    codename: one
    execution_milestone: Agentic-led
    execution_subtask: agentic
    agentic_checklist:
      artifact_action: a
      spec_citation: shared/README.md
      interface_contract: i
      constraints_note: c
      dependency_note: d
    status: Not Started
    touch_zones: []
    dependencies: []
    parallel_tracks: 1
""".lstrip(),
        encoding="utf-8",
    )
    return tmp_path


def test_review_node_mock_llm(tiny_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_OPENAI_API_KEY", "test-key")
    captured: list[str] = []

    def fake_complete(_client: object, user_content: str) -> str:
        captured.append(user_content)
        return "## Review\nok"

    monkeypatch.setattr(review_node, "_make_client", lambda: object())
    monkeypatch.setattr(review_node, "_complete", fake_complete)
    review_node.main(["M99.1", "--repo-root", str(tiny_repo)])
    assert len(captured) == 1
    assert "Brief" in captured[0]
    assert "constraints/README.md" in captured[0]
    assert "shared/README.md" in captured[0]
