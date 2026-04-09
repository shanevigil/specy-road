"""Smoke tests for specy-road CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_specy_road_validate() -> None:
    subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "validate"],
        cwd=REPO,
        check=True,
    )


def test_specy_road_sync_no_git() -> None:
    subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "sync", "--no-git"],
        cwd=REPO,
        check=True,
    )


def test_specy_road_list_nodes() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "list-nodes"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "M0" in r.stdout


def test_specy_road_show_node() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "show-node", "M0.1.1"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "M0.1.1" in r.stdout


def test_specy_road_do_next_available_task_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "do-next-available-task",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--no-sync" in r.stdout
    assert "--base" in r.stdout


def test_specy_road_init_requires_some_action() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "init"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    err = (r.stderr or "") + (r.stdout or "")
    assert "build-gui" in err
    assert "install-gui" in err


def test_specy_road_init_install_gui_dry_run() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "--install-gui",
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Would run:" in r.stdout
    assert "pip" in r.stdout
    assert "gui-next" in r.stdout
    assert "--upgrade" in r.stdout
    assert "npm" in r.stdout
    assert "npm run build" in r.stdout


def test_specy_road_init_reinstall_gui_dry_run() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "--reinstall-gui",
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Would run:" in r.stdout
    assert "--force-reinstall" in r.stdout
    assert "gui-next" in r.stdout
    assert "npm run build" in r.stdout


def test_specy_road_init_install_gui_skip_npm_dry_run() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "--install-gui",
            "--skip-npm-build",
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "gui-next" in r.stdout
    assert "Would skip npm build" in r.stdout
    assert "npm run build" not in r.stdout


def test_specy_road_init_build_gui_only_dry_run() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "--build-gui",
            "--dry-run",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "npm" in r.stdout
    assert "pm-gantt" in r.stdout
    assert "npm run build" in r.stdout
    assert "pip" not in r.stdout
    assert "gui-next" not in r.stdout


def test_specy_road_finish_this_task_help() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "finish-this-task",
            "--help",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--push" in r.stdout
