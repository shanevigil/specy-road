"""How ``specy-road worker …`` renders a worker record and its events as text."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from specy_road.worker_adapter_parsers import usage_text
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
            f"worktree={rec.worktree}  "
            f"lease={rec.lease.get('holder')} epoch={rec.instruction_epoch}{flags}")
    if rec.queued_message:
        line += f"\n  queued: {' '.join(rec.queued_message.split())[:300]}"
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


# --- timeline ----------------------------------------------------------------

#: ``(phase name, start event, end event)`` over the worker's latest turn; the
#: "acked" boundary is the sync acknowledgement that covers the turn's end.
PHASES = (("delegated_to_launched", "delegated", "launched"),
          ("launched_to_first_output", "launched", "first_output"),
          ("first_output_to_end", "first_output", "end"),
          ("end_to_acked", "end", "acked"))


def _parse_at(at: str) -> datetime:
    return datetime.fromisoformat(at.replace("Z", "+00:00"))


def _delegation(e: dict[str, Any]) -> bool:
    """The coordinator's ``started`` or ``message``; a harness's own ``started`` line is not a turn."""
    return e["type"] in ("started", "message") and e.get("source") != "worker"


def _latest_turn(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The events from the latest turn's delegation on."""
    starts = [i for i, e in enumerate(events) if _delegation(e)]
    return events[starts[-1]:] if starts else events


def _boundaries(events: list[dict[str, Any]], marks: dict[str, Any] | None) -> dict[str, str | None]:
    turn = _latest_turn(events)
    first = {}
    for e in turn:
        key = "end" if _ends_turn(e) or e["type"] == "turn_completed" else e["type"]
        first.setdefault(key, e)
    b: dict[str, str | None] = {"delegated": None, "launched": None, "first_output": None, "end": None, "acked": None}
    if turn and _delegation(turn[0]):
        b["delegated"] = turn[0]["at"]
    for key in ("launched", "first_output", "end"):
        if key in first:
            b[key] = first[key]["at"]
    # The ack counts for this turn only once it reaches the end event's sequence.
    if "end" in first and marks and marks.get("acked_at") and int(marks.get("seq", 0)) >= first["end"]["seq"]:
        b["acked"] = str(marks["acked_at"])
    return b


def timeline(rec, events: list[dict[str, Any]], marks: dict[str, Any] | None) -> dict[str, Any]:
    """``{"worker_id", "node_id", "phases": {name: seconds | None}}`` for the latest turn."""
    b = _boundaries(events, marks)
    phases: dict[str, float | None] = {}
    for name, start, end in PHASES:
        if b[start] and b[end]:
            phases[name] = (_parse_at(b[end]) - _parse_at(b[start])).total_seconds()
        else:
            phases[name] = None
    return {"worker_id": rec.worker_id, "node_id": rec.node_id, "phases": phases}


def timeline_lines(data: dict[str, Any]) -> list[str]:
    lines = [f"{data['worker_id']} {data['node_id']} timeline (latest turn)"]
    for name, start, end in PHASES:
        secs = data["phases"][name]
        lines.append(f"  {start} -> {end}: " + ("unknown" if secs is None else f"{secs:.0f}s"))
    return lines


# --- usage -------------------------------------------------------------------

_SUMMED = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "cost_usd", "num_turns")


def _sum_usage(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Each figure summed over the rows that report it; ``None`` when none does, so absent never reads as 0."""
    out: dict[str, Any] = {}
    for f in _SUMMED:
        vals = [r[f] for r in rows if r.get(f) is not None]
        out[f] = (round(sum(vals), 6) if f == "cost_usd" else sum(vals)) if vals else None
    flags = [r["cost_is_estimate"] for r in rows if r.get("cost_is_estimate") is not None]
    out["cost_is_estimate"] = any(flags) if flags else None
    return out


def usage(attempts: list[tuple[Any, list[dict[str, Any]]]]) -> dict[str, Any]:
    """``{"node_id", "attempts": [...], "total"}`` from ``(record, events)`` per worker, from its ``usage`` events."""
    rows = []
    for rec, events in attempts:
        turns = [e["detail"] for e in events if e["type"] == "usage" and e.get("detail")]
        versions = [t["harness_version"] for t in turns if t.get("harness_version")]
        rows.append({"attempt": rec.attempt, "worker_id": rec.worker_id, "model": rec.model, "harness": rec.harness,
                     "harness_version": versions[-1] if versions else None, "worktree": rec.worktree,
                     "turns": len(turns), **_sum_usage(turns)})
    return {"node_id": attempts[0][0].node_id, "attempts": rows,
            "total": {"turns": sum(r["turns"] for r in rows), **_sum_usage(rows)}}


def _project_root_of(worktree: str | None) -> Path | None:
    """The project a worker's worktree belongs to, from its nearest existing directory (a finished leaf's
    worktree is gone, its parent under the project's ``work/`` is not)."""
    from specy_road.worker_adapter_parsers import project_root_from_worktree  # noqa: PLC0415

    p = Path(worktree).resolve() if worktree else None
    while p is not None and not p.is_dir():
        p = p.parent if p.parent != p else None
    return project_root_from_worktree(p) if p is not None else None


def reviewer_total(data: dict[str, Any], repo_root: Path | None = None) -> dict[str, Any] | None:
    """The node's ``review usage`` total (``review delegate`` runs only), or ``None`` when it has none."""
    from specy_road.review_usage import review_usage  # noqa: PLC0415 — it imports this module

    root = repo_root or next((r for a in data["attempts"] if (r := _project_root_of(a.get("worktree")))), None)
    t = review_usage(root, data["node_id"])["total"] if root is not None else None
    return t if t and t["runs"] else None


def _combined_node_total(data: dict[str, Any], repo_root: Path | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Executor subtotal, optional reviewer subtotal, and the node total line should show."""
    exec_total, rev = data["total"], reviewer_total(data, repo_root)
    if rev is None:
        return exec_total, None
    combined = {"turns": exec_total["turns"] + rev["turns"], **_sum_usage([exec_total, rev])}
    return combined, rev


def usage_json_payload(data: dict[str, Any], repo_root: Path | None = None) -> dict[str, Any]:
    """Same node totals as :func:`usage_lines`; per-attempt rows stay executor-only for the GUI."""
    combined, rev = _combined_node_total(data, repo_root)
    if rev is None:
        return data
    return {**data, "executors": data["total"], "reviewers": rev, "total": combined}


def usage_lines(data: dict[str, Any], repo_root: Path | None = None) -> list[str]:
    """Per attempt and the node's total; with delegated reviews, executors, reviewers and total on their own lines."""
    lines = [f"{data['node_id']} usage ({len(data['attempts'])} attempt(s); ? = not reported)"]
    for a in data["attempts"]:
        version = f" {a['harness_version']}" if a["harness_version"] else ""
        lines.append(f"  attempt {a['attempt']} {a['worker_id']} {a['harness']}{version}/{a['model']}, {a['turns']} turn(s): {usage_text(a)}")
    combined, rev = _combined_node_total(data, repo_root)
    if rev is not None:
        lines.append(f"  executors, {data['total']['turns']} turn(s): {usage_text(data['total'])}")
        lines.append(f"  reviewers, {rev['runs']} run(s), {rev['turns']} turn(s): {usage_text(rev)}")
    lines.append(f"  total, {combined['turns']} turn(s): {usage_text(combined)}")
    return lines


def sync_worker_header(w: dict[str, Any], queued: str | None) -> list[str]:
    if queued:
        w["queued_message"] = queued
    flags = f" [{', '.join(w['flags'])}]" if w["flags"] else ""
    lines = [f"{w['worker_id']} {w['node_id']} {w['state']} worktree={w['worktree']} "
             f"lease={w['lease']} epoch={w['epoch']}{flags}"]
    if queued:
        lines.append(f"  queued: {' '.join(queued.split())[:300]}")
    return lines
