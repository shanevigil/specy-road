"""Close a finished brainstorm: move its files to ``work/brainstorm-closed/``.

A session has no closed state inside the file; ``list_slugs`` simply globs
``work/brainstorm-*.yaml``, so a finished session kept counting as open and
forced ``--slug`` on every later command. Moving it one directory down takes it
out of that glob while keeping the tracked record of what was considered.
"""

from __future__ import annotations

import re
from pathlib import Path

from specy_road.bundled_scripts.brainstorm_session import (
    PROMPT_SUFFIX,
    SESSION_PREFIX,
    BrainstormError,
    list_slugs,
    session_path,
    validate_slug,
    work_dir,
)

CLOSED_DIRNAME = "brainstorm-closed"


def closed_dir(root: Path) -> Path:
    return work_dir(root) / CLOSED_DIRNAME


def session_files(root: Path, slug: str) -> list[Path]:
    """The session file plus the prompts written beside it.

    Those are exactly what ``write_prompt`` emits for a slug: ``-prompt.md``
    (start, next-round, recommend), ``-sN-prompt.md`` (panel shards) and
    ``-evidence-prompt.md`` (evidence). The pattern is anchored on the whole
    slug, so closing ``a`` never touches ``ab``'s files.
    """
    safe = validate_slug(slug)
    own = re.compile(rf"^{re.escape(SESSION_PREFIX + safe)}(?:-s\d+|-evidence)?{re.escape(PROMPT_SUFFIX)}$")
    others = set(list_slugs(root)) - {safe}
    out = [session_path(root, safe)]
    for p in sorted(work_dir(root).iterdir()):
        stem = p.name[len(SESSION_PREFIX):-len(PROMPT_SUFFIX)]
        # `a-s1` and `a-evidence` are valid slugs too: their own prompt is not `a`'s to move.
        if p.is_file() and own.match(p.name) and stem not in others:
            out.append(p)
    return out


def close_session(root: Path, slug: str) -> list[tuple[Path, Path]]:
    """Move the session's files into ``work/brainstorm-closed/``; ``(src, dst)`` pairs.

    Checks every destination before moving anything, so a refusal leaves the
    session exactly as it was.
    """
    safe = validate_slug(slug)
    if not session_path(root, safe).is_file():
        raise BrainstormError(f"no open brainstorm session {safe!r} (looked for {SESSION_PREFIX}{safe}.yaml in work/)")
    dest = closed_dir(root)
    moves = [(p, dest / p.name) for p in session_files(root, safe)]
    for _src, dst in moves:
        if dst.exists():
            raise BrainstormError(
                f"{dst.relative_to(root).as_posix()} already exists — a session named {safe!r} was "
                "closed before; rename or remove that file, then close again"
            )
    dest.mkdir(parents=True, exist_ok=True)
    for src, dst in moves:
        src.rename(dst)
    return moves
