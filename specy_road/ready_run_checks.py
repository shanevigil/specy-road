"""Run verifiers for ``specy-road ready``: shell and argv execution, tail capture, failure markers."""

from __future__ import annotations

import json
import shlex
import subprocess
from typing import Any

#: Substrings in a recorded tail that suggest a command failed though the process exited 0.
FAILURE_MARKERS = (
    "cannot open",
    "command not found",
    "No such file or directory",
    "Permission denied",
)

#: How many lines of a run command's output the READY keeps as its ``tail``.
READY_TAIL_LINES = 20


def tail_warning(tail: str) -> str | None:
    """The first tail line containing a :data:`FAILURE_MARKERS` entry, if any."""
    for line in tail.splitlines():
        if any(m in line for m in FAILURE_MARKERS):
            return line
    return None


def _tail(stdout: str) -> str:
    return "\n".join(stdout.rstrip().splitlines()[-READY_TAIL_LINES:])


def _finish(cmd: str, returncode: int, stdout: str) -> dict[str, Any]:
    tail = _tail(stdout)
    out: dict[str, Any] = {"cmd": cmd, "exit": returncode, "tail": tail or "(no output)"}
    if returncode == 0 and (warn := tail_warning(tail)):
        out["warning"] = warn
    return out


def _launch_failure_exit(err: BaseException) -> int:
    if isinstance(err, FileNotFoundError):
        return 127
    if isinstance(err, OSError):
        return 126
    return 126


def _subprocess_output(*, shell: bool, cmd: str | None = None, argv: list[str] | None = None) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd if shell else argv, shell=shell, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors="replace", check=False)
        return r.returncode, r.stdout or ""
    except Exception as e:
        return _launch_failure_exit(e), str(e)


def run_check(cmd: str) -> dict[str, Any]:
    """Run ``cmd`` in a shell from the current directory, as the executor would.

    Returns ``{cmd, exit, tail}``; on exit 0, may add ``warning`` when the tail matches :data:`FAILURE_MARKERS`.
    Any exception while starting the process becomes exit 126 or 127 with the error text in ``tail``.
    """
    code, out = _subprocess_output(shell=True, cmd=cmd)
    return _finish(cmd, code, out)


def run_argv(argv: list[str]) -> dict[str, Any]:
    """Run ``argv`` without a shell; ``cmd`` in the result is ``shlex.join(argv)``.

    Returns ``{cmd, exit, tail}``; on exit 0, may add ``warning`` when the tail matches :data:`FAILURE_MARKERS`.
    Any exception while starting the process becomes exit 126 or 127 with the error text in ``tail``.
    """
    cmd = shlex.join(argv)
    code, out = _subprocess_output(shell=False, argv=argv)
    return _finish(cmd, code, out)


def parse_run_argv(spec: str) -> list[str]:
    """JSON array of strings with at least one element; the first must be non-empty (later elements may be empty).

    No element may contain an embedded NUL (``\\0``); the OS cannot pass that in argv.
    """
    try:
        parsed = json.loads(spec)
    except json.JSONDecodeError as e:
        raise ValueError(f"{spec!r}: not valid JSON ({e})") from e
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f"{spec!r}: expected a non-empty JSON array of strings")
    if not all(isinstance(x, str) for x in parsed):
        raise ValueError(f"{spec!r}: expected a non-empty JSON array of strings")
    if not parsed[0]:
        raise ValueError(f"{spec!r}: the first element must be a non-empty string")
    for i, x in enumerate(parsed):
        if "\0" in x:
            raise ValueError(f"{spec!r}: argv[{i}] contains an embedded NUL character")
    return parsed


def prepare_live_runs(raw_runs: list[str], run_argv_specs: list[str]) -> tuple[list[str], list[list[str]], str | None]:
    """Validate every ``--run`` and ``--run-argv`` before any verifier executes; return a refusal message or None."""
    for raw in raw_runs:
        if not raw.strip():
            return [], [], f"--run {raw!r} is blank or whitespace-only"
        if "\0" in raw:
            return [], [], f"--run {raw!r} contains an embedded NUL character"
    runs = [c.strip() for c in raw_runs]
    argv_runs: list[list[str]] = []
    for spec in run_argv_specs:
        try:
            argv_runs.append(parse_run_argv(spec))
        except ValueError as e:
            return runs, [], str(e)
    return runs, argv_runs, None
