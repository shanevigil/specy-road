"""B4: `specy-road --version` used to print "unknown command: --version"."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_specy_road_version_flag() -> None:
    """B4: the first thing anyone types when filing a bug or pinning an image."""
    from specy_road import __version__

    for flag in ("--version", "-V"):
        r = subprocess.run(
            [sys.executable, "-m", "specy_road.cli", flag],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
        assert r.stdout.strip() == f"specy-road {__version__}"


def test_specyrd_version_flag() -> None:
    from specy_road import __version__

    r = subprocess.run(
        [sys.executable, "-m", "specy_road.specyrd_cli", "--version"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert r.stdout.strip() == f"specyrd {__version__}"


def test_specy_road_usage_lists_version_flag() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "specy_road.cli", "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--version" in r.stdout
