"""Run a command from a test: in this process, or as the child process a user's shell starts."""

from __future__ import annotations

import contextlib
import io
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from specy_road import cli
from specy_road.bundled_scripts import worker_cli
from tests.helpers import script_subprocess_env


def run_cli(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """``specy-road <argv>`` in this process, with what it prints from Python captured.

    Output a child process writes straight to the descriptors (a git command's) is not captured;
    use :func:`run_cli_subprocess` when a test reads it.
    """
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        status = cli.run(argv)
    argv_run = ["specy-road", *argv]
    return subprocess.CompletedProcess(argv_run, status, out.getvalue(), err.getvalue())


def run_cli_subprocess(
    argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """``specy-road <argv>`` as a child process importing this checkout's package."""
    return subprocess.run(
        [sys.executable, "-m", "specy_road.cli", *argv],
        cwd=cwd,
        env=env or script_subprocess_env(),
        capture_output=True,
        text=True,
        check=False,
    )


def run_main(mod: ModuleType, *args: str) -> int:
    """Call ``mod.main(args)``; return its exit status (0 when it returns without exiting)."""
    with pytest.raises(SystemExit) as e:
        mod.main(list(args))
        raise SystemExit(0)
    return e.value.code or 0


def run_worker_cli(*args: str) -> int:
    """Call ``worker_cli.main(args)``, which must exit; return its exit status."""
    with pytest.raises(SystemExit) as e:
        worker_cli.main(list(args))
    return e.value.code or 0
