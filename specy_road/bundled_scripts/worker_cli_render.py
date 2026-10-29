"""How ``specy-road worker …`` renders a worker record and its events as text."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from specy_road.worker_process import wrapper_alive
from specy_road.worker_state import events_since


def _row(rec) -> dict[str, Any]:
    d = rec.to_dict()
    d["alive"] = wrapper_alive(rec)
    return d


def _line(rec, repo: Path | None = None) -> str:
    flags = f" [{', '.join(rec.flags)}]" if rec.flags else ""
    run = " (running)" if wrapper_alive(rec) else ""
    line = (f"{rec.worker_id}  {rec.node_id:<10} {rec.harness}/{rec.model:<22} {rec.state}{run}  "
            f"lease={rec.lease.get('holder')} epoch={rec.instruction_epoch}{flags}")
    if repo is not None and rec.state == "failed":
        msg = _terminal_message(repo, rec.worker_id)
        if msg:
            line += f"\n  {msg}"
    return line


def _ends_turn(e: dict[str, Any]) -> bool:
    """The wrapper's own exit record: a completion, or an error carrying the exit code."""
    return e.get("type") == "completion" or (e.get("type") == "error" and "exit" in (e.get("detail") or {}))


def _harness_message_before(events: list[dict[str, Any]], seq: int) -> str | None:
    """The last full harness message of the turn that ``seq`` ends; never an earlier turn's."""
    for e in reversed(events):
        if e["seq"] >= seq:
            continue
        if _ends_turn(e):
            return None
        if e.get("source") != "worker":
            continue
        msg = (e.get("detail") or {}).get("message")
        if msg:
            return str(msg)
    return None


def _terminal_message(repo: Path, worker_id: str) -> str | None:
    evs = [e.to_dict() for e in events_since(repo, worker_id)]
    for ev in reversed(evs):
        if ev.get("type") != "error" or ev.get("source") != "worker":
            continue
        msg = (ev.get("detail") or {}).get("message") or _harness_message_before(evs, ev["seq"])
        if msg:
            return msg
    return None


def _sync_event_lines(events: list[dict[str, Any]], e: dict[str, Any]) -> list[str]:
    lines = [f"  #{e['seq']} {e['type']} ({e['source']}): {e['summary']}"]
    detail = e.get("detail") or {}
    msg = detail.get("message")
    if e["type"] == "completion" and not detail.get("ready"):
        msg = msg or _harness_message_before(events, e["seq"])
    if e["type"] == "error" and e.get("source") == "worker":
        msg = msg or _harness_message_before(events, e["seq"])
    if msg:
        lines.append(f"  {msg}")
    return lines
