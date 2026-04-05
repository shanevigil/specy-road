"""Tests for file limit validator."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_file_limits_passes_on_repo() -> None:
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "validate_file_limits.py")],
        cwd=REPO,
        check=True,
    )
