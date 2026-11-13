"""The one report ``specy-road upgrade`` prints of what its refreshes changed for the repo.

The refresh steps add the lines they already compute; nothing here detects anything. The report
has four fixed sections, printed in this order whether or not a section has lines, so a reader
(or a script) finds the same headings on every run.
"""

from __future__ import annotations

import contextlib
import io
from collections.abc import Iterator

FILES = "files added or changed"
SCHEMAS = "schema refreshes"
PROFILES = "profile refreshes"
NOTICES = "notices"
SECTIONS = (FILES, SCHEMAS, PROFILES, NOTICES)


class Report:
    """Lines grouped by section, printed once by :meth:`print`."""

    def __init__(self) -> None:
        self.lines: dict[str, list[str]] = {name: [] for name in SECTIONS}

    def add(self, section: str, line: str) -> None:
        """Add one line (it may hold newlines) to ``section``."""
        self.lines[section].append(line)

    @contextlib.contextmanager
    def capture(self, section: str) -> Iterator[None]:
        """Add what a step prints on stdout while the block runs to ``section``, as printed."""
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                yield
        finally:
            text = buf.getvalue().rstrip("\n")
            if text:
                self.add(section, text)

    def print(self) -> None:
        """Print the four sections, each under a ``== <name>`` heading."""
        for name in SECTIONS:
            print(f"\n== {name}", flush=True)
            for line in self.lines[name]:
                print(line)
