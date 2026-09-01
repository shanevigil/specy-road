"""On-disk cache for the roadmap history index.

**Derived, gitignored, and disposable.** Git is the source of truth for every
event in it, so the cache is never migrated — a version it does not recognise is
thrown away and rebuilt. That is the whole reason it can be added at all:
:mod:`specy_road.node_activity` rejects a *committed* sidecar for four concrete
reasons (a cold start on existing repos, a file that dirties the working tree and
trips the toolkit's own clean-tree checks, concurrent writers, and a schema to
migrate), and a rebuildable cache under ``.specyrd/cache/`` answers all four:
nothing to seed, nothing tracked, a last-writer-wins atomic replace, and no
migration path to write.

It lives under ``.specyrd/cache/`` rather than in ``.specyrd/`` proper because
``.specyrd/manifest.json`` is deliberately tracked; only the ``cache/``
subdirectory is ignored.

Every failure here is silent by design. A read-only checkout, a missing
directory, or a half-written file costs a rebuild, never a failed command.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

# Bump to invalidate every existing cache. There is deliberately no migration
# code: a mismatch rebuilds from git, which is always authoritative.
CACHE_VERSION = 1

CACHE_DIR = Path(".specyrd") / "cache"
CACHE_FILENAME = "roadmap-history.json"

_REQUIRED = ("cache_version", "head", "last_indexed_commit", "events")


def cache_path(root: Path) -> Path:
    return root / CACHE_DIR / CACHE_FILENAME


def empty_cache() -> dict[str, Any]:
    return {
        "cache_version": CACHE_VERSION,
        "head": None,
        "last_indexed_commit": None,
        "events": [],
    }


def load_cache(root: Path) -> dict[str, Any] | None:
    """The cached index, or ``None`` when it is absent, stale or unreadable.

    ``None`` always means "rebuild", never "error". A wrong ``cache_version``,
    truncated JSON, or a document missing a required key all take that path.
    """
    path = cache_path(root)
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(doc, dict) or doc.get("cache_version") != CACHE_VERSION:
        return None
    if any(k not in doc for k in _REQUIRED) or not isinstance(doc.get("events"), list):
        return None
    return doc


def save_cache(root: Path, doc: dict[str, Any]) -> bool:
    """Write the cache atomically. ``False`` if it could not be written.

    Temp file plus :func:`os.replace` in the same directory, so a reader either
    sees the whole previous cache or the whole new one. Two processes racing
    resolve to last-writer-wins, and since both computed the same thing from the
    same history, either outcome is correct.
    """
    path = cache_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".history-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    except (OSError, ValueError, TypeError):
        return False
    return True


def clear_cache(root: Path) -> None:
    """Remove the cache file. Used by ``--rebuild`` and by tests."""
    try:
        cache_path(root).unlink(missing_ok=True)
    except OSError:
        pass
