"""Tests for advisory review_node script."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

import review_node
from roadmap_chunk_utils import write_json_chunk
from tests.helpers import REPO, SCHEMAS


@pytest.fixture()
def tiny_repo(tmp_path: Path) -> Path:
    shutil.copytree(SCHEMAS, tmp_path / "schemas")
    shutil.copytree(REPO / "constraints", tmp_path / "constraints")
    (tmp_path / "roadmap" / "phases").mkdir(parents=True)
    (tmp_path / "shared").mkdir(parents=True)
    (tmp_path / "shared" / "README.md").write_text("# S\n", encoding="utf-8")
    (tmp_path / "roadmap" / "registry.yaml").write_text(
        "version: 1\nentries: []\n",
        encoding="utf-8",
    )
    (tmp_path / "roadmap" / "manifest.json").write_text(
        json.dumps({"version": 1, "includes": ["phases/T.json"]}) + "\n",
        encoding="utf-8",
    )
    nodes = [
        {
            "id": "M99",
            "parent_id": None,
            "type": "phase",
            "title": "P",
            "codename": None,
            "execution_milestone": "Human-led",
            "status": "Complete",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
        },
        {
            "id": "M99.1",
            "parent_id": "M99",
            "type": "task",
            "title": "One",
            "codename": "one",
            "execution_milestone": "Agentic-led",
            "execution_subtask": "agentic",
            "agentic_checklist": {
                "artifact_action": "a",
                "contract_citation": "shared/README.md",
                "interface_contract": "i",
                "constraints_note": "c",
                "dependency_note": "d",
            },
            "status": "Not Started",
            "touch_zones": [],
            "dependencies": [],
            "parallel_tracks": 1,
        },
    ]
    write_json_chunk(tmp_path / "roadmap" / "phases" / "T.json", nodes)
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
    assert "Current feature sheet" in captured[0]
    assert "Expected shape" in captured[0]


def test_normalize_review_strips_markdown_fence() -> None:
    raw = "```markdown\n## Intent\n\nx\n```"
    assert review_node._normalize_review_markdown_output(raw) == "## Intent\n\nx"


def test_run_review_planning_body_override(
    tiny_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECY_ROAD_OPENAI_API_KEY", "test-key")
    captured: list[str] = []

    def fake_complete(_client: object, user_content: str) -> str:
        captured.append(user_content)
        return "## OK\n"

    monkeypatch.setattr(review_node, "_make_client", lambda: object())
    monkeypatch.setattr(review_node, "_complete", fake_complete)
    review_node.run_review("M99.1", tiny_repo, planning_body="EDITOR_ONLY")
    assert "EDITOR_ONLY" in captured[0]


def test_run_review_returns_markdown(tiny_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(review_node, "_make_client", lambda: object())
    monkeypatch.setattr(review_node, "_complete", lambda _c, _u: "## OK\n")
    out = review_node.run_review("M99.1", tiny_repo)
    assert out.startswith("## OK")
