"""Shared git subprocess helpers for PM/CLI support modules."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git_ok(args: list[str], cwd: Path, timeout: float) -> tuple[bool, str]:
    """Run ``git`` command and return ``(ok, output_or_error)``."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "").strip()
    return True, (result.stdout or "").strip()
