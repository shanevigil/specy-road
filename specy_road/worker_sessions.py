"""Native session ids and the command lines that carry them (review round 6, B13).

A session id reaches specy-road from the harness's own output (the model can
shape it) or from ``worker adopt`` (the user types it), and it ends up in a
command a human is told to run. Two rules keep that honest: an id is checked
against the vendor's syntax before it is stored by ``adopt`` and for shell
safety before any command is built from it, and a command line shown to a
human is rendered with :func:`shlex.join` (``list2cmdline`` on Windows), never
``" ".join``.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess

from specy_road.worker_lock import WorkerError

#: Letters, digits and ``._:-``, never whitespace or a shell metacharacter.
#: Every harness's id fits; a Cursor chat id is not pinned to one shape.
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
#: The vendor syntax ``adopt`` insists on: Claude Code and Codex ids are UUIDs.
_VENDOR = {"claude-code": (_UUID, "a UUID (Claude Code session id)"),
           "codex": (_UUID, "a UUID (Codex thread id)")}


def session_id_problem(harness: str, session_id: str | None, *, vendor_syntax: bool = False) -> str | None:
    """Why ``session_id`` may not be used for ``harness``, or ``None``.

    Always: shell-safe characters only. With ``vendor_syntax`` (``adopt``,
    where the id is typed in): the vendor's documented shape as well.
    """
    if not session_id:
        return "empty session id"
    if not _SAFE.match(session_id):
        return (f"session id {session_id!r} has whitespace or shell metacharacters; "
                "expected letters, digits, '.', '_', ':' or '-'")
    if vendor_syntax and harness in _VENDOR:
        pattern, what = _VENDOR[harness]
        if not pattern.match(session_id):
            return f"session id {session_id!r} is not {what}"
    return None


def check_session_id(harness: str, session_id: str | None, *, vendor_syntax: bool = False) -> str:
    """``session_id`` when it passes :func:`session_id_problem`; :class:`WorkerError` otherwise."""
    why = session_id_problem(harness, session_id, vendor_syntax=vendor_syntax)
    if why:
        raise WorkerError(f"{harness}: {why}")
    return str(session_id)


def render_command(argv: list[str]) -> str:
    """``argv`` as one line a human can paste into their shell, every argument quoted for it."""
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)
