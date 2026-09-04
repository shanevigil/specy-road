"""Maintain a delimited block inside a file specy-road does not own.

``init project`` copies whole template files and skips anything that already
exists, which is right for scaffolding but useless for ``.gitignore`` and
``.cursorindexingignore``: those belong to the consumer, already have content,
and need one specy-road-managed section kept up to date inside them.

A marked block is the standard answer. Everything between the markers is ours to
rewrite; everything outside is never touched. Rewriting in place also means an
entry we later stop recommending actually disappears, which an append-only
helper could never do.

Idempotent by construction: applying the same lines twice is a no-op, so
``specyrd init`` can be re-run freely.
"""

from __future__ import annotations

from pathlib import Path

MARKER_START = "# >>> specy-road managed block — do not edit inside <<<"
MARKER_END = "# >>> end specy-road managed block <<<"

CREATED = "created"
UPDATED = "updated"
UNCHANGED = "unchanged"
FAILED = "failed"


def render_block(lines: list[str], *, note: str = "") -> str:
    """The managed block itself, markers included, ending in a newline."""
    body = [MARKER_START]
    if note:
        body += [f"# {ln}".rstrip() for ln in note.splitlines()]
    body += list(lines)
    body.append(MARKER_END)
    return "\n".join(body) + "\n"


def _split(text: str) -> tuple[str, str | None, str]:
    """``(before, block, after)`` — ``block`` is ``None`` when absent."""
    start = text.find(MARKER_START)
    if start < 0:
        return text, None, ""
    end = text.find(MARKER_END, start)
    if end < 0:
        # A truncated block (hand-edited, or a half-written file): treat
        # everything from the start marker on as ours to replace.
        return text[:start], text[start:], ""
    stop = end + len(MARKER_END)
    return text[:start], text[start:stop], text[stop:].lstrip("\n")


def apply_managed_block(path: Path, lines: list[str], *, note: str = "") -> str:
    """Write ``lines`` into ``path``'s managed block. Returns what happened.

    Creates the file when missing, replaces the block when present, and leaves
    every other line exactly as it was. Never raises: an unwritable path costs
    the block, not the command that asked for it.
    """
    block = render_block(lines, note=note)
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else None
    except (OSError, UnicodeDecodeError):
        return FAILED

    if existing is None:
        return _write(path, block, CREATED)

    before, current, after = _split(existing)
    if current is not None and current + "\n" == block:
        return UNCHANGED
    if current is None:
        prefix = before if before.endswith("\n") or not before else before + "\n"
        joiner = "\n" if prefix.strip() else ""
        return _write(path, f"{prefix}{joiner}{block}", UPDATED)
    tail = f"\n{after}" if after.strip() else ""
    return _write(path, f"{before}{block}{tail}", UPDATED)


def _write(path: Path, text: str, outcome: str) -> str:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError:
        return FAILED
    return outcome


def remove_managed_block(path: Path) -> str:
    """Drop the block, leaving the rest of the file alone."""
    try:
        if not path.is_file():
            return UNCHANGED
        existing = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return FAILED
    before, current, after = _split(existing)
    if current is None:
        return UNCHANGED
    rest = (before.rstrip("\n") + "\n" + after).lstrip("\n") if after.strip() else before
    return _write(path, rest, UPDATED)
