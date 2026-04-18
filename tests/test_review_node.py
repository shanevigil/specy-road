"""Tests for advisory review_node script."""

from __future__ import annotations

import json
import shutil
import subprocess
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
    (tmp_path / "shared" / "nested").mkdir(parents=True)
    (tmp_path / "shared" / "nested" / "note.md").write_text(
        "## Deep title\n\nbody\n",
        encoding="utf-8",
    )
    (tmp_path / "shared" / "asset.bin").write_bytes(b"\x00\x01\xff")
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
    msg = captured[0]
    assert "Brief" in msg
    assert "## shared/ index (possible references)" in msg
    assert msg.index("## Brief") < msg.index("## shared/ index (possible references)")
    assert msg.index("## shared/ index (possible references)") < msg.index(
        "## constraints/README.md",
    )
    assert "`shared/README.md`" in msg
    assert "`shared/asset.bin`" in msg
    assert "`shared/nested/note.md`" in msg
    assert "Deep title" in msg
    assert msg.index("`shared/README.md`") < msg.index("`shared/asset.bin`")
    assert msg.index("`shared/asset.bin`") < msg.index("`shared/nested/note.md`")
    assert "constraints/README.md" in msg
    assert "shared/README.md" in msg
    assert "Current feature sheet" in msg
    assert "Expected shape" in msg
    assert "scaffold-planning" in msg
    assert "deterministic index" in review_node.SYSTEM_PROMPT


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


def test_shared_catalog_sorts_lexicographically(
    tiny_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Paths are sorted by string, not filesystem creation order."""
    (tiny_repo / "shared" / "b.md").write_text("# B\n", encoding="utf-8")
    (tiny_repo / "shared" / "a.md").write_text("# A\n", encoding="utf-8")
    monkeypatch.setenv("SPECY_ROAD_OPENAI_API_KEY", "test-key")
    captured: list[str] = []

    def fake_complete(_client: object, user_content: str) -> str:
        captured.append(user_content)
        return "## OK\n"

    monkeypatch.setattr(review_node, "_make_client", lambda: object())
    monkeypatch.setattr(review_node, "_complete", fake_complete)
    review_node.run_review("M99.1", tiny_repo)
    msg = captured[0]
    assert msg.index("`shared/a.md`") < msg.index("`shared/b.md`")


def test_shared_catalog_max_files_footer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_node, "_SHARED_CATALOG_MAX_FILES", 2)
    (tmp_path / "shared").mkdir()
    for i in range(4):
        (tmp_path / "shared" / f"z{i}.md").write_text("# t\n", encoding="utf-8")
    out = review_node._shared_catalog(tmp_path)
    assert "`shared/z0.md`" in out
    assert "`shared/z1.md`" in out
    assert "`shared/z2.md`" not in out
    assert "2 more path(s)" in out


def test_shared_catalog_no_shared_directory(tmp_path: Path) -> None:
    out = review_node._shared_catalog(tmp_path)
    assert "not present" in out


def test_shared_catalog_empty_directory(tmp_path: Path) -> None:
    (tmp_path / "shared").mkdir()
    out = review_node._shared_catalog(tmp_path)
    assert "empty" in out.lower()


def test_shared_catalog_memoizes_when_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_node._shared_catalog_cache_clear()
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "x.md").write_text("# X\n", encoding="utf-8")
    calls = {"n": 0}
    real_build = review_node._shared_catalog_build

    def counting_build(r: Path) -> str:
        calls["n"] += 1
        return real_build(r)

    monkeypatch.setattr(review_node, "_shared_catalog_build", counting_build)
    assert review_node._shared_catalog(tmp_path) == review_node._shared_catalog(tmp_path)
    assert calls["n"] == 1


def test_shared_catalog_cache_invalidates_after_file_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_node._shared_catalog_cache_clear()
    (tmp_path / "shared").mkdir()
    p = tmp_path / "shared" / "x.md"
    p.write_text("# X\n", encoding="utf-8")
    calls = {"n": 0}
    real_build = review_node._shared_catalog_build

    def counting_build(r: Path) -> str:
        calls["n"] += 1
        return real_build(r)

    monkeypatch.setattr(review_node, "_shared_catalog_build", counting_build)
    review_node._shared_catalog(tmp_path)
    p.write_text("# Y\n", encoding="utf-8")
    review_node._shared_catalog(tmp_path)
    assert calls["n"] == 2


def test_shared_catalog_memoizes_with_git_head_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    review_node._shared_catalog_cache_clear()
    (tmp_path / "shared").mkdir()
    (tmp_path / "shared" / "a.md").write_text("# Git doc\n", encoding="utf-8")
    subprocess.run(
        ["git", "init", "-b", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "test"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "add", "shared/a.md"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    calls = {"n": 0}
    real_build = review_node._shared_catalog_build

    def counting_build(r: Path) -> str:
        calls["n"] += 1
        return real_build(r)

    monkeypatch.setattr(review_node, "_shared_catalog_build", counting_build)
    assert review_node._shared_catalog(tmp_path) == review_node._shared_catalog(tmp_path)
    assert calls["n"] == 1
    key = review_node._shared_catalog_cache_key(tmp_path.resolve())
    assert "\0git:" in key
