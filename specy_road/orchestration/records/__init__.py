"""The records orchestration keeps on disk: chores, the decisions ledger and review lessons.

Each record keeps its own file and format: a chore is JSON under the main checkout's
``work/chores/``, the decisions ledger is YAML checked against its schema
(``roadmap/decisions.yaml``, with this clone's ``decisions.local.yaml`` over it), and review
lessons are hand-editable Markdown (``constraints/review-lessons.md``). What they share is how a
record file is read and written, the two functions below, not a format or a store. They live in
this package's own module so a reader of one record (``validate`` reads the ledger) imports no
extra module for them.

A missing file reads as ``None``, so each record says once what its absence means (an empty
ledger, no lessons, not a chore). A write creates the file's directory first and replaces the
whole file in place; chores are written atomically by their commands, which this does not change.
"""

from __future__ import annotations

from pathlib import Path


def read_text(path: Path) -> str | None:
    """``path``'s UTF-8 text, or ``None`` when no file is there (a directory counts as none)."""
    return path.read_text(encoding="utf-8") if path.is_file() else None


def write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` as UTF-8, creating its directory first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
