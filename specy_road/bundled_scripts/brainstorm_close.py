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
#: The pass part of a prompt name ``prompt_path`` writes (``-r<N>``, ``-r1-s<K>``, ``-recommend``,
#: ``-evidence``), plus the bare and ``-s<K>`` names older versions wrote.
PROMPT_PASS_RE = r"(?:-r\d+(?:-s\d+)?|-recommend|-evidence|-s\d+)?"


def closed_dir(root: Path) -> Path:
    return work_dir(root) / CLOSED_DIRNAME


def _prompt_names(slug: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(SESSION_PREFIX + slug)}{PROMPT_PASS_RE}{re.escape(PROMPT_SUFFIX)}$")


def session_files(root: Path, slug: str) -> list[Path]:
    """The session file plus the prompts written beside it.

    Those are exactly what ``write_prompt`` emits for a slug: one per pass
    (``-r<N>``, ``-r1-s<K>``, ``-recommend``, ``-evidence``), plus the bare and
    ``-s<K>`` names older versions wrote. The pattern is anchored on the whole
    slug, so closing ``a`` never touches ``ab``'s files.
    """
    safe = validate_slug(slug)
    own = _prompt_names(safe)
    others = [_prompt_names(s) for s in list_slugs(root) if s != safe]
    out = [session_path(root, safe)]
    for p in sorted(work_dir(root).iterdir()):
        # `a-s1` and `a-r1` are valid slugs too: a name another open session could own is not `a`'s to move.
        if p.is_file() and own.match(p.name) and not any(o.match(p.name) for o in others):
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
