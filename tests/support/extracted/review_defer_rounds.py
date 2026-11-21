"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from tests.support.cli import run_cli


def runs(repo: Path, command: str) -> int:
    """Run a status ``next`` command exactly as printed (plus ``--repo-root``)."""
    argv = shlex.split(command)
    assert argv[0] == "specy-road", command
    return cli(argv[1:], repo).returncode


def cli(args: list[str], repo: Path) -> subprocess.CompletedProcess[str]:
    """``specy-road <args> --repo-root <repo>`` from ``repo``, in this process."""
    return run_cli([*args, "--repo-root", str(repo)], cwd=repo)
