"""Markdown section parsing, shared by the brief and the search index.

specy-road's own documents are written as flat ``##`` sections — planning
sheets, gate sheets, implementation summaries and generated briefs all follow
that shape. A section is therefore the natural unit for both jobs this module
serves: pulling one named block out of a sheet (the brief's dependency context),
and cutting a document into indexable chunks (the search corpus).

The parser was previously inlined in ``brief_dependency_context`` and is lifted
here unchanged, so brief output is byte-identical across the move.

Heading matching is deliberately forgiving: case-insensitive, tolerant of
internal whitespace and of a trailing colon (``## Intent:``). Sheets are
hand-written, and a stricter parser would silently drop real content.
"""

from __future__ import annotations

import re
from pathlib import Path

# A level-2 ATX heading. The trailing ``:?`` lets "## Intent:" match "Intent".
LEVEL2_RE = re.compile(r"^\s*##\s+(?P<title>.+?)\s*:?\s*$")


def normalize_heading(raw: str) -> str:
    """Lowercase, collapse internal whitespace, strip a trailing colon."""
    s = " ".join(raw.strip().lower().split())
    if s.endswith(":"):
        s = s[:-1].rstrip()
    return s


def _trim_blank_edges(lines: list[str]) -> list[str]:
    """Drop leading and trailing blank lines, preserving inner structure."""
    out = list(lines)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return out


def split_sections(text: str) -> list[tuple[str | None, str]]:
    """Cut ``text`` into ``(heading, body)`` pairs, in document order.

    Any content before the first ``##`` is returned first with a ``None``
    heading, and is omitted entirely when blank. Bodies have their blank edges
    trimmed but are otherwise verbatim, and may be empty for a heading with no
    content under it — callers decide whether an empty section is interesting.

    Deeper headings (``###`` and below) stay inside their parent section rather
    than starting a new one: a planning sheet's ``### Tasks (if any)`` belongs
    with the ``## Resolution`` it sits under.
    """
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = "\n".join(_trim_blank_edges(buffer))
        if heading is not None or body:
            sections.append((heading, body))

    for line in text.splitlines():
        match = LEVEL2_RE.match(line)
        if match is None:
            buffer.append(line)
            continue
        flush()
        heading = match.group("title").strip()
        buffer = []
    flush()
    return sections


def find_section(text: str, wanted: set[str]) -> str | None:
    """Body of the first section whose heading normalises into ``wanted``.

    ``None`` when no heading matches *and* when the matched section is empty —
    an empty block carries no more information than a missing one, and callers
    render the same fallback for both.
    """
    if not text or not wanted:
        return None
    for heading, body in split_sections(text):
        if heading is None:
            continue
        if normalize_heading(heading) in wanted:
            return body or None
    return None


def read_text_safely(path: Path) -> tuple[str, bool]:
    """``(text, ok)`` for a file that may be missing or undecodable.

    Never raises. A brief must still render when a planning sheet has been
    deleted, and the search index must skip an unreadable file rather than
    abandon the whole corpus.
    """
    if not path.is_file():
        return "", False
    try:
        return path.read_text(encoding="utf-8"), True
    except (OSError, UnicodeDecodeError):
        return "", False
