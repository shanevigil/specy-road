from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from specy_road.git_subprocess import git_ok


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_git_ok_returns_stdout_for_success(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    (repo / "f.txt").write_text("ok\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-m", "init")

    ok, out = git_ok(["rev-parse", "--abbrev-ref", "HEAD"], repo, 10.0)

    assert ok is True
    assert out == "main"


def test_git_ok_returns_false_and_stderr_on_failure(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")

    ok, out = git_ok(["show", "not-a-real-ref"], repo, 10.0)

    assert ok is False
    assert "not-a-real-ref" in out


def test_git_ok_returns_false_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["git", "status"], timeout=0.01)

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    ok, out = git_ok(["status"], Path("."), 0.01)
    assert ok is False
    assert out == ""


def test_git_ok_returns_false_on_oserror(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_oserror(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError("git missing")

    monkeypatch.setattr(subprocess, "run", _raise_oserror)
    ok, out = git_ok(["status"], Path("."), 0.01)
    assert ok is False
    assert out == ""
