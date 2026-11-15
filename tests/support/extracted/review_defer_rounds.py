"""One shared copy of a helper that had identical definitions in several test modules."""
from __future__ import annotations

from pathlib import Path

def _runs(repo: Path, command: str) -> int:
    """Run a status ``next`` command exactly as printed (plus ``--repo-root``)."""
    import shlex
    import subprocess

    argv = shlex.split(command)
    assert argv[0] == "specy-road", command
    return subprocess.run(_cli(argv[1:], repo), capture_output=True, text=True, cwd=repo,
                          env=_this_checkout()).returncode

def _cli(args: list[str], repo: Path) -> list[str]:
    """``specy-road <args>`` from this checkout's package, not whichever ``specy-road`` is first on PATH."""
    import sys

    return [sys.executable, "-c", "import sys; from specy_road.cli import main; main(sys.argv[1:])",
            *args, "--repo-root", str(repo)]

def _this_checkout() -> dict[str, str]:
    import os

    return {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[3])}
