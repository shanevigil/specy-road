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
subdirectory is ignored. The directory ignores itself (:func:`ensure_cache_dir`
writes a ``.gitignore`` of ``*`` into it): the managed ``.gitignore`` block
reaches only repos that ran ``refresh-stubs`` or ``init project``, and the
first ``validate`` after an upgrade must not leave ``?? .specyrd/`` behind.

Every failure here costs a rebuild, never a failed command. One rule
decides which are silent: a path the safe-write rule refuses
(:class:`~specy_road.safe_write.SafeWriteError`: a symlink anywhere on the
cache path, live or dangling; a non-directory where a directory belongs;
anything but a regular file at the end; a component ``lstat`` cannot read) is
one warning naming that path from :func:`save_cache`, so a planted link or a
misplaced file is visible. Every other failure (a read-only checkout, a full
disk, a half-written file) is silent by design. Either way the command
carries on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from specy_road import safe_write

# Bump to invalidate every existing cache. There is deliberately no migration
# code: a mismatch rebuilds from git, which is always authoritative.
CACHE_VERSION = 1

CACHE_DIR = Path(".specyrd") / "cache"
CACHE_FILENAME = "roadmap-history.json"

_REQUIRED = ("cache_version", "head", "last_indexed_commit", "events")


def cache_path(root: Path) -> Path:
    return root / CACHE_DIR / CACHE_FILENAME


def ensure_cache_dir(cache_dir: Path) -> None:
    """Create ``cache_dir`` with a ``.gitignore`` of ``*`` in it; raises ``OSError``.

    ``cache_dir`` is ``<root>/.specyrd/cache``; the safe-write rule walks it from
    that root, so any path it refuses (a symlinked ``.specyrd``, ``cache`` or
    ``.gitignore`` among them) raises :class:`~specy_road.safe_write.SafeWriteError`
    (an ``OSError``).
    """
    root = cache_dir.parents[1]
    safe_write.mkdirs(root, cache_dir)
    ignore = cache_dir / ".gitignore"
    if not safe_write.check(root, ignore).is_file():
        safe_write.write(root, ignore, "# Written by specy-road: everything here is derived.\n*\n")


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

    :func:`specy_road.safe_write.write` from ``root`` (temp file plus
    :func:`os.replace` in the same directory), so a reader either sees the whole
    previous cache or the whole new one. Two processes racing resolve to
    last-writer-wins, and since both computed the same thing from the same
    history, either outcome is correct. A safe-write refusal is a warning naming
    the path on stderr; every other failure is silent (the module docstring).
    """
    path = cache_path(root)
    try:
        ensure_cache_dir(path.parent)
        safe_write.write(root, path, json.dumps(doc, ensure_ascii=False))
    except safe_write.SafeWriteError as e:
        print(f"warning: history cache not written: {e}", file=sys.stderr)
        return False
    except (OSError, ValueError, TypeError):
        return False
    return True


def clear_cache(root: Path) -> None:
    """Remove the cache file. Used by ``--rebuild`` and by tests."""
    try:
        cache_path(root).unlink(missing_ok=True)
    except OSError:
        pass
