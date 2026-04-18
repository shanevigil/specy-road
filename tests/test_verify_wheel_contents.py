"""Unit tests for scripts/verify_wheel_contents.py."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "verify_wheel_contents.py"


def _make_wheel(path: Path, members: dict[str, str]) -> None:
    """Build a tiny zip-shaped 'wheel' with the named members."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)


def _run(wheel: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(wheel)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_passes_with_required_assets(tmp_path: Path) -> None:
    wheel = tmp_path / "specy_road-0.1.0-py3-none-any.whl"
    _make_wheel(wheel, {
        "specy_road/__init__.py": "",
        "specy_road/pm_gantt_static/index.html": "<!doctype html>",
        "specy_road/pm_gantt_static/assets/index-abc123.js": "console.log('hi')",
    })
    r = _run(wheel)
    assert r.returncode == 0, r.stderr
    assert "contains PM Gantt UI assets" in r.stdout


def test_fails_when_index_html_missing(tmp_path: Path) -> None:
    wheel = tmp_path / "broken.whl"
    _make_wheel(wheel, {
        "specy_road/__init__.py": "",
        "specy_road/pm_gantt_static/assets/index-abc123.js": "x",
    })
    r = _run(wheel)
    assert r.returncode == 1
    assert "specy_road/pm_gantt_static/index.html" in r.stderr


def test_fails_when_no_js_chunk(tmp_path: Path) -> None:
    wheel = tmp_path / "broken2.whl"
    _make_wheel(wheel, {
        "specy_road/__init__.py": "",
        "specy_road/pm_gantt_static/index.html": "<!doctype html>",
    })
    r = _run(wheel)
    assert r.returncode == 1
    assert "specy_road/pm_gantt_static/assets/index-" in r.stderr


def test_fails_when_wheel_missing(tmp_path: Path) -> None:
    r = _run(tmp_path / "absent.whl")
    assert r.returncode == 1
    assert "wheel not found" in r.stderr
