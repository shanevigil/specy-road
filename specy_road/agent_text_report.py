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

    Sentences are read whole across wrapped lines; several sentences or entries starting on one
    line are combined, so each line gets at most one result.
    """
    found: dict[int, tuple[list[str], list]] = {}
    for para in _paragraphs(lines):
        for lineno, sentence in _sentence_starts(para):
            entries = [e for e in CATALOGUE if e.contradicted_by(sentence)]
            if entries:
                said, hit = found.setdefault(lineno, ([], []))
                said.append(sentence)
                hit.extend(e for e in entries if e not in hit)
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
