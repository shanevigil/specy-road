"""Maintain a delimited block inside a file specy-road does not own.

``init project`` copies whole template files and skips anything that already
exists, which is right for scaffolding but useless for ``.gitignore``,
``.cursorindexingignore`` and ``CLAUDE.md``: those belong to the consumer,
already have content, and need one specy-road-managed section kept up to date
inside them.

A marked block is the standard answer. Everything between the markers is ours to
rewrite; everything outside is never touched. Rewriting in place also means an
entry we later stop recommending actually disappears, which an append-only
helper could never do.

Idempotent by construction: applying the same lines twice is a no-op, so
``specyrd init`` can be re-run freely.

**Two comment syntaxes, because two file formats.** ``#`` markers are invisible
in an ignore file and an H1 heading in Markdown, which is why the agent-guide
block uses :data:`HTML_COMMENT` instead. :data:`HASH` stays the default so the
ignore files keep their existing bytes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_LABEL = "specy-road managed block — do not edit inside"
_END_LABEL = "end specy-road managed block"


@dataclass(frozen=True)
class MarkerStyle:
    """How a block's markers and note lines are commented in one file format."""

    start: str
    end: str
    comment_prefix: str
    comment_suffix: str = ""

    def comment(self, line: str) -> str:
        """``line`` as a comment, with no trailing whitespace on a blank line."""
        if not self.comment_suffix:
            return f"{self.comment_prefix}{line}".rstrip()
        if not line.strip():
            return f"{self.comment_prefix.rstrip()}{self.comment_suffix}"
        return f"{self.comment_prefix}{line}{self.comment_suffix}"


#: ``.gitignore``, ``.cursorindexingignore`` — anything with ``#`` line comments.
HASH = MarkerStyle(
    start=f"# >>> {_LABEL} <<<",
    end=f"# >>> {_END_LABEL} <<<",
    comment_prefix="# ",
)

#: Markdown (``CLAUDE.md``, ``AGENTS.md``) — a ``#`` marker would be a heading.
HTML_COMMENT = MarkerStyle(
    start=f"<!-- >>> {_LABEL} <<< -->",
    end=f"<!-- >>> {_END_LABEL} <<< -->",
    comment_prefix="<!-- ",
    comment_suffix=" -->",
)

# Kept as module constants: the ignore-file markers are the original contract.
MARKER_START = HASH.start
MARKER_END = HASH.end

CREATED = "created"
UPDATED = "updated"
UNCHANGED = "unchanged"
FAILED = "failed"


def render_block(
    lines: list[str], *, note: str = "", style: MarkerStyle = HASH
) -> str:
    """The managed block itself, markers included, ending in a newline."""
    body = [style.start]
    if note:
        body += [style.comment(ln) for ln in note.splitlines()]
    body += list(lines)
    body.append(style.end)
    return "\n".join(body) + "\n"


def _split(text: str, style: MarkerStyle) -> tuple[str, str | None, str]:
    """``(before, block, after)`` — ``block`` is ``None`` when absent."""
    start = text.find(style.start)
    if start < 0:
        return text, None, ""
    end = text.find(style.end, start)
    if end < 0:
        # A truncated block (hand-edited, or a half-written file): treat
        # everything from the start marker on as ours to replace.
        return text[:start], text[start:], ""
    stop = end + len(style.end)
    return text[:start], text[start:stop], text[stop:].lstrip("\n")


def apply_managed_block(
    path: Path,
    lines: list[str],
    *,
    note: str = "",
    style: MarkerStyle = HASH,
    dry_run: bool = False,
) -> str:
    """Write ``lines`` into ``path``'s managed block. Returns what happened.

    Creates the file when missing, replaces the block when present, and leaves
    every other line exactly as it was. Never raises: an unwritable path costs
    the block, not the command that asked for it.

    With ``dry_run`` the outcome is computed and nothing is written, so
    ``specyrd init --dry-run`` can report the same line it would report for
    real.
    """
    block = render_block(lines, note=note, style=style)
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeDecodeError):
        return FAILED

    if existing is None:
        return _write(path, block, CREATED, dry_run)

    before, current, after = _split(existing, style)
    if current is not None and current + "\n" == block:
        return UNCHANGED
    if current is None:
        prefix = before if before.endswith("\n") or not before else before + "\n"
        joiner = "\n" if prefix.strip() else ""
        return _write(path, f"{prefix}{joiner}{block}", UPDATED, dry_run)
    tail = f"\n{after}" if after.strip() else ""
    return _write(path, f"{before}{block}{tail}", UPDATED, dry_run)


def _write(path: Path, text: str, outcome: str, dry_run: bool = False) -> str:
    if dry_run:
        return outcome
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        return FAILED
    return outcome


def remove_managed_block(path: Path, *, style: MarkerStyle = HASH) -> str:
    """Drop the block, leaving the rest of the file alone."""
    try:
        if not path.is_file():
            return UNCHANGED
        existing = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return FAILED
    before, current, after = _split(existing, style)
    if current is None:
        return UNCHANGED
    rest = (before.rstrip("\n") + "\n" + after).lstrip("\n") if after.strip() else before
    return _write(path, rest, UPDATED)
