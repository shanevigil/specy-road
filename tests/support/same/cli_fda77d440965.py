"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.helpers import REPO
from tests.helpers import script_subprocess_env
import subprocess
import sys

def _cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "specy_road.cli", *args, "--repo-root", str(root)],
                          cwd=REPO, env=script_subprocess_env(), capture_output=True, text=True)
