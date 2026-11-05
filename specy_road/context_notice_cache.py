"""Print ``validate``'s ``context:`` warnings in full only when they changed.

The always-injected-context warnings (:func:`specy_road.agents_md_block.warn_if_context_over_limits`)
repeat on every ``validate`` until the files shrink, which is often never on
purpose. So ``validate`` keeps a hash of their text in ``.specyrd/cache/`` (per
checkout, never committed) and, when it matches the last run, prints one line
instead. Every report records its text, folded or not (``upgrade`` and
``validate --context`` too), so "unchanged" always means "the same as the
report just before". That line stays on stderr, so ``--strict`` still counts it.
``validate --context`` and ``upgrade`` always print them in full: only the
``validate`` CLI turns folding on (:func:`fold_next_report`), for the one
report its run makes, so ``upgrade``'s call to ``validate_at`` never folds.

The hash file is disposable: any failure to read, compare or write it is a
cache miss, so the warnings print in full and the command goes on. It is
compared as bytes, never decoded, so its content cannot raise.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import sys
from collections.abc import Callable
from pathlib import Path

from specy_road.history_cache import CACHE_DIR, ensure_cache_dir

HASH_FILENAME = "context-warnings.sha256"

_fold_next = False


def fold_next_report(on: bool) -> None:
    """Fold the next :func:`report_context_warnings` call that does not say ``cached`` (the ``validate`` CLI)."""
    global _fold_next
    _fold_next = on


def _hash_path(root: Path) -> Path:
    return root / CACHE_DIR / HASH_FILENAME


def _record(root: Path, text: str) -> bool:
    """Record ``text`` as the latest report; whether it equals the one recorded before it.

    The one place the cache is read, compared and written. Every report records,
    folding or not. Empty text is recorded as no file, so a clean repo gets no
    cache written. Any failure to read is a miss (a directory, no permission,
    any bytes at all: they are compared, never decoded); a failure to write or
    remove is ignored.
    """
    path = _hash_path(root)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest().encode("ascii") if text else None
    previous = None
    with contextlib.suppress(OSError):
        previous = path.read_bytes().strip()
    unchanged = digest is not None and previous == digest
    with contextlib.suppress(OSError):
        if digest is None:
            path.unlink(missing_ok=True)
        elif not unchanged:
            ensure_cache_dir(path.parent)
            path.write_bytes(digest + b"\n")
    return unchanged


def report_context_warnings(root: Path, warn: Callable[[Path], None], *, cached: bool | None = None) -> None:
    """Run ``warn(root)`` and record its text; print it in full, or one line when ``cached`` and unchanged.

    ``cached=None`` takes, and clears, what :func:`fold_next_report` set.
    """
    global _fold_next
    if cached is None:
        cached, _fold_next = _fold_next, False
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        warn(root)
    text = captured.getvalue()
    if _record(root, text) and cached:
        n = sum(1 for ln in text.splitlines() if ln.startswith("context: warning"))
        print(f"context: {n} warnings unchanged (validate --context shows them)", file=sys.stderr)
        return
    sys.stderr.write(text)
