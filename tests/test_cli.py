"""Smoke tests for specy-road CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DOGFOOD = REPO / "tests" / "fixtures" / "specy_road_dogfood"


def test_specy_road_validate() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "validate",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        check=True,
    )


def test_specy_road_sync_no_git() -> None:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "sync",
            "--no-git",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        check=True,
    )


def test_specy_road_list_nodes() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "list-nodes",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "M0" in r.stdout


def test_specy_road_show_node() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "show-node",
            "M0.1",
            "--repo-root",
            str(DOGFOOD),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "M0.1" in r.stdout


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
    assert "--base" in r.stdout
    assert "--interactive" in r.stdout
    assert "--no-ci-skip-in-message" in r.stdout
    assert "--no-sync" not in r.stdout
    assert "--no-push-registry" not in r.stdout


def test_specy_road_init_requires_subcommand() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "init"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    err = (r.stderr or "") + (r.stdout or "")
    assert "project" in err or "gui" in err


def test_specy_road_init_install_gui_dry_run() -> None:
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "specy_road.cli",
            "init",
            "gui",
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
            "gui",
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
            "gui",
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
            "gui",
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
