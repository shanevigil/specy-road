"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path
from tests.helpers import REPO
from tests.helpers import script_subprocess_env
import subprocess
from tests.support.cli import run_cli

def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Shared test helper."""
    return run_cli([*args, "--repo-root", str(root)], cwd=REPO, env=script_subprocess_env())
