"""Tests for constitution/purpose.md + principles.md scaffolding."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.constitution_scaffold import (
    PURPOSE_REL,
    PRINCIPLES_REL,
    ConstitutionExistsError,
    write_constitution,
)

REPO = Path(__file__).resolve().parent.parent


def test_write_constitution_creates_both(tmp_path: Path) -> None:
    r = write_constitution(tmp_path, force=False)
    assert set(r.written) == {PURPOSE_REL, PRINCIPLES_REL}
    assert r.skipped_existing == ()
    p = tmp_path / PURPOSE_REL
    pr = tmp_path / PRINCIPLES_REL
    assert p.is_file() and pr.is_file()
    assert "# Purpose" in p.read_text(encoding="utf-8")
    assert "# Principles" in pr.read_text(encoding="utf-8")


def test_write_constitution_both_exist_no_force_raises(tmp_path: Path) -> None:
    write_constitution(tmp_path, force=False)
    with pytest.raises(ConstitutionExistsError) as exc:
        write_constitution(tmp_path, force=False)
    assert PURPOSE_REL in exc.value.existing
    assert PRINCIPLES_REL in exc.value.existing


def test_write_constitution_one_missing_writes_other(tmp_path: Path) -> None:
    c = tmp_path / "constitution"
    c.mkdir()
    (c / "purpose.md").write_text("# Purpose\n\nkeep\n", encoding="utf-8")
    r = write_constitution(tmp_path, force=False)
    assert PURPOSE_REL in r.skipped_existing
    assert PRINCIPLES_REL in r.written
    assert "keep" in (tmp_path / PURPOSE_REL).read_text(encoding="utf-8")


def test_write_constitution_force_overwrites(tmp_path: Path) -> None:
    write_constitution(tmp_path, force=False)
    (tmp_path / PURPOSE_REL).write_text("gone", encoding="utf-8")
    r = write_constitution(tmp_path, force=True)
    assert PURPOSE_REL in r.written
    assert "# Purpose" in (tmp_path / PURPOSE_REL).read_text(encoding="utf-8")


def test_specy_road_scaffold_constitution_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "scaffold-constitution",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--force" in r.stdout
    assert "--repo-root" in r.stdout


def test_specy_road_scaffold_constitution_temp_repo(tmp_path: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "scaffold-constitution",
            "--repo-root",
            str(tmp_path),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "wrote" in r.stdout
    assert (tmp_path / PURPOSE_REL).is_file()
