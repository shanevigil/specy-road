from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

import pytest

from tests.review_repo_helpers import advance_dev, git, make_review_repo

import specy_road
from specy_road.git_subprocess import git_ok, is_worktree_root, merge_conflicts, run


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


def test_run_inherits_the_environment_unless_given_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in (("COUNT", "1"), ("KEY_0", "specy.probe"), ("VALUE_0", "inherited")):
        monkeypatch.setenv(f"GIT_CONFIG_{name}", value)

    assert run(["config", "--get", "specy.probe"], tmp_path).text == "inherited"
    given = {**os.environ, "GIT_CONFIG_VALUE_0": "given"}
    assert run(["config", "--get", "specy.probe"], tmp_path, env=given).text == "given"


def test_merge_conflicts_is_in_memory_and_names_conflicted_paths(tmp_path: Path) -> None:
    repo = make_review_repo(tmp_path)
    assert merge_conflicts(repo, "feature/rm-thing", "dev") == []
    advance_dev(repo, "src/a.py", "print('dev')\n")
    assert merge_conflicts(repo, "feature/rm-thing", "dev") == ["src/a.py"]
    assert merge_conflicts(repo, "feature/rm-thing", "no-such-ref") is None
    assert merge_conflicts(tmp_path, "feature/rm-thing", "dev") is None   # not a repository
    assert git(repo, "status", "--porcelain") == ""   # no checkout, index or working-tree change


_ROOT_AND_BRANCH_FLAGS = {"--show-toplevel", "--show-current"}


def _asks_git_for_root_or_branch(source: str) -> bool:
    """A string constant that is exactly one of the flags: an argument to git, not prose."""
    return any(isinstance(n, ast.Constant) and n.value in _ROOT_AND_BRANCH_FLAGS
               for n in ast.walk(ast.parse(source)))


def test_only_git_subprocess_asks_git_for_the_root_or_the_branch() -> None:
    """Every other module calls git_root, current_branch_name or is_worktree_root instead."""
    assert _asks_git_for_root_or_branch('git_text(["branch", "--show-current"], here)')
    assert not _asks_git_for_root_or_branch('PROMPT = "cd \\"$(git rev-parse --show-toplevel)\\""')
    package = Path(specy_road.__file__).parent
    offenders = [p.relative_to(package).as_posix() for p in sorted(package.rglob("*.py"))
                 if p != package / "git_subprocess.py"
                 and _asks_git_for_root_or_branch(p.read_text(encoding="utf-8"))]
    assert offenders == []


@pytest.mark.parametrize("where, branch, expected", [
    ("top", None, True),
    ("top", "main", True),
    ("top", "other", False),
    ("subdir", None, False),
    ("outside", None, False),
])
def test_is_worktree_root(tmp_path: Path, where: str, branch: str | None, expected: bool) -> None:
    """Only a worktree's top counts, and only with the named branch checked out when one is given."""
    repo = tmp_path / "repo"
    (repo / "subdir").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    _git(repo, "init", "-q", "-b", "main")
    path = {"top": repo, "subdir": repo / "subdir", "outside": tmp_path / "outside"}[where]

    assert is_worktree_root(path, branch) is expected
