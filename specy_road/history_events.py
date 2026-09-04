"""The roadmap history event model, and the graph diff that produces it.

Pure: no git, no filesystem, no subprocess. Everything here takes dicts and
returns dicts, which is what makes the interesting logic — "what changed
between these two versions of the roadmap?" — testable without building a
repository.

**Events are keyed by ``node_key``, never by ``id``.** ``node_key`` is an
immutable UUID while ``id`` renumbers freely as the outline is reorganised, so
an id-keyed history would lose a node's past every time someone inserted a
milestone above it. Recording the id as *data* on each event instead means a
renumbering shows up as an ordinary event (``renumbered``) and the node's story
stays continuous across it.

A node's ``status`` here is its **own** status as written to the chunk, not the
derived ``rollup_status``: rollup is recomputed on load and never persisted, so
it has no history to read.
"""

from __future__ import annotations

from typing import Any

# Structural lifecycle.
CREATED = "created"
REMOVED = "removed"

# Field-level changes on a node that stayed in the graph.
STATUS = "status"
RENUMBERED = "renumbered"
RETITLED = "retitled"
RECODENAMED = "recodenamed"
REPARENTED = "reparented"

# Dependency edges.
DEP_ADDED = "dep_added"
DEP_REMOVED = "dep_removed"

# Sourced from planning/ paths rather than the graph.
SHEET_EDIT = "sheet_edit"

# Sourced from roadmap/archive/index.json rather than the graph.
ARCHIVED = "archived"
RESTORED = "restored"

# Scalar node fields worth a distinct event kind, in emission order.
_TRACKED_FIELDS: tuple[tuple[str, str], ...] = (
    ("id", RENUMBERED),
    ("title", RETITLED),
    ("status", STATUS),
    ("codename", RECODENAMED),
    ("parent_id", REPARENTED),
)

# What a snapshot keeps per node. Deliberately narrow: this is cached on disk
# once per repo, so it holds what history questions are asked about and not the
# whole node.
_STATE_FIELDS = ("id", "title", "status", "codename", "parent_id", "type")


def node_state(node: dict[str, Any]) -> dict[str, Any]:
    """The slice of a node that history tracks."""
    state: dict[str, Any] = {f: node.get(f) for f in _STATE_FIELDS}
    deps = node.get("dependencies")
    state["deps"] = sorted(d for d in deps if isinstance(d, str)) if isinstance(deps, list) else []
    return state


def snapshot(nodes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """``{node_key: state}`` for every node that has one.

    A node with no ``node_key`` is skipped rather than synthesised: without a
    stable identity there is nothing to track it across commits by.
    """
    out: dict[str, dict[str, Any]] = {}
    for node in nodes:
        key = node.get("node_key")
        if isinstance(key, str) and key:
            out[key] = node_state(node)
    return out


def make_event(
    meta: dict[str, Any], node_key: str, kind: str, **fields: Any
) -> dict[str, Any]:
    """One event, carrying the commit that produced it."""
    event = {
        "at": meta.get("at"),
        "commit": meta.get("commit"),
        "author": meta.get("author"),
        "node_key": node_key,
        "kind": kind,
    }
    event.update({k: v for k, v in fields.items() if v is not None})
    return event


def _sort_key(event: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(event.get("node_key") or ""),
        str(event.get("kind") or ""),
        str(event.get("to") or event.get("from") or ""),
    )


def _field_events(
    key: str, before: dict[str, Any], after: dict[str, Any], meta: dict[str, Any]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for field, kind in _TRACKED_FIELDS:
        old, new = before.get(field), after.get(field)
        if old != new:
            out.append(
                make_event(meta, key, kind, id=after.get("id"), **{"from": old, "to": new})
            )
    return out


def _dep_events(
    key: str, before: dict[str, Any], after: dict[str, Any], meta: dict[str, Any]
) -> list[dict[str, Any]]:
    old = set(before.get("deps") or [])
    new = set(after.get("deps") or [])
    out: list[dict[str, Any]] = []
    for dep in sorted(new - old):
        out.append(make_event(meta, key, DEP_ADDED, id=after.get("id"), to=dep))
    for dep in sorted(old - new):
        out.append(make_event(meta, key, DEP_REMOVED, id=after.get("id"), **{"from": dep}))
    return out


def diff_snapshots(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    meta: dict[str, Any],
) -> list[dict[str, Any]]:
    """Every event implied by the move from ``before`` to ``after``.

    ``created`` and ``removed`` are structural only — they say a ``node_key``
    entered or left the *live* graph. Archiving also removes a node from the
    live graph, so the caller reconciles these against the archive ledger
    before recording them (see :func:`reconcile_archive`).
    """
    events: list[dict[str, Any]] = []
    for key in sorted(set(after) - set(before)):
        state = after[key]
        events.append(
            make_event(meta, key, CREATED, id=state.get("id"), title=state.get("title"))
        )
    for key in sorted(set(before) - set(after)):
        state = before[key]
        events.append(
            make_event(meta, key, REMOVED, id=state.get("id"), title=state.get("title"))
        )
    for key in sorted(set(before) & set(after)):
        events.extend(_field_events(key, before[key], after[key], meta))
        events.extend(_dep_events(key, before[key], after[key], meta))
    return sorted(events, key=_sort_key)


def reconcile_archive(
    events: list[dict[str, Any]],
    archived_keys: set[str],
    restored_keys: set[str],
) -> list[dict[str, Any]]:
    """Drop structural events that the archive ledger already explains.

    Archiving takes nodes out of the live graph and restoring puts them back,
    so the graph diff reports them as ``removed`` and ``created``. Those are
    misleading — nothing was deleted or invented — and the walk emits richer
    ``archived``/``restored`` events for the same commit from the ledger. Keep
    the ledger's version and drop the graph's.
    """
    return [
        e
        for e in events
        if not (e.get("kind") == REMOVED and e.get("node_key") in archived_keys)
        and not (e.get("kind") == CREATED and e.get("node_key") in restored_keys)
    ]


def archive_events(
    before: dict[str, Any], after: dict[str, Any], meta: dict[str, Any]
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Diff two ``roadmap/archive/index.json`` documents.

    Returns the events plus the node_keys archived and restored in this commit,
    which :func:`reconcile_archive` needs to clean up the graph diff.
    """
    old = _records_by_id(before)
    new = _records_by_id(after)
    events: list[dict[str, Any]] = []
    archived: set[str] = set()
    restored: set[str] = set()

    for aid in sorted(set(new) - set(old)):
        keys = _record_keys(new[aid])
        archived |= keys
        events.extend(_ledger_events(new[aid], keys, ARCHIVED, meta))
    for aid in sorted(set(old) - set(new)):
        keys = _record_keys(old[aid])
        restored |= keys
        events.extend(_ledger_events(old[aid], keys, RESTORED, meta))
    return sorted(events, key=_sort_key), archived, restored


def _ledger_events(
    record: dict[str, Any], keys: set[str], kind: str, meta: dict[str, Any]
) -> list[dict[str, Any]]:
    """One event per node in an archived or restored subtree."""
    ids = {
        n.get("node_key"): n.get("id")
        for n in record.get("nodes_summary") or []
        if isinstance(n, dict)
    }
    return [
        make_event(
            meta,
            key,
            kind,
            id=ids.get(key),
            archive_id=record.get("archive_id"),
            root_node_id=record.get("root_node_id"),
        )
        for key in sorted(keys)
    ]


def _records_by_id(doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = doc.get("records") if isinstance(doc, dict) else None
    if not isinstance(records, list):
        return {}
    return {
        r["archive_id"]: r
        for r in records
        if isinstance(r, dict) and isinstance(r.get("archive_id"), str)
    }


def _record_keys(record: dict[str, Any]) -> set[str]:
    keys = record.get("node_keys")
    if not isinstance(keys, list):
        return set()
    return {k for k in keys if isinstance(k, str)}
