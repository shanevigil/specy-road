#!/usr/bin/env python3
"""CLI for ``specy-road worker …`` (``docs/orchestration-workers.md``). Commands return at once except ``sync --wait``.
Exit codes: 0 done, 1 refused or failed, 2 unsupported or ``sync --wait`` timed out.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from specy_road import worker_ops as ops
from specy_road.bundled_scripts.role_prompt_rework import rework_check
from specy_road.bundled_scripts.worker_cli_args import FixRound
from specy_road.bundled_scripts.worker_cli_render import (_line, _row, timeline, timeline_lines, usage, usage_lines)
from specy_road.bundled_scripts.worker_cli_sync import add_sync_parser, cmd_sync as _cmd_sync
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.tool_call_guard import read_payload
from specy_road.worker_adapters import ADAPTERS, Unsupported
from specy_road.worker_hook import HOOKS
from specy_road.worker_orphans import add_terminate, list_view
from specy_road.worker_outbox import lookup_op
from specy_road.worker_reconcile import reconcile_lines, sync_marks
from specy_road.worker_runner import log_path
from specy_road.worker_sessions import render_command
from specy_road.worker_state import (
    HARNESSES,
    LeaseError,
    WorkerError,
    begin_op,
    complete_op,
    events_since,
    list_records,
    load_record,
)


def _emit(ns: argparse.Namespace, data: dict[str, Any], lines: list[str]) -> int:
    print(json.dumps(data, indent=2) if ns.json else "\n".join(lines))
    return 0


def _target_of(ns: argparse.Namespace) -> str | None:
    return getattr(ns, "worker_id", None) or getattr(ns, "node_id", None) or getattr(ns, "node", None)


def _replay(ns: argparse.Namespace, op: str, old: dict[str, Any]) -> int:
    print(json.dumps(old["result"], indent=2) if ns.json else f"op {op} already {old['state']}: "
          + json.dumps(old["result"]))
    return 0 if old["state"] == "applied" else 1


def _with_op(ns: argparse.Namespace, root: Path, kind: str, fn, inputs: dict[str, Any] | None = None):
    """Run ``fn()`` under ``--op-id``: a retried op answers from its first result.

    ``inputs`` are the behaviour-affecting arguments the op id is bound to;
    by default the relevant flags, resolved (a ``--file`` is bound by its
    text, not its path: the same path with new contents is a different op).
    """
    op = getattr(ns, "op_id", None)
    if op:
        if inputs is None:
            inputs = {k: getattr(ns, k) for k in ("model", "harness", "worktree", "text", "note", "session", "offline", "rework")
                      if getattr(ns, k, None)}
        old = begin_op(root, op, kind, _target_of(ns), inputs)
        if old is not None:
            return _replay(ns, op, old)
    try:
        result = fn()
    except Exception as e:
        if op:
            complete_op(root, op, {"error": str(e)}, ok=False)
        raise
    if op:
        complete_op(root, op, result)
    return None


def cmd_delegate(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    state: dict[str, Any] = {}

    def go():
        if ns.rework:   # before delegate, which would return an active worker rather than replace it
            rework_check(root, ns.node_id)
        rec, created = ops.delegate(root, ns.node_id, ns.model, harness=ns.harness,
                                    worktree=Path(ns.worktree) if ns.worktree else None, offline=ns.offline)
        state.update(worker_id=rec.worker_id, created=created, state=rec.state, worktree=rec.worktree,
                     harness=rec.harness, model=rec.model, pid=rec.pid)
        return dict(state)

    rc = _with_op(ns, root, "delegate", go)
    if rc is not None:
        return rc
    verb = "delegated" if state["created"] else "already active"
    return _emit(ns, state, [f"{state['worker_id']}: {verb} — {ns.node_id} on {state['harness']}/{state['model']} "
                             f"in {state['worktree']}", "Poll with `specy-road worker sync`."])


def cmd_list(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    ops.sweep_stalled(root)
    recs = list_records(root, active_only=not ns.all)
    if not recs:
        return _emit(ns, {"workers": []}, ["No workers under work/.workers/."])
    return _emit(ns, *list_view(root, recs, _row, _line))   # held workers whose leaf is over are marked orphaned


def cmd_status(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    rec = load_record(root, ns.worker_id)
    last = events_since(root, rec.worker_id, max(rec.last_event_seq - 3, 0))
    data = _row(rec)
    data["recent_events"] = [e.to_dict() for e in last]
    return _emit(ns, data, [_line(rec), f"  worktree: {rec.worktree}", f"  session: {rec.provider_session_id or '-'}",
                            *(f"  #{e.seq} {e.type} ({e.source}): {e.summary}" for e in last)])


def cmd_events(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    evs = events_since(root, ns.worker_id, ns.since)
    return _emit(ns, {"worker_id": ns.worker_id, "events": [e.to_dict() for e in evs]},
                 [f"#{e.seq} {e.at} {e.type} ({e.source}, {e.authority}): {e.summary}" for e in evs]
                 or [f"no events after #{ns.since}"])


def cmd_sync(ns: argparse.Namespace) -> int:
    return _cmd_sync(ns, emit=_emit)


def _mutate(ns: argparse.Namespace, kind: str, fn, render, inputs: dict[str, Any] | None = None) -> int:
    root = resolve_repo_root(ns)
    out: dict[str, Any] = {}

    def go():
        out.update(fn(root))
        return dict(out)

    rc = _with_op(ns, root, kind, go, inputs)
    return rc if rc is not None else _emit(ns, out, render(out))


def cmd_message(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    try:
        text = Path(ns.file).read_text(encoding="utf-8") if ns.file else ns.text
    except OSError as e:
        # A retry whose file is gone: the outbox answers before anything else is touched.
        old = lookup_op(root, ns.op_id, "message", ns.worker_id) if ns.op_id else None
        if old is None:
            raise WorkerError(f"cannot read --file {ns.file}: {e}") from None
        return _replay(ns, ns.op_id, old)
    return _mutate(ns, "message", lambda root: _row(ops.message(root, ns.worker_id, text, offline=ns.offline,
                                                                 no_queue=ns.no_queue, fix_round=ns.fix_round)),
                   lambda o: ([f"{o['worker_id']}: message queued for the next turn"]
                              if o.get("queued_message") else
                              [f"{o['worker_id']}: message sent; resumed (pid {o['pid']})"]),
                   inputs={"text": text, **({"offline": True} if ns.offline else {}),
                           **({"no_queue": True} if ns.no_queue else {}), **({"fix_round": True} if ns.fix_round else {})})


def cmd_resume(ns: argparse.Namespace) -> int:
    return _mutate(ns, "resume",
                   lambda root: _row(ops.resume(root, ns.worker_id, offline=ns.offline,
                                              ready_only=getattr(ns, "ready_only", False))),
                   lambda o: [f"{o['worker_id']}: resumed (pid {o['pid']})"],
                   inputs={"ready_only": True} if getattr(ns, "ready_only", False) else None)


def cmd_interrupt(ns: argparse.Namespace) -> int:
    ops.interrupt(resolve_repo_root(ns), ns.worker_id)   # raises Unsupported for every CLI adapter
    return 0


def cmd_terminate(ns: argparse.Namespace) -> int:
    return _mutate(ns, "terminate", lambda root: _row(ops.terminate(root, ns.worker_id)),
                   lambda o: [f"{o['worker_id']}: terminated"])


def cmd_handoff(ns: argparse.Namespace) -> int:
    def fn(root):
        rec, cmd = ops.handoff(root, ns.worker_id)
        return {**_row(rec), "resume_command": cmd}
    return _mutate(ns, "handoff", fn, lambda o: [
        f"{o['worker_id']}: leased to you (epoch {o['instruction_epoch']}). In {o['worktree']} run:",
        "  " + render_command(o["resume_command"]),
        "Then `specy-road worker reclaim " + o["worker_id"] + "` when you are done."])


def cmd_reclaim(ns: argparse.Namespace) -> int:
    def fn(root):
        rec, delta = ops.reclaim(root, ns.worker_id, ns.note or "")
        return {**_row(rec), "delta": delta}
    return _mutate(ns, "reclaim", fn, lambda o: [
        f"{o['worker_id']}: reclaimed; epoch {o['instruction_epoch']}; {len(o['delta']['prompts'])} prompt(s) recorded"
        + (f"; flags {o['flags']}" if o["flags"] else ""),
        *(o["delta"]["diff_stat"].splitlines() or ["  no changes since the checkpoint"])])


def cmd_adopt(ns: argparse.Namespace) -> int:
    return _mutate(ns, "adopt", lambda root: _row(ops.adopt(
        root, ns.node, ns.harness, ns.session, worktree=Path(ns.worktree) if ns.worktree else None, model=ns.model)),
        lambda o: [f"{o['worker_id']}: adopted {o['harness']} session {o['provider_session_id']} (observe only)"])


def cmd_reconcile(ns: argparse.Namespace) -> int:
    def fn(root):
        rec, delta = ops.dismiss(root, ns.worker_id, ns.dismiss) if ns.dismiss is not None else ops.reconcile(root, ns.worker_id)
        return {**_row(rec), "delta": delta}
    return _mutate(ns, "reconcile", fn, reconcile_lines, inputs={"dismiss": ns.dismiss} if ns.dismiss is not None else None)


def cmd_open(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    rec = load_record(root, ns.worker_id)
    try:
        cmd = ADAPTERS[rec.harness].human_resume(rec.provider_session_id or "", Path(rec.worktree)) \
            if rec.provider_session_id else None
    except Unsupported:
        cmd = None
    data = {"worker_id": rec.worker_id, "worktree": rec.worktree, "log": str(log_path(root, rec.worker_id)),
            "resume_command": cmd, "lease": rec.lease.get("holder")}
    return _emit(ns, data, [f"worktree: {rec.worktree}", f"log:      {data['log']}",
                            "resume:   " + (render_command(cmd) if cmd else "(no native session)")
                            + ("" if rec.lease.get("holder") == "human" else "  — run `worker handoff` first")])


def _records_for(root: Path, target: str) -> list:
    """The worker ``target`` names, or every worker (attempt) on node ``target``, oldest first."""
    if target.startswith("w-"):
        return [load_record(root, target)]
    recs = [r for r in list_records(root) if r.node_id == target]
    if not recs:
        raise WorkerError(f"no worker for {target}")
    return recs


def cmd_timeline(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    rec = _records_for(root, ns.target)[-1]   # a node id: its latest worker
    data = timeline(rec, [e.to_dict() for e in events_since(root, rec.worker_id)], sync_marks(root).get(rec.worker_id))
    return _emit(ns, data, timeline_lines(data))


def cmd_usage(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    data = usage([(r, [e.to_dict() for e in events_since(root, r.worker_id)]) for r in _records_for(root, ns.target)])
    return _emit(ns, data, usage_lines(data))


def cmd_hook(ns: argparse.Namespace) -> int:
    adapter = HOOKS[ns.format]
    if ns.print_config:
        print(adapter.config)   # stdout stays pure JSON, safe to paste whole
        print(f"# {adapter.notes}", file=sys.stderr)
        return 0
    try:
        sid, prompt = adapter.session_and_prompt(read_payload(sys.stdin.read()))
        if sid and prompt:
            ops.record_hook_prompt(resolve_repo_root(ns), sid, prompt, harness=adapter.harness)
    except Exception as e:  # noqa: BLE001 — a witness must never block the prompt
        print(f"worker hook: ignored ({e})", file=sys.stderr)
    if adapter.allow_output:
        print(adapter.allow_output)
    return 0


def _offline_arg(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--offline", action="store_true",
                    help="Count this checkout's workers only and push no lease (when the integration remote is unreachable)")


def _w(sp: argparse.ArgumentParser, *, op: bool = True) -> None:
    sp.add_argument("worker_id", metavar="W")
    sp.add_argument("--json", action="store_true")
    if op:
        sp.add_argument("--op-id", metavar="ID", help="Idempotency key; a retry returns the first result")
    add_repo_root_arg(sp)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("worker", help="Workers: leaves implemented by sessions on vendor harnesses")
    ws = w.add_subparsers(dest="worker_cmd", required=True)

    sp = ws.add_parser("delegate", help="Launch a worker for a claimed leaf and return at once")
    sp.add_argument("node_id", help="A claimed leaf, or a chore slug (`specy-road chore start`)")
    sp.add_argument("--model", help="Roster id (executor role); a chore's default is its own --model")
    sp.add_argument("--harness", choices=HARNESSES, help="Override the roster entry's harness")
    sp.add_argument("--worktree", help="Run in this checkout (default: this one if it has the claim's branch, else a linked worktree)")
    _offline_arg(sp); sp.add_argument("--rework", action="store_true", help="Take over after blocking reviews or a terminated or failed worker")
    sp.add_argument("--json", action="store_true"); sp.add_argument("--op-id", metavar="ID")
    add_repo_root_arg(sp); sp.set_defaults(func=cmd_delegate)

    sp = ws.add_parser("list", help="Active workers (--all includes finished)")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_list)

    sp = ws.add_parser("status", help="One worker's record and last events"); _w(sp, op=False); sp.set_defaults(func=cmd_status)
    sp = ws.add_parser("events", help="A worker's events after a sequence number"); _w(sp, op=False)
    sp.add_argument("--since", type=int, default=0, metavar="N"); sp.set_defaults(func=cmd_events)

    add_sync_parser(ws, cmd_sync, add_repo_root_arg)

    sp = ws.add_parser("message", help="Send a follow-up prompt (resumes the native session)"); _w(sp)
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", metavar="PATH"); g.add_argument("--text", metavar="TEXT")
    sp.add_argument("--fix-round", action=FixRound, group=g, help="Send the blocking findings and the class-audit block, then any text")
    sp.add_argument("--no-queue", action="store_true",
                    help="Refuse while a turn is still running instead of queueing for the next turn")
    _offline_arg(sp); sp.set_defaults(func=cmd_message)
    sp = ws.add_parser("resume", help="Resume a stopped worker with a continue prompt"); _w(sp); _offline_arg(sp)
    sp.add_argument("--ready-only", action="store_true",
                    help="Resume with a short prompt to write READY for HEAD only (after READY missing)")
    sp.set_defaults(func=cmd_resume)
    sp = ws.add_parser("interrupt", help="Stop the current turn (declared unsupported by the CLI adapters)"); _w(sp, op=False)
    sp.set_defaults(func=cmd_interrupt)
    add_terminate(ws, cmd_terminate, _emit)   # `terminate W`, or `--orphaned` for every held worker whose leaf is over
    sp = ws.add_parser("handoff", help="Lease the worker to a human and print the native resume command"); _w(sp); sp.set_defaults(func=cmd_handoff)
    sp = ws.add_parser("reclaim", help="Take the lease back; record what the human did"); _w(sp)
    sp.add_argument("--note", metavar="TEXT"); sp.set_defaults(func=cmd_reclaim)
    sp = ws.add_parser("reconcile", help="Changed paths since the checkpoint vs the leaf's touch zones"); _w(sp)
    sp.add_argument("--dismiss", metavar="REASON", help="Clear needs_reconcile, recording REASON as an event")
    sp.set_defaults(func=cmd_reconcile)
    sp = ws.add_parser("open", help="Where a human can look: worktree, log, resume command"); _w(sp, op=False)
    sp.set_defaults(func=cmd_open)
    sp = ws.add_parser("timeline", help="Seconds per phase of a worker's latest turn (worker id or node id)")
    sp.add_argument("target", metavar="W|NODE_ID"); sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp); sp.set_defaults(func=cmd_timeline)
    sp = ws.add_parser("usage", help="Tokens and cost per attempt, and the node's total (worker id or node id)")
    sp.add_argument("target", metavar="W|NODE_ID"); sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp); sp.set_defaults(func=cmd_usage)

    sp = ws.add_parser("adopt", help="Register a session the user started natively (observe only)")
    sp.add_argument("--node", required=True); sp.add_argument("--harness", required=True, choices=HARNESSES)
    sp.add_argument("--session", required=True, help="The harness's session/thread/chat id")
    sp.add_argument("--model", default="unknown"); sp.add_argument("--worktree")
    sp.add_argument("--json", action="store_true"); sp.add_argument("--op-id", metavar="ID")
    add_repo_root_arg(sp); sp.set_defaults(func=cmd_adopt)

    sp = ws.add_parser("hook", help="Prompt-submit hook body: record a human's prompt to a worker session")
    sp.add_argument("--format", choices=sorted(HOOKS), required=True)
    sp.add_argument("--print-config", action="store_true", help="Print the snippet that wires this hook into --format's harness")
    add_repo_root_arg(sp); sp.set_defaults(func=cmd_hook)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    try:
        raise SystemExit(ns.func(ns))
    except Unsupported as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(2) from None
    except (WorkerError, LeaseError) as e:
        print(f"error: {e}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
