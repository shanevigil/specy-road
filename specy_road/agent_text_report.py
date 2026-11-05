"""Report project agent text that a shipped behaviour change contradicts.

Reads the agent files ``validate`` checks (root ``AGENTS.md``, ``CLAUDE.md``
and ``.specyrd/AGENTS.team.md``) outside their managed blocks and prints one
notice per line that matches a :data:`~specy_road.behaviour_changes.CATALOGUE`
pattern. Report only: those files are the developer's, so nothing is rewritten.
"""

from __future__ import annotations

import re
from pathlib import Path

from specy_road.behaviour_changes import CATALOGUE
from specy_road.bundled_scripts.validate_stale_commands import agent_files
from specy_road.managed_block import agent_file_lines_outside_block
from specy_road.runtime_paths import git_root

_EXCERPT = 120


_SENTENCE_END = re.compile(r"(?<![0-9])[.!?](?=\s+[^\s])")
_BLOCK_START = re.compile(r"^\s*(?:[-*+>|#]|\d+[.)])\s?")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_DIRECTIVE = re.compile(r"\b(?:Run\s+)?specy-road\b|^Run\s+[a-z]", re.IGNORECASE)


def _is_directive_line(line: str) -> bool:
    return bool(_DIRECTIVE.search(line.strip()))


def _record(found: dict[int, tuple[list[str], list]], lineno: int, text: str, entries: list) -> None:
    if not entries:
        return
    said, hit = found.setdefault(lineno, ([], []))
    if text not in said:
        said.append(text)
    hit.extend(e for e in entries if e not in hit)


def sentences(line: str) -> list[str]:
    """``line`` split after each ``.``, ``!`` or ``?`` followed by more text (not after a list number like ``4.``)."""
    return [part for part in _SENTENCE_END.split(line) if part.strip()]


def _paragraphs(lines: list[tuple[int, str]]):
    """``[(line number, text), ...]`` per Markdown paragraph, so a sentence wrapped over lines is read whole.

    A blank line, a gap in numbering (a stripped managed block), a list item, quote, table row or
    heading starts a new paragraph; each line inside a code fence is its own paragraph.
    """
    para: list[tuple[int, str]] = []
    fenced = False
    prev = None
    for lineno, line in lines:
        if _FENCE.match(line):
            if para:
                yield para
                para = []
            fenced = not fenced
            prev = lineno
            continue
        if para and (not line.strip() or _BLOCK_START.match(line) or (not fenced and lineno != prev + 1)):
            yield para
            para = []
        if line.strip():
            para.append((lineno, line.strip()))
        prev = lineno
    if para:
        yield para


def _sentence_starts(para: list[tuple[int, str]]):
    """``(line number where it starts, sentence)`` per sentence of one paragraph."""
    text, starts = "", []
    for lineno, line in para:
        starts.append((len(text), lineno))
        text += line + " "
    pos = 0
    for part in _SENTENCE_END.split(text):
        offset = text.index(part, pos)
        pos = offset + len(part)
        if part.strip():
            yield max(n for start, n in starts if start <= offset + len(part) - len(part.lstrip())), part.strip()


def contradicted_lines(lines: list[tuple[int, str]]):
    """``(line number, sentence, entries)`` per source line on which a reported sentence starts.

    Wrapped sentences are read whole across lines. Adjacent directive lines each get their own
    notice when both match independently.
    """
    found: dict[int, tuple[list[str], list]] = {}
    for para in _paragraphs(lines):
        directive_hits = [
            (lineno, line)
            for lineno, line in para
            if _is_directive_line(line) and any(e.contradicted_by(line) for e in CATALOGUE)
        ]
        if len(directive_hits) >= 2:
            for lineno, line in directive_hits:
                entries = [e for e in CATALOGUE if e.contradicted_by(line)]
                _record(found, lineno, line, entries)
            continue
        if len(para) == 1:
            lineno, line = para[0]
            entries = [e for e in CATALOGUE if e.contradicted_by(line)]
            _record(found, lineno, line, entries)
            continue
        for lineno, sentence in _sentence_starts(para):
            entries = [e for e in CATALOGUE if e.contradicted_by(sentence)]
            _record(found, lineno, sentence, entries)
    for lineno, (said, hit) in sorted(found.items()):
        yield lineno, " ".join(said), tuple(hit)


def warn_contradicted_instructions(project_root: Path) -> None:
    """One ``agents: notice`` line on stdout per contradicting source line, naming file:line."""
    root = project_root.resolve()
    checkout = git_root(root) or root
    for path in agent_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(checkout)
        for lineno, line, entries in contradicted_lines(agent_file_lines_outside_block(text)):
            excerpt = line.strip()
            if len(excerpt) > _EXCERPT:
                excerpt = excerpt[: _EXCERPT - 1] + "…"
            now = "; ".join(f"since {e.since}: {e.now}" for e in entries)
            print(f'agents: notice — {rel}:{lineno}: says "{excerpt}"; {now}')
