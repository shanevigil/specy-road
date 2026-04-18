"""Unit tests for scripts/check_release_version.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check_release_version.py"


def _run(tag: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), tag],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_pyproject(tmp_path: Path, version: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f"""[project]
name = "specy-road"
version = "{version}"
""",
        encoding="utf-8",
    )


def test_matches_plain_version(tmp_path: Path) -> None:
    _seed_pyproject(tmp_path, "0.1.0")
    r = _run("v0.1.0", tmp_path)
    assert r.returncode == 0, r.stderr
    assert "matches tag" in r.stdout


def test_matches_prerelease_with_pep440_normalization(tmp_path: Path) -> None:
    """Tags use 'v0.1.0-rc1' (Git-friendly); pyproject uses '0.1.0rc1' (PEP 440)."""
    _seed_pyproject(tmp_path, "0.1.0rc1")
    r = _run("v0.1.0-rc1", tmp_path)
    assert r.returncode == 0, r.stderr


def test_pyproject_with_dash_form_is_rejected(tmp_path: Path) -> None:
    """pyproject must use PEP 440 prerelease form ('0.1.0rc1', no dash)."""
    _seed_pyproject(tmp_path, "0.1.0-rc1")
    r = _run("v0.1.0-rc1", tmp_path)
    assert r.returncode == 1
    assert "does NOT match" in r.stderr


def test_mismatch_returns_nonzero(tmp_path: Path) -> None:
    _seed_pyproject(tmp_path, "0.1.0")
    r = _run("v0.2.0", tmp_path)
    assert r.returncode == 1
    assert "does NOT match" in r.stderr


def test_strips_refs_tags_prefix(tmp_path: Path) -> None:
    _seed_pyproject(tmp_path, "0.1.0")
    r = _run("refs/tags/v0.1.0", tmp_path)
    assert r.returncode == 0, r.stderr


def test_missing_pyproject_errors(tmp_path: Path) -> None:
    r = _run("v0.1.0", tmp_path)
    assert r.returncode != 0
    assert "pyproject.toml not found" in r.stderr


def test_missing_version_errors(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "specy-road"\n', encoding="utf-8"
    )
    r = _run("v0.1.0", tmp_path)
    assert r.returncode != 0
    assert "project.version missing" in r.stderr
