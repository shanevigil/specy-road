"""Report project agent text that a shipped behaviour change contradicts.

Reads the agent files ``validate`` checks (root ``AGENTS.md``, ``CLAUDE.md``
and ``.specyrd/AGENTS.team.md``) outside their managed blocks and prints one
notice per line that matches a :data:`~specy_road.behaviour_changes.CATALOGUE`
pattern. Report only: those files are the developer's, so nothing is rewritten.
"""

from __future__ import annotations

from pathlib import Path

from specy_road.behaviour_changes import CATALOGUE
from specy_road.bundled_scripts.validate_stale_commands import agent_files
from specy_road.managed_block import agent_file_lines_outside_block
from specy_road.runtime_paths import git_root

_EXCERPT = 120


def contradicted_lines(lines: list[tuple[int, str]]):
    """``(line number, line, entry)`` per numbered line a catalogue pattern matches."""
    for lineno, line in lines:
        for entry in CATALOGUE:
            if entry.contradicts is not None and entry.contradicts.search(line):
                yield lineno, line, entry


def warn_contradicted_instructions(project_root: Path) -> None:
    """One ``agents: notice`` line on stdout per contradicted instruction, naming file:line."""
    root = project_root.resolve()
    checkout = git_root(root) or root
    for path in agent_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(checkout)
        for lineno, line, entry in contradicted_lines(agent_file_lines_outside_block(text)):
            excerpt = line.strip()
            if len(excerpt) > _EXCERPT:
                excerpt = excerpt[: _EXCERPT - 1] + "…"
            print(f'agents: notice — {rel}:{lineno}: says "{excerpt}"; since {entry.since}: {entry.now}')
