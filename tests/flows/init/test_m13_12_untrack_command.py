"""M13.12 A3: every command the ignore note prints is a line of its own that a shell parses back to its argv.

Paths with spaces, quotes and parentheses are quoted; when more tracked files
match than the note lists, the overflow note is its own line, never part of the command.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from specy_road.agent_ignores import MATCH_LIMIT, apply_and_report
from specy_road.ignore_report import UNTRACK_HINT, UNTRACK_LABEL
from tests.m13_7_ignore_helpers import git, write

ODD = ["work/prompt-a b.md", "work/prompt-it's.md", 'work/prompt-"q".md', "work/prompt-(x).md", "work/prompt-$HOME;.md"]


def tracked_prompts(repo: Path, names: list[str]) -> Path:
    git(repo, "init", "-q")
    for rel in names:
        write(repo, rel)
    git(repo, "add", "--", *names)
    git(repo, "commit", "-qm", "tracked prompts")
    return repo


def commands(out: list[str]) -> list[list[str]]:
    """Each printed command line (four-space indent) parsed as a shell would."""
    return [shlex.split(ln) for ln in out if ln.startswith("    ")]


def test_odd_paths_round_trip_through_the_shell(tmp_path: Path, capsys) -> None:
    repo = tracked_prompts(tmp_path, ODD)
    apply_and_report(repo, "", [])
    out = capsys.readouterr().out.splitlines()
    assert commands(out) == [["git", "rm", "--cached", "--", *sorted(ODD)]]
    assert out[-3] == UNTRACK_LABEL and out[-1] == UNTRACK_HINT


def test_more_tracked_matches_than_listed_put_the_overflow_on_its_own_line(tmp_path: Path, capsys) -> None:
    names = [f"work/prompt-{i:02d} (copy).md" for i in range(MATCH_LIMIT + 1)]
    repo = tracked_prompts(tmp_path, names)
    apply_and_report(repo, "", [])
    out = capsys.readouterr().out.splitlines()
    assert commands(out) == [
        ["git", "rm", "--cached", "--", *sorted(names)[:MATCH_LIMIT]],
        ["git", "ls-files", "-ci", "--exclude-standard"],
    ]
    assert "  1 more tracked file(s) match a new rule; this lists every tracked file git ignores:" in out
    assert out[-1] == UNTRACK_HINT
