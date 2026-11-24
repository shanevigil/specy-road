"""Run a command from a test: in this process, or as the child process a user's shell starts."""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import subprocess
import sys
import tempfile
import traceback
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import IO

import pytest

from specy_road import cli
from specy_road.bundled_scripts import worker_cli
from tests.helpers import BUNDLED_SCRIPTS, script_subprocess_env


def run_cli(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """``specy-road <argv>`` in this process (:func:`run_in_process`)."""
    return run_in_process(["specy-road", *argv], cwd=cwd, env=env, input=input)


#: The entry module each console script runs.
CONSOLE_SCRIPTS = {"specy-road": "specy_road.cli", "specyrd": "specy_road.specyrd_cli"}


def run_module(
    module: str, argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """``python -m <module> <argv>`` in this process (:func:`run_in_process`).

    An entry module runs as its console script (``specy-road``, ``specyrd``); a bundled module
    has its file as ``sys.argv[0]``, as ``-m`` gives it.
    """
    scripts = {entry: name for name, entry in CONSOLE_SCRIPTS.items()}
    argv0 = scripts.get(module) or str(importlib.import_module(module).__file__)
    return run_in_process([argv0, *argv], cwd=cwd, env=env)


def run_script(
    script: str, argv: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """``python <bundled_scripts>/<script> <argv>`` in this process (:func:`run_in_process`).

    ``sys.argv[0]`` is the script's path, so argparse names the program ``<script>`` as it did.
    """
    return run_in_process([str(BUNDLED_SCRIPTS / script), *argv], cwd=cwd, env=env)


def run_in_process(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input: str | None = None,
    stderr_to_stdout: bool = False,
) -> subprocess.CompletedProcess[str]:
    """The child ``argv`` run in this process: ``main()`` of the module ``argv[0]`` names.

    ``argv[0]`` is a console script (:data:`CONSOLE_SCRIPTS`) or a bundled script's path. The
    output is read at the file descriptors too, so a git command the CLI runs is captured, as
    :func:`specy_road.cli.run_captured` does. While it runs, ``sys.argv`` is ``argv`` (``main``
    reads it, and argparse names the program from it, as in the child), the working directory is
    ``cwd``, ``os.environ`` is ``env`` and stdin reads ``input``; each is restored afterwards. An
    exception ``main`` does not handle is reported as a child's would be: its traceback on stderr
    and status 1 (an unreadable registry in the orchestration snapshot tests, a failed pickup's
    self-heal). ``stderr_to_stdout`` interleaves both streams in ``stdout``, as
    ``stderr=subprocess.STDOUT`` does; ``stderr`` is then ``None``.
    """
    module = CONSOLE_SCRIPTS.get(argv[0]) or f"specy_road.bundled_scripts.{Path(argv[0]).stem}"
    main = importlib.import_module(module).main
    state = _process_state(argv, cwd, env, input)
    with state, _captured_fds(stderr_to_stdout) as output:
        try:
            main()
            status = 0
        except SystemExit as e:
            status = cli.exit_status(e)
        except Exception:   # what a child's pipe captured when it crashed: its traceback, status 1
            traceback.print_exc()
            status = 1
        sys.stdout.flush()
        sys.stderr.flush()
    return subprocess.CompletedProcess(argv, status, *output)


@contextlib.contextmanager
def _process_state(
    argv: list[str], cwd: Path | None, env: dict[str, str] | None, stdin: str | None
) -> Iterator[None]:
    """``sys.argv``, the working directory, ``os.environ`` and stdin as a child would have them."""
    saved = sys.argv, os.getcwd(), dict(os.environ), sys.stdin
    sys.argv = list(argv)
    sys.stdin = io.StringIO(stdin or "")
    if cwd is not None:
        os.chdir(cwd)
    if env is not None:
        os.environ.clear()
        os.environ.update(env)
    try:
        yield
    finally:
        sys.argv, sys.stdin = saved[0], saved[3]
        os.chdir(saved[1])
        if os.environ != saved[2]:
            os.environ.clear()
            os.environ.update(saved[2])


@contextlib.contextmanager
def _captured_fds(merged: bool) -> Iterator[list[str | None]]:
    """Descriptors 1 and 2, and sys.stdout and sys.stderr on them, written to temp files.

    The yielded list holds what was written to each, stdout then stderr, once the block ends;
    ``merged`` writes both to the first file and leaves stderr ``None``.
    """
    output: list[str | None] = []
    sys.stdout.flush()
    sys.stderr.flush()
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        files = (out, out if merged else err)
        saved = os.dup(1), os.dup(2)
        os.dup2(files[0].fileno(), 1)
        os.dup2(files[1].fileno(), 2)
        try:
            with contextlib.ExitStack() as writers:
                py_out, py_err = (
                    writers.enter_context(
                        open(f.fileno(), "w", buffering=1, encoding="utf-8", closefd=False)
                    )
                    for f in files
                )
                with contextlib.redirect_stdout(py_out), contextlib.redirect_stderr(py_err):
                    yield output
        finally:
            os.dup2(saved[0], 1)
            os.dup2(saved[1], 2)
            os.close(saved[0])
            os.close(saved[1])
            output.extend((_read(out), None if merged else _read(err)))


def _read(f: IO[bytes]) -> str:
    f.seek(0)
    return f.read().decode("utf-8", errors="replace")


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
