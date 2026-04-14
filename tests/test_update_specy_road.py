"""Tests for specy-road update (scripts/update_specy_road.py)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import update_specy_road as usr

REPO = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "git@github.com:shanevigil/specy-road.git",
            "shanevigil/specy-road",
        ),
        (
            "https://github.com/shanevigil/specy-road.git",
            "shanevigil/specy-road",
        ),
        (
            "https://github.com/shanevigil/specy-road",
            "shanevigil/specy-road",
        ),
        (
            "git@github.com:other/other.git",
            "other/other",
        ),
    ],
)
def test_normalize_github_repo_path(url: str, expected: str) -> None:
    assert usr.normalize_github_repo_path(url) == expected.lower()


def test_normalize_github_repo_path_invalid() -> None:
    assert usr.normalize_github_repo_path("not-a-url") is None


@pytest.mark.parametrize(
    "url",
    [
        "git@github.com:shanevigil/specy-road.git",
        "https://github.com/shanevigil/specy-road",
    ],
)
def test_is_canonical_specy_road_remote_accepts(url: str) -> None:
    assert usr.is_canonical_specy_road_remote(url) is True


def test_is_canonical_specy_road_remote_rejects_fork() -> None:
    fork = "git@github.com:other/specy-road.git"
    assert usr.is_canonical_specy_road_remote(fork) is False


def test_specy_road_update_help() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "update", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    out = r.stdout + r.stderr
    assert "--path" in out
    assert "--dry-run" in out
    assert "--allow-dirty" in out
    assert "--install-gui-stack" in out


def test_update_dry_run_tmp_repo(tmp_path: Path) -> None:
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "t@e.st"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "t"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
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
    subprocess.run(
        ["git", "branch", "-M", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "remote",
            "add",
            "origin",
            "https://github.com/shanevigil/specy-road.git",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "update",
            "--path",
            str(tmp_path),
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Would run:" in r.stdout
    assert "git fetch" in r.stdout
    assert "git checkout" in r.stdout
    assert "merge --ff-only" in r.stdout
