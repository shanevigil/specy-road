"""Unit tests for scripts/verify_wheel_contents.py."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "verify_wheel_contents.py"


COMPLETE_WHEEL = {
    "specy_road/__init__.py": "",
    "specy_road/pm_gantt_static/index.html": "<!doctype html>",
    "specy_road/pm_gantt_static/assets/index-abc123.js": "console.log('hi')",
    "specy_road/templates/project/.gitignore": "work/prompt-*.md\n",
    "specy_road/templates/project/work/.gitkeep": "",
    "specy_road/schemas/archive.schema.json": "{}",
}


def _make_wheel(path: Path, members: dict[str, str]) -> None:
    """Build a tiny zip-shaped 'wheel' with the named members."""
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in members.items():
            zf.writestr(name, content)


def _wheel_without(path: Path, *omit: str) -> None:
    _make_wheel(path, {k: v for k, v in COMPLETE_WHEEL.items() if k not in omit})


def _run(wheel: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(wheel)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_passes_with_required_assets(tmp_path: Path) -> None:
    wheel = tmp_path / "specy_road-0.1.0-py3-none-any.whl"
    _make_wheel(wheel, COMPLETE_WHEEL)
    r = _run(wheel)
    assert r.returncode == 0, r.stderr
    assert "scaffold dotfiles" in r.stdout


def test_fails_when_the_bundled_archive_schema_is_missing(tmp_path: Path) -> None:
    """Without it every archive command dies as a broken install."""
    wheel = tmp_path / "broken-schema.whl"
    _wheel_without(wheel, "specy_road/schemas/archive.schema.json")
    r = _run(wheel)
    assert r.returncode == 1
    assert "specy_road/schemas/archive.schema.json" in r.stderr


def test_fails_when_index_html_missing(tmp_path: Path) -> None:
    wheel = tmp_path / "broken.whl"
    _wheel_without(wheel, "specy_road/pm_gantt_static/index.html")
    r = _run(wheel)
    assert r.returncode == 1
    assert "specy_road/pm_gantt_static/index.html" in r.stderr


def test_fails_when_no_js_chunk(tmp_path: Path) -> None:
    wheel = tmp_path / "broken2.whl"
    _wheel_without(wheel, "specy_road/pm_gantt_static/assets/index-abc123.js")
    r = _run(wheel)
    assert r.returncode == 1
    assert "specy_road/pm_gantt_static/assets/index-" in r.stderr


def test_fails_when_scaffold_gitignore_missing(tmp_path: Path) -> None:
    """package-data globs skip dotfiles, and an editable checkout hides it."""
    wheel = tmp_path / "broken3.whl"
    _wheel_without(wheel, "specy_road/templates/project/.gitignore")
    r = _run(wheel)
    assert r.returncode == 1
    assert "specy_road/templates/project/.gitignore" in r.stderr
    assert "dotfiles" in r.stderr


def test_fails_when_wheel_missing(tmp_path: Path) -> None:
    r = _run(tmp_path / "absent.whl")
    assert r.returncode == 1
    assert "wheel not found" in r.stderr
