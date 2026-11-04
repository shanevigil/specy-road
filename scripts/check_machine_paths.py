#!/usr/bin/env python3
"""Fail when a tracked file names one person's machine: a home directory, a harness temp dir, a hostname.

Paths are resolved at run time (repo-relative, ``git rev-parse``, environment
variables), never written in. Flagged: ``/Users/<name>/`` and ``/home/<name>/``
(and the ``-Users-<name>`` form Claude Code uses for project directories),
``C:\\Users\\<name>\\``, ``/tmp/claude-<uid>`` and ``/private/tmp/claude-<uid>``, and
``<host>-MacBook`` hostnames. Deliberate placeholders pass: the name ``x``
(``/Users/x/``) and an angle-bracketed name (``/home/<name>/``).

Usage: ``python scripts/check_machine_paths.py [--root DIR]``
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PATTERN = re.compile(
    r"/(?:Users|home)/(?!x/|<)[^/\s`'\"]+/"
    r"|-Users-(?!x-)[A-Za-z0-9]"
    r"|[A-Za-z]:\\Users\\(?!<)"
    r"|/(?:private/)?tmp/claude-\d"
    r"|[A-Za-z0-9]-MacBook"
)


def find_machine_paths(root: Path) -> list[str]:
    """``<file>:<line>: <text>`` for every tracked text line that matches."""
    names = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
    hits = []
    for name in filter(None, names.decode().split("\0")):
        try:
            text = (root / name).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue   # binary
        hits += [f"{name}:{n}: {line.strip()[:160]}" for n, line in enumerate(text.splitlines(), 1)
                 if PATTERN.search(line)]
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    hits = find_machine_paths(parser.parse_args(argv).root)
    for hit in hits:
        print(hit)
    if hits:
        print(f"{len(hits)} machine-specific path(s) or identifier(s) in tracked files; resolve them at run time.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
