"""CLI for roadmap history: one node's timeline, or a roadmap-wide feed.

Read-only. Nothing here writes to the roadmap; the only file it touches is the
gitignored cache under ``.specyrd/cache/``, and even that is best-effort.

``--json`` is the contract an agentic IDE should consume: a stable envelope of
events, each carrying the commit that produced it, so the caller can join
against git for anything this does not already answer.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.history_events import ARCHIVED, RESTORED, SHEET_EDIT
from specy_road.history_index import (
    events as all_events,
    feed,
    history_index,
    ids_ever_held,
    node_timeline,
    resolve_node_key,
)
from specy_road.runtime_paths import default_user_repo_root

# How each event kind reads on one line. `{}` slots are filled from the event.
_PHRASES = {
    "created": "created as {to_or_id}",
    "removed": "removed from the roadmap",
    "status": "status {from} -> {to}",
    "renumbered": "renumbered {from} -> {to}",
    "retitled": "retitled to {to}",
    "recodenamed": "codename {from} -> {to}",
    "reparented": "moved under {to}",
    "dep_added": "depends on {to}",
    "dep_removed": "no longer depends on {from}",
    SHEET_EDIT: "planning sheet edited",
    ARCHIVED: "archived as {archive_id}",
    RESTORED: "restored from {archive_id}",
}

# A field that had no previous value reads badly as "? -> x".
_INITIAL_PHRASES = {
    "status": "status set to {to}",
    "renumbered": "id set to {to}",
    "recodenamed": "codename set to {to}",
    "reparented": "parent set to {to}",
}


def _root(ns: argparse.Namespace) -> Path:
    return (ns.repo_root or default_user_repo_root()).resolve()


def describe(event: dict) -> str:
    """A one-line phrase for an event, falling back to its raw kind."""
    kind = str(event.get("kind"))
    if not event.get("from") and kind in _INITIAL_PHRASES:
        template = _INITIAL_PHRASES[kind]
    else:
        template = _PHRASES.get(kind)
    if template is None:
        return kind
    values = {
        "from": event.get("from"),
        "to": event.get("to"),
        "to_or_id": event.get("to") or event.get("id"),
        "archive_id": event.get("archive_id"),
    }
    for name, value in values.items():
        template = template.replace("{" + name + "}", str(value) if value else "?")
    return template


def _print_events(events: list[dict], *, show_node: bool) -> None:
    for event in events:
        when = str(event.get("at") or "")[:10]
        commit = str(event.get("commit") or "")[:8]
        who = str(event.get("author") or "")
        label = f"{event.get('id') or event.get('node_key', '')[:8]:<8} " if show_node else ""
        print(f"{when}  {commit}  {label}{describe(event):<44} {who}")


def cmd_history(ns: argparse.Namespace) -> int:
    root = _root(ns)
    index = history_index(root, rebuild=ns.rebuild)

    if ns.node is None:
        return _cmd_feed(ns, index)
    return _cmd_node(ns, root, index)


def _cmd_feed(ns: argparse.Namespace, index: dict) -> int:
    kinds = {ARCHIVED, RESTORED} if ns.archived else None
    events = feed(index, since=ns.since, kinds=kinds, limit=ns.limit)
    if ns.json:
        print(json.dumps({"events": events}, indent=2, sort_keys=True))
        return 0
    if not events:
        print(_empty_note(index))
        return 0
    _print_events(events, show_node=True)
    print(f"\n{len(events)} event(s) from {len(all_events(index))} indexed.")
    return 0


def _cmd_node(ns: argparse.Namespace, root: Path, index: dict) -> int:
    key, candidates = resolve_node_key(root, ns.node, index)
    if key is None:
        return _report_unresolved(ns.node, candidates, index)

    events = node_timeline(index, key)
    if ns.archived:
        events = [e for e in events if e["kind"] in (ARCHIVED, RESTORED)]
    if ns.since:
        events = [e for e in events if str(e.get("at") or "") >= ns.since]
    if ns.limit:
        events = events[-ns.limit:]

    if ns.json:
        payload = {"node_key": key, "ids": ids_ever_held(index, key), "events": events}
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    ids = ids_ever_held(index, key)
    print(f"{ns.node}  node_key {key}")
    if len(ids) > 1:
        print(f"  ids over time: {' -> '.join(ids)}")
    print()
    if not events:
        print(_empty_note(index))
        return 0
    _print_events(events, show_node=False)
    return 0


def _report_unresolved(arg: str, candidates: list[str], index: dict) -> int:
    """Ambiguity is the answer, not a failure to find one."""
    if not candidates:
        print(
            f"error: no node {arg!r} in the roadmap, the archive ledger, or history.",
            file=sys.stderr,
        )
        return 1
    print(
        f"error: {arg!r} is ambiguous — {len(candidates)} nodes have held that id.\n"
        "An id is a position in the outline, not an identity. Re-run with one "
        "of these node_keys:",
        file=sys.stderr,
    )
    for key in candidates:
        ids = " -> ".join(ids_ever_held(index, key)) or "?"
        print(f"  {key}   {ids}", file=sys.stderr)
    return 2


def _empty_note(index: dict) -> str:
    if index.get("head") is None:
        return (
            "no history: this is not a git worktree, or it has no commits yet. "
            "Roadmap history is derived from git and is not stored anywhere else."
        )
    return "no matching events."


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="specy-road history",
        description=(
            "How the roadmap got here: status changes, dependency edges, "
            "renumbering, and archived work, derived from git history."
        ),
    )
    p.add_argument(
        "node",
        metavar="NODE_ID",
        nargs="?",
        help="A node id (M1.2) or node_key. Omit for a roadmap-wide feed.",
    )
    p.add_argument(
        "--since",
        metavar="DATE",
        default=None,
        help="Only events on or after this ISO date, e.g. 2026-01-01.",
    )
    p.add_argument(
        "--archived",
        action="store_true",
        help="Only archive/restore events — work that left the live graph.",
    )
    p.add_argument("--limit", type=int, default=None, metavar="N")
    p.add_argument("--json", action="store_true", help="Machine-readable output.")
    p.add_argument(
        "--rebuild",
        action="store_true",
        help="Discard the cache under .specyrd/cache/ and re-walk all history.",
    )
    p.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        metavar="DIR",
        help="Repository root (default: git root or cwd).",
    )
    p.set_defaults(func=cmd_history)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `specy-road history …` forwards its own name; argparse defines it here.
    if argv and argv[0] == "history":
        argv = argv[1:]
    ns = build_parser().parse_args(argv)
    try:
        raise SystemExit(ns.func(ns))
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
