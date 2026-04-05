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
