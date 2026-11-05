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
    tail = _tail(stdout or "")
    out: dict[str, Any] = {"cmd": cmd, "exit": returncode, "tail": tail or "(no output)"}
    if returncode == 0 and (warn := tail_warning(tail)):
        out["warning"] = warn
    return out


def run_check(cmd: str) -> dict[str, Any]:
    """Run ``cmd`` in a shell from the current directory, as the executor would."""
    r = subprocess.run(cmd, shell=True, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, errors="replace", check=False)
    return _finish(cmd, r.returncode, r.stdout or "")


def run_argv(argv: list[str]) -> dict[str, Any]:
    """Run ``argv`` without a shell; ``cmd`` in the result is ``shlex.join(argv)``."""
    r = subprocess.run(argv, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, errors="replace", check=False)
    return _finish(shlex.join(argv), r.returncode, r.stdout or "")


def parse_run_argv(spec: str) -> list[str]:
    """``spec`` is a JSON array of non-empty strings; refused before any run when invalid."""
    try:
        parsed = json.loads(spec)
    except json.JSONDecodeError as e:
        raise ValueError(f"{spec!r}: not valid JSON ({e})") from e
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f"{spec!r}: expected a non-empty JSON array of strings")
    if not all(isinstance(x, str) and x for x in parsed):
        raise ValueError(f"{spec!r}: expected a non-empty JSON array of strings")
    return parsed
