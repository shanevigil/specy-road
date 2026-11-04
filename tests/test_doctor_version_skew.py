"""Running specy-road older than the project's recorded minimum."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road import __version__
from specy_road.managed_block import HTML_COMMENT, render_block
from specy_road.agents_md_block import AGENTS_MD, render_agents_lines


def _write_manifest(root: Path, version: str) -> None:
    path = root / ".specyrd" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"specyrd_version": version, "project_root": "."}), encoding="utf-8")


def _write_agents_block(root: Path, *, written_by: str | None = None, minimum: str | None = None) -> None:
    lines = render_agents_lines()
    block = render_block(lines, style=HTML_COMMENT)
    if written_by is not None:
        block = block.replace(f"Written by specy-road {__version__}", f"Written by specy-road {written_by}", 1)
    if minimum is not None:
        block = block.replace(f"(minimum {__version__})", f"(minimum {minimum})")
    (root / AGENTS_MD).write_text(f"# Agents\n\n{block}\n", encoding="utf-8")


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *args],
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("recorded", "equals"),
    [("99.0.0", False), ("0.3.1rc99", True)],
    ids=["final-space", "prerelease-equals"],
)
def test_warns_when_the_running_version_is_older_than_the_manifest(
    tmp_path: Path, recorded: str, equals: bool
) -> None:
    _write_manifest(tmp_path, recorded)
    root = [f"--repo-root={tmp_path}"] if equals else ["--repo-root", str(tmp_path)]

    proc = _cli("validate", *root, "--help")

    assert proc.returncode == 0
    assert proc.stderr.count("older install earlier on PATH") == 1
    assert f"specy-road {__version__} is running but this project records {recorded}" in proc.stderr


def test_warns_when_the_minimum_is_newer_than_written_by_and_the_manifest(tmp_path: Path) -> None:
    _write_manifest(tmp_path, "0.0.1")
    _write_agents_block(tmp_path, written_by=__version__, minimum="99.0.0")

    proc = _cli("validate", "--repo-root", str(tmp_path), "--help")

    assert proc.returncode == 0
    assert f"records 99.0.0 ({AGENTS_MD})" in proc.stderr
    assert proc.stderr.count("older install earlier on PATH") == 1


@pytest.mark.parametrize(
    "manifest_bytes",
    [None, b"", b"{", b"\xff"],
    ids=["missing", "empty", "invalid-json", "non-utf8"],
)
def test_unreadable_manifest_still_warns_from_agents_md(
    tmp_path: Path, manifest_bytes: bytes | None
) -> None:
    if manifest_bytes is not None:
        path = tmp_path / ".specyrd" / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(manifest_bytes)
    _write_agents_block(tmp_path, written_by=__version__, minimum="99.0.0")

    proc = _cli("validate", "--repo-root", str(tmp_path), "--help")

    assert proc.returncode == 0
    assert f"records 99.0.0 ({AGENTS_MD})" in proc.stderr
    assert proc.stderr.count("older install earlier on PATH") == 1


def test_unreadable_agents_md_still_warns_from_the_manifest(tmp_path: Path) -> None:
    _write_manifest(tmp_path, "99.0.0")
    (tmp_path / AGENTS_MD).write_bytes(b"\xff")

    proc = _cli("validate", "--repo-root", str(tmp_path), "--help")

    assert proc.returncode == 0
    assert "records 99.0.0 (.specyrd/manifest.json)" in proc.stderr
    assert proc.stderr.count("older install earlier on PATH") == 1


def test_silent_when_running_matches_the_recorded_version(tmp_path: Path) -> None:
    _write_manifest(tmp_path, __version__)

    proc = _cli("validate", "--repo-root", str(tmp_path), "--help")

    assert proc.returncode == 0
    assert "older install earlier on PATH" not in proc.stderr


def test_silent_when_running_is_newer_than_every_recorded_source(tmp_path: Path) -> None:
    _write_manifest(tmp_path, "0.0.1")

    proc = _cli("validate", "--repo-root", str(tmp_path), "--help")

    assert proc.returncode == 0
    assert "older install earlier on PATH" not in proc.stderr


def test_doctor_emits_the_skew_warning(tmp_path: Path) -> None:
    _write_manifest(tmp_path, "99.0.0")

    proc = _cli("doctor", "--repo-root", str(tmp_path))

    assert proc.returncode != 0
    assert proc.stderr.count("older install earlier on PATH") == 1
