#!/usr/bin/env python3
"""CLI for `specy-road session start|touch|end|list|check`.

An agent announces itself before its first edit (``start``), renews on long
work (``touch``), and withdraws when done (``end``). ``list`` is what the
others read; ``handoff status`` shows the same. ``check`` is the commit guard:
exit 1 when the staged paths (or ``--path`` ones) overlap another live
session's, so a pre-commit hook can refuse a commit that would land on
someone else's work. All of it is advisory past that one exit code.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.git_subprocess import git_stdout
from specy_road.session_presence import (
    DEFAULT_TTL_HOURS,
    conflicts,
    default_agent_id,
    end_session,
    list_sessions,
    start_session,
    warn_lines,
)
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.tool_call_guard import ADAPTERS, decide, read_payload


def _agent(ns: argparse.Namespace) -> str:
    return ns.agent or default_agent_id()


def cmd_start(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    try:
        # `touch` without --path renews and keeps the paths; `start` without them records none.
        paths = ns.path if (ns.path or ns.session_cmd != "touch") else None
        s = start_session(root, _agent(ns), paths=paths, note=ns.note or "",
                          ttl_hours=ns.ttl_hours, worktree=Path.cwd())
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"session {s.agent}: {len(s.paths)} path(s), until {s.expires} ({s.path})")
    for line in warn_lines(conflicts(root, s.paths, exclude=s.agent), what="your paths"):
        print(line, file=sys.stderr)
    return 0


def cmd_end(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    agent = _agent(ns)
    print(f"session {agent}: {'ended' if end_session(root, agent) else 'no record'}")
    return 0


def cmd_list(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    sessions = list_sessions(root, live_only=not ns.all)
    if ns.json:
        print(json.dumps([s.to_dict() for s in sessions], indent=2))
        return 0
    if not sessions:
        print("No live sessions under work/.sessions/.")
    for s in sessions:
        state = "" if s.is_live() else "  (expired)"
        print(f"{s.agent:<28} {s.branch or '-':<32} until {s.expires}{state}")
        print(f"  {s.worktree}")
        print(f"  paths: {', '.join(s.paths) or '-'}" + (f"  — {s.note}" if s.note else ""))
    return 0


def _staged(root: Path) -> list[str]:
    out = git_stdout(["diff", "--cached", "--name-only"], root) or ""
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def cmd_check(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    paths = list(ns.path) or _staged(root)
    if not paths:
        print("session check: nothing staged, nothing to check")
        return 0
    found = conflicts(root, paths, exclude=_agent(ns))
    if not found:
        print(f"session check: {len(paths)} path(s) clear of other live sessions")
        return 0
    for line in warn_lines(found, what="staged paths"):
        print(line, file=sys.stderr)
    print("session check: refuse — another live session owns these paths. Coordinate, or wait for "
          "its record to expire; `specy-road session list` shows who.", file=sys.stderr)
    return 1


def _answer(answer: tuple) -> int:
    out, err, code = answer
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return code


def cmd_guard(ns: argparse.Namespace) -> int:
    """Allow or deny one shell command; the body of every harness hook adapter.

    With ``--command`` the verdict is printed for a human. With ``--format``
    the command is read from the harness's stdin payload and the answer goes
    out the way that harness reads it; a payload with nothing to judge is a
    plain allow. An internal error is answered as a deny: a guard must not
    fail open quietly.
    """
    adapter = ADAPTERS[ns.format]
    if ns.print_config:
        print(adapter.config)   # stdout stays pure JSON, safe to paste whole
        print(f"# {adapter.notes}", file=sys.stderr)
        return 0
    try:
        root = resolve_repo_root(ns)
        command = ns.command or adapter.extract(read_payload(sys.stdin.read()))
        if not command:
            return _answer(adapter.on_allow(None))
        v = decide(root, command, agent=_agent(ns), always=ns.always)
    except Exception as e:  # noqa: BLE001 — fail closed, loudly
        return _answer(adapter.on_deny(f"internal error ({e}); refusing rather than failing open"))
    if v.allowed:
        return _answer(adapter.on_allow(v.reason or None))
    return _answer(adapter.on_deny(v.reason))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    sess = sub.add_parser("session", help="Presence records for agent sessions in this checkout")
    ssub = sess.add_subparsers(dest="session_cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--agent", help="Session id (default: $SPECY_ROAD_AGENT_ID, else <user>-s<POSIX session id>)")
        add_repo_root_arg(sp)

    for name, help_ in (("start", "Announce this session and the paths it will edit (renews an existing record)"),
                        ("touch", "Renew this session's expiry (same as start)")):
        sp = ssub.add_parser(name, help=help_)
        sp.add_argument("--path", action="extend", nargs="+", default=[], metavar="PATH",
                        help="Repo-relative paths or globs (several after one --path, or repeat the flag)")
        sp.add_argument("--note", help="One line on what you are doing")
        sp.add_argument("--ttl-hours", type=float, default=DEFAULT_TTL_HOURS)
        common(sp)
        sp.set_defaults(func=cmd_start)

    sp = ssub.add_parser("end", help="Remove this session's record")
    common(sp)
    sp.set_defaults(func=cmd_end)

    sp = ssub.add_parser("list", help="Live sessions (--all includes expired)")
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--json", action="store_true")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_list)

    sp = ssub.add_parser("check", help="Exit 1 if staged paths (or --path) overlap another live session; a pre-commit guard")
    sp.add_argument("--path", action="extend", nargs="+", default=[], metavar="PATH")
    common(sp)
    sp.set_defaults(func=cmd_check)

    sp = ssub.add_parser("guard", help="Deny a shell command that is destructive in a shared checkout; the harness hook body")
    sp.add_argument("--command", metavar="CMD", help="Judge this command (default: read the harness payload from stdin)")
    sp.add_argument("--format", choices=sorted(ADAPTERS), default="generic",
                    help="Which harness's stdin payload and exit codes to use (default: generic)")
    sp.add_argument("--always", action="store_true", help="Deny even when no other session is live")
    sp.add_argument("--print-config", action="store_true", help="Print the snippet that wires this guard into --format's harness")
    common(sp)
    sp.set_defaults(func=cmd_guard)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
