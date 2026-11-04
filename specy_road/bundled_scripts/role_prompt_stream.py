"""Run a reviewer or CLI-channel command and keep its output (split from ``role_prompt`` for the file limit)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def stream_and_capture(cmd, *, cwd: Path, transcript: list[str], stdin: str | None = None,
                        shell: bool = False, env: dict[str, str] | None = None) -> int:
    """Run ``cmd`` to its end, writing each line to stderr and ``transcript`` as it arrives."""
    proc = subprocess.Popen(
        cmd, cwd=cwd, shell=shell, env=env, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
    )
    if stdin is not None and proc.stdin:
        try:
            proc.stdin.write(stdin)
            proc.stdin.close()
        except OSError as e:   # the harness quit before reading its prompt
            sys.stderr.write(f"harness closed stdin early: {e}\n")
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stderr.write(line)
        transcript.append(line.rstrip("\n"))
    return proc.wait()
