"""Running specy-road older than the project's recorded minimum."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from specy_road import __version__
from specy_road.bundled_scripts import doctor
from specy_road.managed_block import HTML_COMMENT, render_block
from specy_road.agents_md_block import AGENTS_MD, render_agents_lines
from specy_road import cli


def _write_manifest(root: Path, version: str) -> None:
    path = root / ".specyrd" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"specyrd_version": version, "project_root": "."}), encoding="utf-8")


def _write_agents_block(root: Path, *, written_by: str | None = None, minimum: str | None = None) -> None:
    lines = render_agents_lines()
    block = render_block(lines, style=HTML_COMMENT)
    if written_by is not None:
        block = block.replace(f"Written by specy-road {__version__};", f"Written by specy-road {written_by};")
    if minimum is not None:
        block = block.replace(
            f"**Minimum specy-road version:** {__version__}.",
            f"**Minimum specy-road version:** {minimum}.",
        )
    (root / AGENTS_MD).write_text(f"# Agents\n\n{block}\n", encoding="utf-8")


@pytest.mark.parametrize(
    "recorded",
    ["99.0.0", "0.3.1rc99"],
)
def test_warns_when_the_running_version_is_older_than_the_manifest(
    tmp_path: Path, capsys, recorded: str
) -> None:
    _write_manifest(tmp_path, recorded)

    cli.warn_if_running_version_older(tmp_path)

    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert f"specy-road {__version__} is running but this project records {recorded}" in err
    assert "older install earlier on PATH" in err


def test_warns_when_the_running_version_is_older_than_agents_md(tmp_path: Path, capsys) -> None:
    _write_agents_block(tmp_path, written_by="99.0.0", minimum="99.0.0")

    cli.warn_if_running_version_older(tmp_path)

    err = capsys.readouterr().err
    assert f"records 99.0.0 ({AGENTS_MD})" in err


def test_silent_when_running_matches_or_exceeds_the_recorded_version(tmp_path: Path, capsys) -> None:
    _write_manifest(tmp_path, __version__)
    _write_agents_block(tmp_path)

    cli.warn_if_running_version_older(tmp_path)
    assert capsys.readouterr().err == ""

    _write_manifest(tmp_path, "0.0.1")
    cli.warn_if_running_version_older(tmp_path)
    assert capsys.readouterr().err == ""


def test_doctor_emits_the_skew_warning(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_manifest(tmp_path, "99.0.0")
    monkeypatch.setattr(doctor, "_context", lambda ns: None)

    with pytest.raises(SystemExit) as exc:
        doctor.main(["--repo-root", str(tmp_path)])

    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert err.count("older install earlier on PATH") == 1


def test_cli_warns_once_for_other_commands(tmp_path: Path, capsys, monkeypatch) -> None:
    _write_manifest(tmp_path, "99.0.0")

    def stop(_script: str, _args: list[str]) -> None:
        raise SystemExit(0)

    monkeypatch.setattr(cli, "_run", stop)

    with pytest.raises(SystemExit):
        cli.main(["validate", "--repo-root", str(tmp_path)])

    err = capsys.readouterr().err
    assert err.count("older install earlier on PATH") == 1
