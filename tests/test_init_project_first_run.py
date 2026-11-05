"""A project fresh from ``init project`` passes its own checks after the first commit."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from specy_road.bundled_scripts import digest_cli, export_roadmap_md, validate_roadmap
from specy_road.init_project import run_init_project


def _argv_main(main: Callable[[], None], monkeypatch, *argv: str) -> Callable[[], None]:
    def run() -> None:
        monkeypatch.setattr(sys, "argv", ["specy-road", *argv])
        main()
    return run


def _exit_code(run: Callable[[], None]) -> int:
    try:
        run()
    except SystemExit as e:
        return e.code or 0
    return 0


def _first_commit(root: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "init"],
                   cwd=root, check=True)


@pytest.mark.parametrize("name, args", [
    ("validate", ()),
    ("validate", ("--strict",)),
    ("export", ("--check",)),
    ("digest", ("--check",)),
])
def test_a_new_project_passes_each_check_with_nothing_about_the_scaffold(
        tmp_path: Path, capsys, monkeypatch, name: str, args: tuple[str, ...]) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    assert run_init_project(tmp_path) == 0
    _first_commit(tmp_path)
    capsys.readouterr()
    repo_args = (*args, "--repo-root", str(tmp_path))
    run = {
        "validate": _argv_main(validate_roadmap.main, monkeypatch, *repo_args),
        "export": _argv_main(export_roadmap_md.main, monkeypatch, *repo_args),
        "digest": lambda: digest_cli.main(["digest", *repo_args]),
    }[name]

    code = _exit_code(run)

    cap = capsys.readouterr()
    assert code == 0, cap.out + cap.err
    for scaffold_name in ("my-executor", "vision.md"):
        assert scaffold_name not in cap.out + cap.err
