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
    assert ".cursor/commands/specyrd-constitution.md" in r.written
    assert ".cursor/commands/specyrd-sync.md" in r.written
    assert ".specyrd/README.md" in r.written
    assert not (tmp_path / ".cursor").exists()


def test_specyrd_migrates_legacy_dot_specyr_manifest(tmp_path: Path) -> None:
    """``.specyr/manifest.json`` is copied to ``.specyrd/`` and the legacy file is removed."""
    leg = tmp_path / ".specyr"
    leg.mkdir()
    (leg / "manifest.json").write_text(
        json.dumps({"specyr_version": "0.0.1", "agents": {"cursor": ["old"]}}),
        encoding="utf-8",
    )
    run_init(
        target=tmp_path,
        agent="cursor",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
    )
    primary = tmp_path / ".specyrd" / "manifest.json"
    assert primary.is_file()
    data = json.loads(primary.read_text(encoding="utf-8"))
    assert "specyrd_version" in data
    assert "cursor" in data["agents"]
    assert not (leg / "manifest.json").is_file()


def test_specyrd_init_removes_stale_legacy_when_primary_exists(tmp_path: Path) -> None:
    (tmp_path / ".specyrd").mkdir(parents=True)
    (tmp_path / ".specyrd" / "manifest.json").write_text(
        json.dumps({"specyrd_version": "9.9.9", "agents": {}}),
        encoding="utf-8",
    )
    leg = tmp_path / ".specyr"
    leg.mkdir()
    (leg / "manifest.json").write_text("{}", encoding="utf-8")
    run_init(
        target=tmp_path,
        agent="cursor",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
    )
    assert not (leg / "manifest.json").is_file()


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
    assert "planning/<node-id>" in text or "planning/" in text
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
    assert "specy-road brief" in p.read_text(encoding="utf-8")


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


def test_specyrd_init_role_both_matches_full_set(tmp_path: Path) -> None:
    r_both = run_init(
        target=tmp_path,
        agent="cursor",
        dry_run=True,
        force=False,
        ai_commands_dir=None,
        role="both",
    )
    r_all = run_init(
        target=tmp_path,
        agent="cursor",
        dry_run=True,
        force=False,
        ai_commands_dir=None,
        role=None,
    )
    assert sorted(r_both.written) == sorted(r_all.written)


def test_specyrd_init_writes_claude_md(tmp_path: Path) -> None:
    run_init(
        target=tmp_path,
        agent="claude-code",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
        write_claude_md=True,
    )
    p = tmp_path / "CLAUDE.md"
    assert p.is_file()
    assert "AGENTS.md" in p.read_text(encoding="utf-8")


def test_specyrd_init_gui_settings_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "specy_road.specyrd_init.Path.home",
        lambda: tmp_path,
    )
    run_init(
        target=tmp_path,
        agent="cursor",
        dry_run=False,
        force=False,
        ai_commands_dir=None,
        gui_settings_stub=True,
    )
    gui = tmp_path / ".specy-road" / "gui-settings.json"
    assert gui.is_file()
    data = json.loads(gui.read_text(encoding="utf-8"))
    assert "llm" in data


def test_specyrd_cli_no_prompt_requires_role(tmp_path: Path) -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.specyrd_cli",
            "init",
            str(tmp_path),
            "--ai",
            "cursor",
            "--no-prompt",
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    assert "--no-prompt requires --role" in r.stderr


def test_specyrd_cli_extras_dry_run_skips_pip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: list[str] = []

    def fake_check_call(cmd: list[str], **_: object) -> None:
        called.append(" ".join(cmd))

    monkeypatch.setattr("specy_road.specyrd_cli.subprocess.check_call", fake_check_call)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.specyrd_cli",
            "init",
            str(tmp_path),
            "--ai",
            "cursor",
            "--role",
            "pm",
            "--extras",
            "review",
            "--dry-run",
        ],
        cwd=REPO,
        check=True,
    )
    assert not called
