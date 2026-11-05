"""Which specy-road install is running, and managed blocks another version wrote (M13.1)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from specy_road import __version__, agent_guide_block, cli
from specy_road.agent_guide_block import apply_agent_guide_block
from specy_road.managed_block import HTML_COMMENT
from specy_road.version_skew import (
    launchers_on_path,
    print_install_report,
    warn_if_blocks_written_by_other_version,
)


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


@pytest.mark.skipif(os.name == "nt", reason="POSIX launchers and symlinks")
def test_parent_components_and_links_out_of_prefix_are_not_running(tmp_path: Path, monkeypatch, capsys) -> None:
    prefix = tmp_path / "running-env"
    running = _launcher(prefix / "bin" / "specy-road")
    foreign = _launcher(tmp_path / "foreign" / "specy-road")
    (prefix / "links").mkdir()
    (prefix / "links" / "specy-road").symlink_to(foreign)   # inside the prefix, but runs another install
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(sys, "argv", ["pytest"])
    dotted = f"{prefix}{os.sep}..{os.sep}foreign"   # lexically below the prefix, really beside it
    path_env = os.pathsep.join([dotted, str(prefix / "links"), str(running.parent)])

    found = launchers_on_path(path_env)

    assert [(ln.path, ln.resolved, ln.running) for ln in found] == [
        (Path(dotted) / "specy-road", foreign.resolve(), False),
        (prefix / "links" / "specy-road", foreign.resolve(), False),
        (running, running.resolve(), True),
    ]
    print_install_report(path_env)
    err = capsys.readouterr().err
    assert "first specy-road on PATH" in err and str(foreign.resolve()) in err


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_symlinked_prefix_and_trailing_slash_still_running(tmp_path: Path, monkeypatch, capsys) -> None:
    real = tmp_path / "real-env"
    running = _launcher(real / "bin" / "specy-road")
    (tmp_path / "link-env").symlink_to(real)
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "link-env") + os.sep)
    monkeypatch.setattr(sys, "argv", ["pytest"])
    path_env = os.pathsep.join([str(tmp_path / "link-env" / "bin") + os.sep, str(running.parent)])

    assert [ln.running for ln in launchers_on_path(path_env)] == [True, True]
    print_install_report(path_env)
    assert "warning" not in capsys.readouterr().err


@pytest.mark.skipif(os.name == "nt", reason="POSIX launchers")
def test_no_shadow_warning_when_running_install_is_first(tmp_path: Path, monkeypatch, capsys) -> None:
    prefix = tmp_path / "running-env"
    running = _launcher(prefix / "bin" / "specy-road")
    other = _launcher(tmp_path / "other" / "bin" / "specy-road")
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(sys, "argv", ["pytest"])
    print_install_report(os.pathsep.join([str(running.parent), str(other.parent)]))
    assert "warning" not in capsys.readouterr().err


@pytest.mark.skipif(os.name == "nt", reason="POSIX launchers")
def test_empty_path_component_is_the_current_directory(tmp_path: Path, monkeypatch, capsys) -> None:
    prefix = tmp_path / "running-env"
    running = _launcher(prefix / "bin" / "specy-road")
    cwd = tmp_path / "project"
    foreign = _launcher(cwd / "specy-road")
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(sys, "prefix", str(prefix))
    monkeypatch.setattr(sys, "argv", ["pytest"])
    path_env = os.pathsep + str(running.parent)   # "" first: the shell looks in ./ before the running install

    found = launchers_on_path(path_env)

    assert [(ln.path, ln.resolved, ln.running) for ln in found] == [
        (foreign, foreign.resolve(), False),
        (running, running.resolve(), True),
    ]
    print_install_report(path_env)
    err = capsys.readouterr().err
    assert "first specy-road on PATH" in err and str(foreign.resolve()) in err


def test_generated_claude_md_block_at_running_version_is_silent(tmp_path: Path, capsys) -> None:
    apply_agent_guide_block(tmp_path)
    assert f"Written by specy-road {__version__};" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    warn_if_blocks_written_by_other_version(tmp_path)
    assert capsys.readouterr().err == ""


def test_generated_claude_md_block_from_older_version_names_clean_version(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(agent_guide_block, "__version__", "0.0.1")
    apply_agent_guide_block(tmp_path)
    monkeypatch.undo()
    warn_if_blocks_written_by_other_version(tmp_path)
    err = capsys.readouterr().err
    assert f"CLAUDE.md block written by specy-road 0.0.1, running {__version__}; run `specy-road upgrade`." in err


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
