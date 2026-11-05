"""``worker sync`` and its wait helpers (M15.13 — split from :mod:`worker_cli` for the file limit)."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from specy_road import worker_ops as ops
from specy_road.bundled_scripts.worker_cli_render import sync_event_lines, sync_worker_header
from specy_road.runtime_paths import resolve_repo_root
from specy_road.worker_orphans import with_orphans
from specy_road.worker_state import (
    WorkerError,
    events_since,
    flag_stamp,
    load_record,
    wait_for_event,
)

_SYNC_UNTIL = frozenset({"completion", "error", "intervention"})


def parse_sync_until(raw: str | None) -> frozenset[str] | None:
    """Comma-separated event types for ``--wait --until``; ``None`` means any event (default)."""
    if raw is None:
        return None
    types = frozenset(p.strip() for p in raw.split(",") if p.strip())
    bad = types - _SYNC_UNTIL
    if bad:
        raise WorkerError(f"--until: unknown event type(s) {', '.join(sorted(bad))}; "
                          f"expected comma-separated subset of {', '.join(sorted(_SYNC_UNTIL))}")
    return types or None


def _delta_has_type(delta: list[dict[str, Any]], event_types: frozenset[str]) -> bool:
    return any(e["type"] in event_types for w in delta for e in w["events"])


def wait_for_typed_event(repo_root, timeout: float, since: tuple[int, int] | None, interval: float,
                         event_types: frozenset[str]) -> bool:
    """Block until an unacknowledged event whose ``type`` is in ``event_types``, or ``timeout`` elapses."""
    deadline = time.monotonic() + timeout
    stamp = since
    while time.monotonic() < deadline:
        if _delta_has_type(ops.sync(repo_root), event_types):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not wait_for_event(repo_root, remaining, stamp, interval):
            return False
        stamp = flag_stamp(repo_root)
    return False


def wait_for_sync(repo_root, timeout: float, since: tuple[int, int] | None, event_types: frozenset[str] | None) -> bool:
    """Return once ``sync`` would report something worth waiting for (see ``--until``)."""
    if event_types is None:
        if ops.sync(repo_root):
            return True
        return wait_for_event(repo_root, timeout, since)
    if _delta_has_type(ops.sync(repo_root), event_types):
        return True
    return wait_for_typed_event(repo_root, timeout, since, 0.25, event_types)


def cmd_sync(ns: argparse.Namespace, *, emit) -> int:
    root = resolve_repo_root(ns)
    until_types = parse_sync_until(getattr(ns, "until", None))
    timed_out = False
    if ns.wait:
        since = flag_stamp(root)
        try:
            timed_out = not wait_for_sync(root, ns.timeout, since, until_types)
        except KeyboardInterrupt:
            print("worker sync: interrupted; nothing acknowledged", file=sys.stderr)
            return 130
    delta = ops.sync(root, ack=ns.ack)
    lines = []
    for w in delta:
        rec = load_record(root, w["worker_id"])
        w["worktree"] = rec.worktree
        lines += sync_worker_header(w, rec.queued_message)
        lines += [f"  ! gap: event(s) #{a}" + (f"–#{b}" if b > a else "") + " missing from the log (lost or unreadable)"
                  for a, b in w["gaps"]]
        history = [e.to_dict() for e in events_since(root, w["worker_id"])]
        lines += sync_event_lines(history, w["events"], w["worker_id"], verbose=getattr(ns, "verbose", False))
    if not lines:
        lines = ["No new worker events."]
    elif not ns.ack:
        lines.append("(re-run with --ack once handled)")
    rc = emit(ns, *with_orphans(root, {"workers": delta, "acked": ns.ack}, lines))
    return 2 if timed_out else rc


def add_sync_parser(ws, cmd_sync_fn, add_repo_root_arg) -> None:
    sp = ws.add_parser("sync", help="Every worker's events since the last --ack; call at the start of each turn")
    sp.add_argument("--ack", action="store_true", help="Mark the returned events handled")
    sp.add_argument("--wait", action="store_true", help="Block until a worker writes an event (exit 2 on --timeout)")
    sp.add_argument("--until", metavar="TYPES",
                    help="With --wait: return only on these event types (comma list: completion, error, intervention)")
    sp.add_argument("--timeout", type=float, default=600, metavar="SECONDS", help="With --wait (default 600)")
    sp.add_argument("--verbose", action="store_true", help="Show each tool-use output line instead of collapsing runs")
    sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_sync_fn)
