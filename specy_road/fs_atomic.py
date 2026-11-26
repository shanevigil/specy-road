"""Replace a file's text in one step, so a reader sees the old or the new file, never half of one.

Writers that must refuse symlinks on the path use :mod:`specy_road.safe_write` or
:func:`specy_road.review_write_check.replace_file` instead; this helper takes no
repository root and checks nothing.
"""

from __future__ import annotations

import os
from pathlib import Path


def atomic_write_text(path: Path, text: str, *, tmp: Path | None = None) -> None:
    """Write ``text`` to a temporary file beside ``path``, then rename it over ``path``.

    The text is UTF-8, with newlines translated as :meth:`Path.write_text` does. The
    temporary file is ``tmp``, or ``.<name>.<pid>.tmp`` in ``path``'s directory; it is
    created with the process umask, so a new or replaced file gets that mode. A failed
    write leaves the temporary file where it is: a caller that rolls back passes its
    own ``tmp`` so it can remove it.
    """
    tmp = tmp or path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def read_text_exact(path: Path) -> str:
    """``path``'s UTF-8 text with its line endings kept exactly: no ``\\r\\n`` or ``\\r`` translation.

    For a reader whose text is written back or compared with what was written:
    :meth:`Path.read_text` would turn a user's CRLF into LF.
    """
    with path.open(encoding="utf-8", newline="") as f:
        return f.read()


def split_lines(text: str) -> list[str]:
    """``text`` split on ``\\n`` only, as :meth:`str.splitlines` splits a ``\\n``-only text.

    :meth:`str.splitlines` also breaks on ``\\r``, U+0085, U+2028, U+2029 and others,
    which a value written by specy-road may hold. As with it, a final ``\\n`` ends the
    last line rather than starting an empty one, and any ``\\r`` stays in its line.
    """
    lines = text.split("\n")
    return lines[:-1] if lines[-1] == "" else lines
