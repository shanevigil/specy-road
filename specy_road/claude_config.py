"""Where Claude Code keeps its per-account data."""

from __future__ import annotations

import os
from pathlib import Path


def claude_config_dir(home: Path | None = None) -> Path:
    """Claude Code's user config root: ``$CLAUDE_CONFIG_DIR``, else ``~/.claude``.

    ``CLAUDE_CONFIG_DIR`` selects the account, and each account has its own
    ``CLAUDE.md``, transcripts and memory. Its value is taken literally, as the
    shell wrappers' ``${CLAUDE_CONFIG_DIR:-$HOME/.claude}`` does: a ``~`` in it
    is not expanded. ``home`` stands in for the home directory (a fake ``HOME``,
    not a config-dir override), and when given the variable is ignored.
    """
    configured = os.environ.get("CLAUDE_CONFIG_DIR") if home is None else None
    if configured:
        return Path(configured)
    return (home or Path.home()) / ".claude"


def claude_projects_dir(home: Path | None = None) -> Path:
    """Claude Code's transcript root: ``<config dir>/projects`` (see :func:`claude_config_dir`)."""
    return claude_config_dir(home) / "projects"
