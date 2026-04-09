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
