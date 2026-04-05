"""Tests for specyrd init (IDE glue installer)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from specy_road.specyrd_init import run_init

REPO = Path(__file__).resolve().parent.parent


def test_specyrd_init_dry_run_cursor(tmp_path: Path) -> None:
    r = run_init(
        target=tmp_path,
        agent="cursor",
        dry_run=True,
        force=False,
        ai_commands_dir=None,
    )
    assert r.dry_run
    assert ".cursor/commands/specyrd-validate.md" in r.written
    assert ".specyrd/README.md" in r.written
    assert not (tmp_path / ".cursor").exists()


def test_specyrd_init_writes_cursor(tmp_path: Path) -> None:
    run_init(
        target=tmp_path,
        agent="cursor",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
    )
    v = tmp_path / ".cursor" / "commands" / "specyrd-validate.md"
    assert v.is_file()
    text = v.read_text(encoding="utf-8")
    assert "specy-road validate" in text
    assert "specify/<node-id>" in text or "specify" in text
    manifest = tmp_path / ".specyrd" / "manifest.json"
    assert manifest.is_file()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "cursor" in data["agents"]
    assert "specyrd_version" in data


def test_specyrd_init_generic_requires_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="--ai-commands-dir"):
        run_init(
            target=tmp_path,
            agent="generic",
            dry_run=True,
            force=False,
            ai_commands_dir=None,
        )


def test_specyrd_init_generic_writes(tmp_path: Path) -> None:
    run_init(
        target=tmp_path,
        agent="generic",
        dry_run=False,
        force=False,
        ai_commands_dir=Path("docs/agent-cmds"),
    )
    p = tmp_path / "docs" / "agent-cmds" / "specyrd-brief.md"
    assert p.is_file()
    assert "generate_brief.py" in p.read_text(encoding="utf-8")


def test_specyrd_init_rejects_parent_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="\\.\\."):
        run_init(
            target=tmp_path,
            agent="generic",
            dry_run=True,
            force=False,
            ai_commands_dir=Path(".."),
        )


def test_specyrd_init_skips_without_force(tmp_path: Path) -> None:
    cmd = tmp_path / ".cursor" / "commands" / "specyrd-validate.md"
    cmd.parent.mkdir(parents=True, exist_ok=True)
    cmd.write_text("keep", encoding="utf-8")
    r = run_init(
        target=tmp_path,
        agent="cursor",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
    )
    assert r.skipped
    assert cmd.read_text(encoding="utf-8") == "keep"


def test_specyrd_cli_smoke() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.specyrd_cli",
            "init",
            str(REPO),
            "--ai",
            "cursor",
            "--dry-run",
        ],
        cwd=REPO,
        check=True,
    )
