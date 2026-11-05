"""Print ``validate``'s ``context:`` warnings in full only when they changed.

The always-injected-context warnings (:func:`specy_road.agents_md_block.warn_if_context_over_limits`)
repeat on every ``validate`` until the files shrink, which is often never on
purpose. So ``validate`` keeps a hash of their text in ``.specyrd/cache/`` (per
checkout, never committed) and, when it matches the last run, prints one line
instead. That line stays on stderr, so ``--strict`` still counts it.
``validate --context`` and ``upgrade`` always print them in full.
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


def _hash_path(root: Path) -> Path:
    return root / CACHE_DIR / HASH_FILENAME


def _changed(root: Path, digest: str) -> bool:
    """Whether ``digest`` differs from the last recorded one; records it. An unwritable cache counts as changed."""
    path = _hash_path(root)
    try:
        if path.is_file() and path.read_text(encoding="utf-8").strip() == digest:
            return False
        ensure_cache_dir(path.parent)
        path.write_text(digest + "\n", encoding="utf-8")
    except OSError:
        pass
    return True


def report_context_warnings(root: Path, warn: Callable[[Path], None], *, cached: bool) -> None:
    """Run ``warn(root)``; print its stderr in full, or one line when ``cached`` and unchanged since the last run."""
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        warn(root)
    text = captured.getvalue()
    if cached and not text:
        with contextlib.suppress(OSError):
            _hash_path(root).unlink(missing_ok=True)   # nothing to remember: a clean repo gets no cache written
    if not cached or not text:
        sys.stderr.write(text)
        return
    if not _changed(root, hashlib.sha256(text.encode("utf-8")).hexdigest()):
        n = sum(1 for ln in text.splitlines() if ln.startswith("context: warning"))
        print(f"context: {n} warnings unchanged (validate --context shows them)", file=sys.stderr)
        return
    sys.stderr.write(text)
