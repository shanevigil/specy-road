"""Tests for file limit validator."""

from __future__ import annotations

import subprocess
import sys
from tests.helpers import BUNDLED_SCRIPTS, REPO, script_subprocess_env


def test_file_limits_passes_on_repo() -> None:
    subprocess.run(
        [sys.executable, str(BUNDLED_SCRIPTS / "validate_file_limits.py")],
        cwd=REPO,
        env=script_subprocess_env(),
        check=True,
    )
