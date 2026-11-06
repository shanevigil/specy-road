"""M21.39: the pickup hint marker and the brainstorm lock refuse any symlink on the path.

Each row links one component and checks the refusal names it, and that the
link and its target (bytes, or absence) are unchanged. Publish's rows are in
``tests/test_pm_publish.py``, finish's reviews-base rows in
``tests/test_finish_config_preflight.py``, and ``resolve_deterministic_paths``
called directly is the ``finish`` writer of ``tests/test_writers_refuse_links_out.py``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.on_complete_pickup import print_orchestration_hint
from tests.helpers import DOGFOOD, REPO, script_subprocess_env
THEIRS = b"someone else's file\n"


def _tree(path: Path) -> object:
    """What is at ``path``, never through a link: absent, a link target, bytes, or a directory's listing."""
    if not os.path.lexists(path):
        return None
    if path.is_symlink():
        return ("link", os.readlink(path))
    if path.is_dir():
        return {p.relative_to(path).as_posix(): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}
    return path.read_bytes()


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
    outside_before = _tree(outside)

    print_orchestration_hint(root)   # returns: pickup goes on and exits 0

    out = capsys.readouterr()
    assert "grind-session" in out.out   # a link is never read as "already shown"
    assert out.err.splitlines() == [f"warning: pickup hint marker not recorded: {_refusal(link, expected)}"]
    assert _tree(outside) == outside_before
    assert link.is_symlink()


def test_brainstorm_add_idea_refuses_a_linked_lock(tmp_path: Path) -> None:
    """``session_lock`` re-raises the refusal as a BrainstormError: an error line, exit 1, no traceback."""
    repo = tmp_path / "repo"
    shutil.copytree(DOGFOOD, repo)

    def brainstorm(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-m", "specy_road.cli", "brainstorm", *args, "--repo-root", str(repo)],
                              cwd=REPO, capture_output=True, text=True, env=script_subprocess_env())

    assert brainstorm("start", "--topic", "How do we expand payments?").returncode == 0
    theirs = tmp_path / "theirs.lock"
    theirs.write_bytes(THEIRS)
    lock = repo / ".specyrd" / "cache" / "brainstorm.lock"
    lock.unlink(missing_ok=True)
    lock.symlink_to(theirs)

    result = brainstorm("add-idea", "--title", "One")

    assert result.returncode == 1, result.stdout + result.stderr
    assert _refusal(lock, "a regular file") in result.stderr
    assert "Traceback" not in result.stderr
    assert theirs.read_bytes() == THEIRS
    assert lock.is_symlink()
