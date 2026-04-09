"""Tests for specy-road init and install-gui helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from specy_road.cli_init import (
    build_install_gui_command,
    specy_road_repo_root_for_editable_install,
)

REPO = Path(__file__).resolve().parent.parent


def test_specy_road_repo_root_for_editable_install_from_test_env() -> None:
    root = specy_road_repo_root_for_editable_install()
    assert root is not None
    assert (root / "pyproject.toml").is_file()
    assert 'name = "specy-road"' in (root / "pyproject.toml").read_text(encoding="utf-8")


def test_build_install_gui_command_editable_when_in_repo() -> None:
    cmd, cwd = build_install_gui_command()
    assert "-e" in cmd
    assert ".[gui-next]" in cmd
    assert cwd is not None
    assert (cwd / "pyproject.toml").is_file()


def test_build_install_gui_command_pypi_when_no_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_pkg = tmp_path / "site_packages" / "specy_road"
    fake_pkg.mkdir(parents=True)
    (fake_pkg / "__init__.py").write_text("", encoding="utf-8")

    import specy_road.cli_init as cli_init_mod

    def fake_repo_root() -> None:
        return None

    monkeypatch.setattr(cli_init_mod, "specy_road_repo_root_for_editable_install", fake_repo_root)
    cmd, cwd = cli_init_mod.build_install_gui_command()
    assert cmd[-1] == "specy-road[gui-next]"
    assert cwd is None
