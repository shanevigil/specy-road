"""Public API for roadmap history: build it, cache it, query it.

``history_index`` is the one call everything else goes through. It reuses the
on-disk cache when ``HEAD`` has not moved, appends only the new commits when it
has, and rebuilds from scratch when history was rewritten underneath it.

Resolving a node is the subtle part. ``id`` renumbers as the outline is
reorganised, so "M1.2" does not identify one node across history — it is a
position, and different nodes can have held it. :func:`resolve_node_key` walks
from the most authoritative answer to the least and *reports* ambiguity rather
than guessing, because surfacing it is precisely what the index is for.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from specy_road.history_cache import (
    CACHE_VERSION,
    clear_cache,
    load_cache,
    save_cache,
)
from specy_road.history_events import ARCHIVED, RESTORED
from specy_road.history_git import head_sha, is_ancestor
from specy_road.history_walk import walk

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)

# Memo keyed on (repo path, HEAD sha), mirroring node_activity: commit history
# cannot change while HEAD is still, so this is exact rather than a TTL guess.
_MEMO: dict[tuple[str, str], dict[str, Any]] = {}
_MEMO_MAX = 8


def history_index(root: Path, *, rebuild: bool = False) -> dict[str, Any]:
    """The event index for ``root``, cached and incremental.

    Three paths: ``HEAD`` unchanged reuses the cache verbatim; ``HEAD`` moved
    forward from the last indexed commit walks only the new commits; anything
    else — a rebase, an amend, a force-push, a missing or unrecognised cache —
    rebuilds from the beginning.
    """
    head = head_sha(root)
    if head is None:
        # Not a git worktree, or no commits yet. Nothing to derive, and no
        # stable key to memoise under.
        return _document(None, None, [])

    memo_key = (str(root.resolve()), head)
    if not rebuild and memo_key in _MEMO:
        return _MEMO[memo_key]

    if rebuild:
        clear_cache(root)
        cached = None
    else:
        cached = load_cache(root)

    if cached is not None and cached.get("head") == head:
        return _remember(memo_key, cached)

    since, events = _resume_point(root, cached, head)
    new_events, last_seen = walk(root, since)
    doc = _document(head, last_seen or since, [*events, *new_events])
    save_cache(root, doc)
    return _remember(memo_key, doc)


def _resume_point(
    root: Path, cached: dict[str, Any] | None, head: str
) -> tuple[str | None, list[dict[str, Any]]]:
    """Where to resume from, and the events already known at that point.

    A cached commit that is no longer an ancestor of ``HEAD`` means history was
    rewritten, so its events describe commits that no longer exist. Appending to
    them would leave the index permanently wrong; start over instead.
    """
    if cached is None:
        return None, []
    last = cached.get("last_indexed_commit")
    if not isinstance(last, str) or not last:
        return None, []
    if not is_ancestor(root, last, head):
        return None, []
    events = cached.get("events")
    return last, list(events) if isinstance(events, list) else []


def _document(
    head: str | None, last: str | None, events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Assemble the index, stamping each event with its position in the walk.

    Numbering the whole list (rather than continuing a counter) keeps an
    incrementally-appended index identical to a rebuilt one, since both hold the
    same events in the same order.
    """
    for position, event in enumerate(events):
        event["seq"] = position
    return {
        "cache_version": CACHE_VERSION,
        "head": head,
        "last_indexed_commit": last,
        "events": events,
    }


def _remember(key: tuple[str, str], doc: dict[str, Any]) -> dict[str, Any]:
    if len(_MEMO) >= _MEMO_MAX:
        _MEMO.pop(next(iter(_MEMO)))
    _MEMO[key] = doc
    return doc


def clear_memo() -> None:
    """Drop the in-process memo (tests, and after rewriting history)."""
    _MEMO.clear()


# --- queries ----------------------------------------------------------------


def _event_sort_key(event: dict[str, Any]) -> tuple[int, str, str]:
    """Order by walk position first.

    Commit timestamps are second-resolution, so several roadmap commits made in
    the same second tie — and breaking that tie on the commit SHA orders them at
    random, which showed a status going ``In Progress -> Complete`` *before* the
    ``Not Started -> In Progress`` that preceded it. ``seq`` is assigned in walk
    order, which is mainline order, so it never ties.
    """
    seq = event.get("seq")
    return (
        seq if isinstance(seq, int) else 0,
        str(event.get("at") or ""),
        str(event.get("kind") or ""),
    )


def events(index: dict[str, Any]) -> list[dict[str, Any]]:
    raw = index.get("events")
    return [e for e in raw if isinstance(e, dict)] if isinstance(raw, list) else []


def node_timeline(index: dict[str, Any], node_key: str) -> list[dict[str, Any]]:
    """Every event for one node, oldest first."""
    matched = [e for e in events(index) if e.get("node_key") == node_key]
    return sorted(matched, key=_event_sort_key)


def feed(
    index: dict[str, Any],
    *,
    since: str | None = None,
    kinds: set[str] | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Roadmap-wide events, newest first.

    ``since`` is compared as an ISO 8601 prefix, so ``2026-01-01`` and a full
    timestamp both work without parsing dates.
    """
    out = events(index)
    if kinds:
        out = [e for e in out if e.get("kind") in kinds]
    if since:
        out = [e for e in out if str(e.get("at") or "") >= since]
    out = sorted(out, key=_event_sort_key, reverse=True)
    return out[:limit] if limit else out


def archive_history(index: dict[str, Any]) -> list[dict[str, Any]]:
    """Archived and restored events only — the work that left the live graph."""
    return feed(index, kinds={ARCHIVED, RESTORED})


def ids_ever_held(index: dict[str, Any], node_key: str) -> list[str]:
    """Every ``id`` this node has had, oldest first. Usually one."""
    seen: list[str] = []
    for event in node_timeline(index, node_key):
        for value in (event.get("from"), event.get("id"), event.get("to")):
            if isinstance(value, str) and value.startswith("M") and value not in seen:
                seen.append(value)
    return seen


# --- resolving a node argument ----------------------------------------------


def _live_key_for_id(root: Path, node_id: str) -> str | None:
    try:
        from specy_road.archive_plan import ensure_bundled_scripts_on_path

        ensure_bundled_scripts_on_path()
        from roadmap_chunk_router_pick import load_merged_nodes

        for node in load_merged_nodes(root):
            if node.get("id") == node_id and isinstance(node.get("node_key"), str):
                return node["node_key"]
    except Exception:  # noqa: BLE001 - resolution falls through to the ledger
        return None
    return None


def _archived_key_for_id(root: Path, node_id: str) -> str | None:
    try:
        from specy_road.archive_index import index_records, load_archive_index

        for record in index_records(load_archive_index(root)):
            for summary in record.get("nodes_summary") or []:
                if isinstance(summary, dict) and summary.get("id") == node_id:
                    key = summary.get("node_key")
                    if isinstance(key, str):
                        return key
    except Exception:  # noqa: BLE001 - a broken ledger must not block history
        return None
    return None


def _historical_keys_for_id(index: dict[str, Any], node_id: str) -> list[str]:
    """Every node_key that ever carried ``node_id``, in first-seen order."""
    keys: list[str] = []
    for event in sorted(events(index), key=_event_sort_key):
        if event.get("id") != node_id and event.get("to") != node_id:
            continue
        key = event.get("node_key")
        if isinstance(key, str) and key not in keys:
            keys.append(key)
    return keys


def resolve_node_key(
    root: Path, arg: str, index: dict[str, Any]
) -> tuple[str | None, list[str]]:
    """``(node_key, candidates)`` for a user-supplied node id or key.

    A resolved key comes back with an empty candidate list. When only history
    can answer and more than one node has held the id, the key is ``None`` and
    every candidate is returned for the caller to present — an id is a position
    in the outline, not an identity, so guessing here would silently show the
    wrong node's past.
    """
    arg = arg.strip()
    if _UUID_RE.match(arg):
        return arg.lower(), []
    for lookup in (_live_key_for_id, _archived_key_for_id):
        key = lookup(root, arg)
        if key:
            return key, []
    candidates = _historical_keys_for_id(index, arg)
    if len(candidates) == 1:
        return candidates[0], []
    return None, candidates
