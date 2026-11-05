"""Which harness binary a launch runs (M15.9 A3): the roster entry's ``harness_bin``, else ``PATH``, else the
harness's documented install directories, which a non-interactive shell's ``PATH`` often lacks.

Not found is a refusal (:class:`HarnessNotFound`) naming the directories searched and ``harness_bin``, never the
shell's exit 127. See ``docs/orchestration-harness-launch.md``.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from specy_road.worker_adapter_base import PROGRAMS, Unsupported

#: Where each harness's own installer puts its binary: Cursor's agent CLI and Claude Code's native installer use
#: ``~/.local/bin``; Claude Code's older local install ``~/.claude/local``.
INSTALL_DIRS = {"claude-code": ("~/.local/bin", "~/.claude/local"), "codex": ("~/.local/bin",),
                "cursor": ("~/.local/bin",)}


class HarnessNotFound(Unsupported):
    """No runnable harness binary: the message names what was searched."""


def resolve(harness: str, harness_bin: str | None = None) -> str:
    """The absolute path of ``harness``'s binary: ``harness_bin`` when set (a path, or a name looked up on
    ``PATH``), else ``PATH``, else :data:`INSTALL_DIRS`."""
    program = PROGRAMS[harness]
    if harness_bin:
        found = shutil.which(os.path.expanduser(harness_bin))
        if found:
            return os.path.abspath(found)
        raise HarnessNotFound(f"{harness}: the roster's harness_bin {harness_bin!r} is not an executable file; "
                              "fix harness_bin or remove it to search PATH")
    dirs = [os.path.expanduser(d) for d in INSTALL_DIRS[harness]]
    found = shutil.which(program) or shutil.which(program, path=os.pathsep.join(dirs))
    if found:
        return os.path.abspath(found)
    raise HarnessNotFound(f"{harness}: `{program}` is not on PATH or in {', '.join(dirs)}; install it, or set the "
                          f"roster entry's harness_bin to its path")


def entry_binary(harness: str, entry: dict[str, Any], *, default: bool = True) -> str | None:
    """The resolved binary roster ``entry``'s default command runs (:func:`resolve` with its ``harness_bin``);
    ``None`` for a custom command (``default`` false), which runs as written, or a ``generic`` harness."""
    if not default or harness not in PROGRAMS:
        return None
    return resolve(harness, entry.get("harness_bin"))
