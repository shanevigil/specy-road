"""Tests for markdown export."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_export_check_matches_repo() -> None:
    subprocess.run(
        [sys.executable, str(REPO / "scripts" / "export_roadmap_md.py"), "--check"],
        cwd=REPO,
        check=True,
    )
