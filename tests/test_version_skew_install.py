"""Which specy-road install is running, and managed blocks another version wrote (M13.1)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from specy_road import __version__, cli
from specy_road.managed_block import HTML_COMMENT
from specy_road.version_skew import launchers_on_path, print_install_report


def _launcher(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


@pytest.mark.skipif(os.name == "nt", reason="POSIX launchers and symlinks")
def test_launchers_in_path_order_and_shadow_warning(tmp_path: Path, monkeypatch, capsys) -> None:
    prefix = tmp_path / "running-env"
    running = _launcher(prefix / "bin" / "specy-road")
    other = _launcher(tmp_path / "other" / "bin" / "specy-road")
    links = tmp_path / "links"
    links.mkdir()
    (links / "specy-road").symlink_to(running)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(sys, "argv", ["pytest"])
    path_env = os.pathsep.join([str(other.parent), str(links), str(tmp_path / "missing")])

    found = launchers_on_path(path_env)

    assert [(ln.path, ln.resolved, ln.running) for ln in found] == [
        (other, other.resolve(), False),
        (links / "specy-road", running.resolve(), True),
    ]
    print_install_report(path_env)
    out, err = capsys.readouterr()
    assert out.index(str(other)) < out.index(str(links / "specy-road"))
    assert f"-> {running.resolve()}" in out
    assert "first specy-road on PATH" in err and str(other.resolve()) in err and str(prefix) in err
    assert "which -a specy-road" in err


@pytest.mark.skipif(os.name == "nt", reason="POSIX launchers")
def test_no_shadow_warning_when_running_install_is_first(tmp_path: Path, monkeypatch, capsys) -> None:
    prefix = tmp_path / "running-env"
    running = _launcher(prefix / "bin" / "specy-road")
    other = _launcher(tmp_path / "other" / "bin" / "specy-road")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(sys, "argv", ["pytest"])
    print_install_report(os.pathsep.join([str(running.parent), str(other.parent)]))
    assert "warning" not in capsys.readouterr().err


def _block(written_by: str) -> str:
    return (
        f"# Project\n\n{HTML_COMMENT.start}\nWritten by specy-road {written_by} "
        f"(minimum {written_by}); `specy-road upgrade` rewrites only this section.\n{HTML_COMMENT.end}\n"
    )


def test_validate_warns_on_block_from_other_version_with_matching_manifest(tmp_path: Path, capsys) -> None:
    (tmp_path / ".specyrd").mkdir()
    (tmp_path / ".specyrd" / "manifest.json").write_text(json.dumps({"specyrd_version": __version__}))
    (tmp_path / "AGENTS.md").write_text(_block("0.0.1"), encoding="utf-8")
    (tmp_path / "CLAUDE.md").write_text(_block(__version__), encoding="utf-8")

    with pytest.raises(SystemExit):
        cli.main(["validate", "--repo-root", str(tmp_path)])
    err = capsys.readouterr().err

    assert f"AGENTS.md block written by specy-road 0.0.1, running {__version__}" in err
    assert "specy-road upgrade" in err
    assert "CLAUDE.md block" not in err
    assert "this project records" not in err   # the older-than-recorded warning stays quiet


def test_claude_md_block_from_other_version_warns(tmp_path: Path, capsys) -> None:
    (tmp_path / "CLAUDE.md").write_text(_block("0.0.1"), encoding="utf-8")
    with pytest.raises(SystemExit):
        cli.main(["validate", "--repo-root", str(tmp_path)])
    assert f"CLAUDE.md block written by specy-road 0.0.1, running {__version__}" in capsys.readouterr().err
