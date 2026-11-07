"""M21.39: Publish, finish's land and reviews copy, the pickup hint, the brainstorm lock and the
history cache refuse any symlink on the path.

One test per entry point. Each row links one component and checks the refusal
names it, and that the link and its target (bytes, or absence) are unchanged.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from specy_road.finish_land_deterministic import DeterministicResolveError, resolve_deterministic_paths
from specy_road.on_complete_pickup import print_orchestration_hint
from tests.helpers import DOGFOOD, REPO, script_subprocess_env
from tests.review_repo_helpers import commit_file, git
from tests.test_finish_merge_mode import merge_mode_finish_repo

THEIRS = b"someone else's file\n"
SUMMARY = "work/implementation-summary-M1.1.md"
GIT_ID = ["-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]


def _snapshot(d: Path) -> dict[str, bytes | None]:
    """Every path under the existing directory ``d``: a file's bytes, ``None`` for a directory."""
    return {p.relative_to(d).as_posix(): p.read_bytes() if p.is_file() else None for p in sorted(d.rglob("*"))}


def _git_state(repo: Path) -> tuple[str, str, str]:
    """HEAD, the index, and the worktree status (ignored files included)."""
    return (git(repo, "rev-parse", "HEAD"), git(repo, "ls-files", "-s"),
            git(repo, "status", "--porcelain", "-uall", "--ignored"))


def _committed_dogfood(root: Path) -> Path:
    shutil.copytree(DOGFOOD, root, ignore=shutil.ignore_patterns(".specyrd"))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", *GIT_ID, "commit", "-qm", "init"], cwd=root, check=True)
    return root


def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(root)],
                          cwd=REPO, capture_output=True, text=True, env=script_subprocess_env())


def _refusal(link: Path, expected: str) -> str:
    return f"{link} is a symlink (to {os.readlink(link)}), not {expected}"


def _cache_out(root: Path, outside: Path) -> Path:
    (root / ".specyrd").mkdir()
    link = root / ".specyrd" / "cache"
    link.symlink_to(outside, target_is_directory=True)
    return link


def _specyrd_out(root: Path, outside: Path) -> Path:
    link = root / ".specyrd"
    link.symlink_to(outside, target_is_directory=True)
    return link


def _marker(target: str):
    def arrange(root: Path, outside: Path) -> Path:
        (root / ".specyrd" / "cache").mkdir(parents=True)
        if target == "file":
            (outside / "theirs.md").write_bytes(THEIRS)
        link = root / ".specyrd" / "cache" / "pickup-orchestration-hint"
        link.symlink_to(outside / ("theirs.md" if target == "file" else "made.md"))
        return link
    return arrange


@pytest.mark.parametrize(
    ("arrange", "expected"),
    [(_cache_out, "a directory"), (_specyrd_out, "a directory"),
     (_marker("dangling"), "a regular file"), (_marker("file"), "a regular file")],
    ids=["cache-linked-out", "specyrd-linked", "marker-dangling", "marker-to-outside-file"],
)
def test_pickup_hint_refuses_a_linked_marker_path(tmp_path: Path, monkeypatch, capsys, arrange, expected: str) -> None:
    """Best effort: one warning line, the hint still shown, nothing written through the link."""
    monkeypatch.delenv("SPECY_ROAD_GRIND_SESSION", raising=False)
    root, outside = tmp_path / "repo", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = arrange(root, outside)
    outside_before = _snapshot(outside)

    print_orchestration_hint(root)   # returns: pickup goes on and exits 0

    out = capsys.readouterr()
    assert "grind-session" in out.out   # a link is never read as "already shown"
    assert out.err.splitlines() == [f"warning: pickup hint marker not recorded: {_refusal(link, expected)}"]
    assert _snapshot(outside) == outside_before
    assert link.is_symlink()


def test_brainstorm_add_idea_refuses_a_linked_lock(tmp_path: Path) -> None:
    """``session_lock`` re-raises the refusal as a BrainstormError: an error line, exit 1, no traceback."""
    repo = tmp_path / "repo"
    shutil.copytree(DOGFOOD, repo)

    assert _cli(repo, "brainstorm", "start", "--topic", "How do we expand payments?").returncode == 0
    theirs = tmp_path / "theirs.lock"
    theirs.write_bytes(THEIRS)
    lock = repo / ".specyrd" / "cache" / "brainstorm.lock"
    lock.unlink(missing_ok=True)
    lock.symlink_to(theirs)

    result = _cli(repo, "brainstorm", "add-idea", "--title", "One")

    assert result.returncode == 1, result.stdout + result.stderr
    assert _refusal(lock, "a regular file") in result.stderr
    assert "Traceback" not in result.stderr
    assert theirs.read_bytes() == THEIRS
    assert lock.is_symlink()


def _history_file(root: Path, outside: Path) -> Path:
    (root / ".specyrd" / "cache").mkdir(parents=True)
    (outside / "theirs.json").write_bytes(THEIRS)
    link = root / ".specyrd" / "cache" / "roadmap-history.json"
    link.symlink_to(outside / "theirs.json")
    return link


def _ignore_dangling(root: Path, outside: Path) -> Path:
    (root / ".specyrd" / "cache").mkdir(parents=True)
    link = root / ".specyrd" / "cache" / ".gitignore"
    link.symlink_to(outside / "made")
    return link


@pytest.mark.parametrize(
    ("arrange", "expected"),
    [(_cache_out, "a directory"), (_ignore_dangling, "a regular file"), (_history_file, "a regular file")],
    ids=["cache-linked-out", "gitignore-dangling", "history-to-outside-file"],
)
def test_digest_carries_on_past_a_linked_history_cache(tmp_path: Path, arrange, expected: str) -> None:
    """A6: the cache is optional; one warning naming the path, exit 0, nothing written through the link."""
    root, outside = _committed_dogfood(tmp_path / "repo"), tmp_path / "outside"
    outside.mkdir()
    link = arrange(root, outside)
    outside_before = _snapshot(outside)

    result = _cli(root, "digest")

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr.splitlines() == [f"warning: history cache not written: {_refusal(link, expected)}"]
    assert _snapshot(outside) == outside_before
    assert link.is_symlink()


@pytest.mark.parametrize(
    ("name", "target"), [("roadmap.md", "payload.md"), ("roadmap-context.md", "../outside.md")],
    ids=["roadmap-in-repo", "context-dangling"],
)
def test_publish_refuses_a_linked_generated_file(tmp_path: Path, monkeypatch, name: str, target: str) -> None:
    """GUI Publish: HTTP 400 with finish's sentence; HEAD, index and the in-repo target bytes unchanged."""
    from specy_road.gui_app import create_app

    repo = _committed_dogfood(tmp_path / "dogfood")
    bare = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "push", "-q", "-u", "origin", "HEAD")
    link = repo / name
    link.unlink()
    link.symlink_to(target)
    if target == "payload.md":   # committed, so Publish's scope check passes and the link is what refuses
        (repo / "payload.md").write_bytes(THEIRS)
        git(repo, "add", "payload.md", name)
        git(repo, *GIT_ID, "commit", "-qm", f"{name} links to payload.md")
    chunk = repo / "roadmap" / "phases" / "M0.json"
    chunk.write_text(chunk.read_text(encoding="utf-8").replace("Foundation", "Foundation renamed", 1), encoding="utf-8")
    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(repo))
    before, outside_before = _git_state(repo), _snapshot(tmp_path)

    client = TestClient(create_app())
    fp = client.get("/api/roadmap/fingerprint").json()["fingerprint"]
    r = client.post("/api/publish", headers={"X-PM-Gui-Fingerprint": str(fp)}, json={"message": "roadmap: publish"})

    assert r.status_code == 400, r.text
    assert f"{name} is a symlink (to {target}), not a regular file" in r.json()["detail"]
    assert (_git_state(repo), _snapshot(tmp_path)) == (before, outside_before)
    assert link.is_symlink()


@pytest.mark.parametrize("target", ["payload.md", "../outside.md"], ids=["link-in", "link-out"])
def test_resolve_deterministic_paths_refuses_a_linked_roadmap_md(tmp_path: Path, target: str) -> None:
    """Called directly, skipping finish's preflight: refused before either generated file is written."""
    root = tmp_path / "repo"
    shutil.copytree(DOGFOOD, root, ignore=shutil.ignore_patterns(".specyrd"))
    (tmp_path / "outside.md").write_bytes(THEIRS)
    (root / "payload.md").write_bytes(THEIRS)
    link = root / "roadmap.md"
    link.unlink()
    link.symlink_to(target)
    before = _snapshot(tmp_path)

    with pytest.raises(DeterministicResolveError, match="roadmap.md is a symlink"):
        resolve_deterministic_paths(root, codename=None)

    assert _snapshot(tmp_path) == before
    assert os.readlink(link) == target


@pytest.mark.parametrize(
    ("linked", "from_worktree"),
    [("work/reviews", False), ("work/reviews", True), ("work/reviews/M1.1", False), ("work", False), ("work", True)],
    ids=["reviews-main", "reviews-from-worktree", "node", "work-main", "work-from-worktree"],
)
def test_finish_refuses_a_linked_reviews_base(tmp_path: Path, monkeypatch, linked: str, from_worktree: bool) -> None:
    """The untracked summary's copy is walked from the main checkout's project root: exit 1, nothing changed."""
    main, _bare = merge_mode_finish_repo(tmp_path, monkeypatch)
    commit_file(main, "work/brief-M1.1.md", "# brief M1.1\n", "brief")
    repo = main
    if from_worktree:
        git(main, "checkout", "-q", "dev")
        repo = tmp_path / "lane"
        git(main, "worktree", "add", "-q", str(repo), "feature/rm-thing")
    (repo / SUMMARY).write_text("# summary M1.1, never committed\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "theirs.md").write_bytes(THEIRS)
    link = main / linked
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_dir():   # main's own work/ (the committed brief): its contents move to the link's target
        shutil.copytree(link, outside, dirs_exist_ok=True)
        shutil.rmtree(link)
    link.symlink_to(outside, target_is_directory=True)
    before = (_git_state(repo), _git_state(main), _snapshot(outside), (repo / SUMMARY).read_bytes())

    result = subprocess.run([sys.executable, "-m", "specy_road.cli", "finish-this-task", "--repo-root", str(repo)],
                            cwd=repo, capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(REPO)})

    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{link} is a symlink (to {outside}), not a directory" in result.stderr, result.stderr
    assert "finish-this-task: nothing was changed" in result.stderr
    assert "Traceback" not in result.stderr
    assert (_git_state(repo), _git_state(main), _snapshot(outside), (repo / SUMMARY).read_bytes()) == before
    assert link.is_symlink()
