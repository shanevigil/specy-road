from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from specy_road.pm_publish import (
    PUBLISH_PATHSPECS,
    classify_publish_status,
    path_in_publish_scope,
    publish_roadmap,
    publish_status_dict,
)


def test_path_in_publish_scope() -> None:
    assert path_in_publish_scope("roadmap/manifest.json") is True
    assert path_in_publish_scope("planning/foo.md") is True
    assert path_in_publish_scope("constitution/purpose.md") is True
    assert path_in_publish_scope("vision.md") is True
    assert path_in_publish_scope("roadmap.md") is True
    assert path_in_publish_scope("work/notes.md") is False
    assert path_in_publish_scope("shared/x.png") is False
    assert path_in_publish_scope("README.md") is False


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture()
def tmp_git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    # Initial commit so HEAD exists
    (repo / "README.md").write_text("x\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "init")
    return repo


def test_classify_clean_repo(tmp_git_repo: Path) -> None:
    st = classify_publish_status(tmp_git_repo)
    assert st.blocked is False
    assert st.scope_dirty is False
    assert st.can_publish is False


def test_classify_scope_dirty(tmp_git_repo: Path) -> None:
    d = tmp_git_repo / "roadmap"
    d.mkdir()
    (d / "manifest.json").write_text("{}\n", encoding="utf-8")
    _git(tmp_git_repo, "add", "roadmap/manifest.json")
    _git(tmp_git_repo, "commit", "-m", "add roadmap")

    (d / "chunk.json").write_text("[]\n", encoding="utf-8")
    st = classify_publish_status(tmp_git_repo)
    assert st.scope_dirty is True
    assert st.blocked is False
    assert st.can_publish is True
    assert "chunk.json" in "".join(st.scope_paths)


def test_classify_blocked_out_of_scope(tmp_git_repo: Path) -> None:
    (tmp_git_repo / "roadmap").mkdir()
    (tmp_git_repo / "roadmap" / "x.json").write_text("{}\n", encoding="utf-8")
    (tmp_git_repo / "other.txt").write_text("y\n", encoding="utf-8")
    st = classify_publish_status(tmp_git_repo)
    assert st.blocked is True
    assert st.blocked_reason == "out_of_scope_changes"


def test_classify_blocked_staged_out_of_scope(tmp_git_repo: Path) -> None:
    (tmp_git_repo / "roadmap").mkdir()
    (tmp_git_repo / "roadmap" / "x.json").write_text("{}\n", encoding="utf-8")
    (tmp_git_repo / "other.txt").write_text("y\n", encoding="utf-8")
    _git(tmp_git_repo, "add", "other.txt")
    st = classify_publish_status(tmp_git_repo)
    assert st.blocked is True
    assert st.blocked_reason == "staged_out_of_scope"


def test_publish_roadmap_commits_and_push_fails_without_remote(
    tmp_git_repo: Path,
) -> None:
    (tmp_git_repo / "roadmap").mkdir()
    (tmp_git_repo / "roadmap" / "manifest.json").write_text("{}\n", encoding="utf-8")
    _git(tmp_git_repo, "add", "roadmap/manifest.json")
    _git(tmp_git_repo, "commit", "-m", "r")

    (tmp_git_repo / "roadmap" / "chunk.json").write_text("[]\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="upstream|push"):
        publish_roadmap(tmp_git_repo, "roadmap: test publish")
    # Commit runs before push; push fails without remote/upstream.
    # publish_roadmap raises RuntimeError on push failure - commit is NOT reverted
    r = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"],
        cwd=tmp_git_repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.stdout.strip() == "roadmap: test publish"


def test_publish_status_dict_api(tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(tmp_git_repo))
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r = client.get("/api/publish/status")
    assert r.status_code == 200
    j = r.json()
    assert "can_publish" in j
    assert "scope_dirty" in j
    assert j["blocked"] is False


def test_api_publish_validation(tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(tmp_git_repo))
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r = client.post("/api/publish", json={"message": "roadmap: x"})
    assert r.status_code == 400
    assert "No roadmap" in r.json()["detail"] or "publish" in r.json()["detail"].lower()


def test_publish_pathspecs_cover_manifest() -> None:
    assert "roadmap/" in PUBLISH_PATHSPECS
