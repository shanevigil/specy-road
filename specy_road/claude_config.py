"""Where Claude Code keeps its per-account data."""

from __future__ import annotations

import os
from pathlib import Path


def claude_projects_dir(home: Path | None = None) -> Path:
    """Claude Code's transcript root: ``$CLAUDE_CONFIG_DIR/projects``, else ``~/.claude/projects``.

    ``CLAUDE_CONFIG_DIR`` selects the account, and each account has its own
    transcripts and memory. An explicit ``home`` names the root directly, so it
    ignores the variable.
    """
    configured = os.environ.get("CLAUDE_CONFIG_DIR") if home is None else None
    if configured:
        return Path(configured).expanduser() / "projects"
    return (home or Path.home()) / ".claude" / "projects"
