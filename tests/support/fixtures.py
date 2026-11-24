"""Pytest fixtures shared by the whole suite; ``tests/conftest.py`` registers them.

A test file that defines a fixture of the same name keeps its own: pytest prefers the closer one.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests.helpers import DOGFOOD
from tests.support.same.git_84c8ad8f55f9 import git


@pytest.fixture()
def dogfood_copy(tmp_path: Path) -> Path:
    """A private copy of the dogfood fixture, which a test may change freely."""
    dest = tmp_path / "dogfood"
    shutil.copytree(DOGFOOD, dest)
    return dest


@pytest.fixture()
def api_client(dogfood_copy: Path, monkeypatch: pytest.MonkeyPatch):
    """A PM GUI test client serving :func:`dogfood_copy`."""
    from starlette.testclient import TestClient

    from specy_road.gui_app import create_app

    monkeypatch.setenv("SPECY_ROAD_REPO_ROOT", str(dogfood_copy))
    return TestClient(create_app())


@pytest.fixture(scope="session")
def git_template(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """A repo on ``dev`` with one commit and its bare ``origin``, built once per session.

    Only :func:`git_remote_repo` copies it; a test that changed it would change every later one.
    """
    base = tmp_path_factory.mktemp("git-template")
    repo, bare = base / "repo", base / "remote.git"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "dev")
    git(repo, "config", "user.email", "t@e.com")
    git(repo, "config", "user.name", "T")
    (repo / "README.md").write_text("# template\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-qm", "initial")
    git(base, "clone", "-q", "--bare", str(repo), str(bare))
    git(repo, "remote", "add", "origin", str(bare))
    git(repo, "fetch", "-q", "origin")
    git(repo, "branch", "-q", "--set-upstream-to", "origin/dev")
    return repo, bare


@pytest.fixture()
def git_remote_repo(git_template: tuple[Path, Path], tmp_path: Path) -> tuple[Path, Path]:
    """This test's own copy of :func:`git_template` as ``(repo, bare)``, origin the copied bare."""
    src_repo, src_bare = git_template
    repo = shutil.copytree(src_repo, tmp_path / "repo", symlinks=True)
    bare = shutil.copytree(src_bare, tmp_path / "remote.git", symlinks=True)
    git(repo, "remote", "set-url", "origin", str(bare))
    return repo, bare


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """A private copy of the dogfood fixture, at ``tmp_path / "repo"``.

    Twenty-two test modules defined this same fixture. A module that still defines
    ``repo`` keeps its own; pytest uses the closer one.
    """
    dest = tmp_path / "repo"
    shutil.copytree(DOGFOOD, dest)
    return dest
