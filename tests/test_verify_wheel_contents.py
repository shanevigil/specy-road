"""Unit tests for scripts/verify_wheel_contents.py."""

from __future__ import annotations

import io
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "verify_wheel_contents.py"


COMPLETE_WHEEL = {
    "specy_road/__init__.py": "",
    "specy_road/pm_gantt_static/index.html": "<!doctype html>",
    "specy_road/pm_gantt_static/assets/index-abc123.js": "console.log('hi')",
    "specy_road/templates/project/.gitignore": "work/prompt-*.md\n",
    "specy_road/templates/project/work/.gitkeep": "",
    "specy_road/schemas/archive.schema.json": "{}",
    "specy_road/schemas/handoff.schema.json": "{}",
    "specy_road/schemas/review-record.schema.json": "{}",
    "specy_road/templates/project/model-profiles/README.md": "# profiles",
    "specy_road/templates/project/model-profiles/anthropic-claude/claude-opus-5-5.md": "---\n---\n",
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


SHIPPED_TEMPLATES = [
    "specy_road/templates/project/research/README.md",
    "specy_road/templates/project/work/handoff-ready.template.md",
    "specy_road/templates/specyrd/commands/specyrd-prompt.md",
]


def _pack(path: Path, fmt: str, files: dict[str, str]) -> None:
    if fmt == "zip":
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return
    with tarfile.open(path, "w:gz") as archive:
        directories = {"pkg-1.0"}
        for name in files:
            parent = Path(name).parent
            while str(parent) not in (".", ""):
                directories.add(f"pkg-1.0/{parent.as_posix()}")
                parent = parent.parent
        for directory in sorted(directories):
            for stored in (directory, f"{directory}/"):
                info = tarfile.TarInfo(stored)
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(f"pkg-1.0/{name}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))


@pytest.mark.parametrize("fmt", ["zip", "gztar"])
@pytest.mark.parametrize("scenario", ["denied-member", "denied-text", "shipped"])
def test_sdist_and_wheel_promotion_scan(tmp_path: Path, fmt: str, scenario: str) -> None:
    if scenario == "denied-member":
        files = {"docs/design-notes/x.md": "x\n"}
    elif scenario == "denied-text":
        files = {"README.md": "Claude-" + "Session: abc\n"}
    else:
        files = {name: "x\n" for name in SHIPPED_TEMPLATES}
    archive = tmp_path / ("dist.zip" if fmt == "zip" else "dist.tar.gz")
    _pack(archive, fmt, files)
    result = _run(archive)
    assert result.returncode == (0 if scenario == "shipped" else 1), result.stderr
    if scenario == "denied-member":
        assert "docs/design-notes/x.md" in result.stderr
        assert "pkg-1.0/docs/design-notes/x.md" not in result.stderr
    if scenario == "denied-text" and fmt == "gztar":
        assert "README.md" in result.stderr
        assert "pkg-1.0/README.md" not in result.stderr


@pytest.mark.parametrize("name", ["broken.zip", "broken.tar.gz"])
def test_fails_when_the_archive_cannot_be_read(tmp_path: Path, name: str) -> None:
    bad = tmp_path / name
    bad.write_bytes(b"not an archive")
    assert _run(bad).returncode != 0
