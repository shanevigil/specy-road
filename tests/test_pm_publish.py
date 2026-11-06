from __future__ import annotations

import os
import subprocess
import shutil
import sys
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

from tests.helpers import DOGFOOD


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


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout


def _add_bare_remote(repo: Path) -> Path:
    bare = repo.parent / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
    _git(repo, "remote", "add", "origin", str(bare))
    _git(repo, "push", "-u", "origin", "HEAD")
    return bare


def _state(repo: Path) -> tuple[str, str, bytes | None, bytes | None]:
    """HEAD, the index, and both generated files' bytes (``None`` when absent)."""

    def _bytes(name: str) -> bytes | None:
        p = repo / name
        return p.read_bytes() if p.is_file() else None

    return (
        _git_out(repo, "rev-parse", "HEAD"),
        _git_out(repo, "ls-files", "--stage"),
        _bytes("roadmap.md"),
        _bytes("roadmap-context.md"),
    )


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
    _add_bare_remote(tmp_git_repo)
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
    _add_bare_remote(tmp_git_repo)

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


@pytest.mark.parametrize("remote", ["none", "push_remote_gone"])
def test_publish_roadmap_refuses_without_remote(
    tmp_git_repo: Path, remote: str
) -> None:
    (tmp_git_repo / "roadmap").mkdir()
    (tmp_git_repo / "roadmap" / "manifest.json").write_text("{}\n", encoding="utf-8")
    _git(tmp_git_repo, "add", "roadmap/manifest.json")
    _git(tmp_git_repo, "commit", "-m", "r")
    if remote == "push_remote_gone":
        _add_bare_remote(tmp_git_repo)
        _git(tmp_git_repo, "config", "remote.pushDefault", "gone")

    (tmp_git_repo / "roadmap" / "chunk.json").write_text("[]\n", encoding="utf-8")
    (tmp_git_repo / "roadmap-context.md").write_text("# ctx\n", encoding="utf-8")
    _git(tmp_git_repo, "add", "roadmap-context.md")
    before = _state(tmp_git_repo)
    st = classify_publish_status(tmp_git_repo)
    assert st.blocked is True
    assert st.blocked_reason == "no_remote"
    assert st.detail and "git remote add" in st.detail
    with pytest.raises(ValueError, match="No git remote is configured"):
        publish_roadmap(tmp_git_repo, "roadmap: test publish")
    assert _state(tmp_git_repo) == before


def test_publish_status_dict_api(tmp_git_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(tmp_git_repo))
    from specy_road.gui_app import create_app

    _add_bare_remote(tmp_git_repo)
    client = TestClient(create_app())
    r = client.get("/api/publish/status")
    assert r.status_code == 200
    j = r.json()
    assert "can_publish" in j
    assert "scope_dirty" in j
    assert j["blocked"] is False


def test_api_publish_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dogfood = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dogfood)
    subprocess.run(
        ["git", "init"],
        cwd=dogfood,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "pytest@example.com"],
        cwd=dogfood,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "pytest"],
        cwd=dogfood,
        check=True,
        capture_output=True,
    )
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood))
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    r0 = client.get("/api/roadmap")
    assert r0.status_code == 200
    fp = r0.json()["fingerprint"]
    r = client.post(
        "/api/publish",
        headers={
            "X-PM-Gui-Fingerprint": str(fp),
            "Content-Type": "application/json",
        },
        json={"message": "roadmap: x"},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert isinstance(detail, str)
    assert len(detail) > 0


def test_publish_pathspecs_cover_manifest() -> None:
    assert "roadmap/" in PUBLISH_PATHSPECS


@pytest.fixture()
def dogfood_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The dogfood fixture committed in a git repo with a bare remote, served by the GUI."""
    repo = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, repo)
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    _add_bare_remote(repo)
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(repo))
    return repo


def _post_publish(repo: Path, message: str = "roadmap: publish"):
    from specy_road.gui_app import create_app

    client = TestClient(create_app())
    fp = client.get("/api/roadmap/fingerprint").json()["fingerprint"]
    return client.post(
        "/api/publish",
        headers={"X-PM-Gui-Fingerprint": str(fp)},
        json={"message": message},
    )


def _edit_m0(repo: Path, old: str, new: str) -> None:
    chunk = repo / "roadmap" / "phases" / "M0.json"
    text = chunk.read_text(encoding="utf-8")
    assert old in text
    chunk.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_publish_regenerates_generated_files_and_pushes(dogfood_repo: Path) -> None:
    _edit_m0(dogfood_repo, '"title": "Foundation — architecture and contracts"',
             '"title": "Foundation — renamed for publish"')
    r = _post_publish(dogfood_repo)
    assert r.status_code == 200, r.text
    assert set(r.json()) == {"ok", "commit_sha", "pushed", "branch"}
    clone = dogfood_repo.parent / "clone"
    subprocess.run(
        ["git", "clone", str(dogfood_repo.parent / "remote.git"), str(clone)],
        check=True, capture_output=True,
    )
    assert "renamed for publish" in (clone / "roadmap.md").read_text(encoding="utf-8")
    for command in ("export", "digest"):
        done = subprocess.run(
            [sys.executable, "-m", "specy_road.cli", command, "--check",
             "--repo-root", str(clone)],
            capture_output=True, text=True, check=False,
        )
        assert done.returncode == 0, (command, done.stdout, done.stderr)


def _break_not_json(repo: Path) -> None:
    (repo / "roadmap" / "phases" / "M1.json").write_text("{ not json", encoding="utf-8")


def _break_missing_chunk(repo: Path) -> None:
    (repo / "roadmap" / "phases" / "M1.json").unlink()


def _break_unknown_dependency(repo: Path) -> None:
    _edit_m0(repo, '"dependencies": [],\n      "execution_milestone": "Mixed"',
             '"dependencies": ["M9.99"],\n      "execution_milestone": "Mixed"')


@pytest.mark.parametrize(
    ("breaker", "cause"),
    [
        (_break_not_json, "M1.json"),
        (_break_missing_chunk, "M1.json"),
        (_break_unknown_dependency, "M9.99"),
    ],
)
def test_publish_refuses_invalid_graph(dogfood_repo: Path, breaker, cause: str) -> None:
    breaker(dogfood_repo)
    before = _state(dogfood_repo)
    r = _post_publish(dogfood_repo)
    assert r.status_code == 400, r.text
    assert cause in r.json()["detail"]
    assert _state(dogfood_repo) == before


@pytest.mark.parametrize(
    ("name", "layout"),
    [("roadmap-context.md", "dangling_out"), ("roadmap-context.md", "link_out"), ("roadmap.md", "link_in")],
)
def test_publish_refuses_a_linked_generated_file(dogfood_repo: Path, name: str, layout: str) -> None:
    """M21.17 link out; M21.39: any link (in-repo, dangling) is refused with finish's sentence, nothing written."""
    link = dogfood_repo / name
    target = dogfood_repo / "payload.md" if layout == "link_in" else dogfood_repo.parent / "outside.md"
    if layout != "dangling_out":
        target.write_text("someone else's file\n", encoding="utf-8")
    link.unlink()
    link.symlink_to("payload.md" if layout == "link_in" else target)
    if layout == "link_in":   # committed, so Publish's scope check passes and the link is what refuses
        _git(dogfood_repo, "add", "payload.md", name)
        _git(dogfood_repo, "commit", "-m", f"{name} links to payload.md")
    _edit_m0(dogfood_repo, '"title": "Foundation — architecture and contracts"',
             '"title": "Foundation — renamed for publish"')
    before = _state(dogfood_repo)
    r = _post_publish(dogfood_repo)
    assert r.status_code == 400, r.text
    assert f"{name} is a symlink (to {os.readlink(link)}), not a regular file" in r.json()["detail"]
    assert _state(dogfood_repo) == before   # HEAD, index and both files' bytes
    assert link.is_symlink()
    if layout == "dangling_out":
        assert not target.exists()
    else:
        assert target.read_bytes() == b"someone else's file\n"
