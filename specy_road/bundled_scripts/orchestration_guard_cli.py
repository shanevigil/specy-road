"""``specy-road orchestration guard``: role-based git/gh/worktree/cloud denials (M8.5)."""

from __future__ import annotations

import argparse
import json
import sys

from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.orchestration_guard_adapters import ADAPTERS
from specy_road.orchestration_role_guard import ROLE_CHOICES, decide_role, orchestration_role
from specy_road.tool_call_guard import read_payload


def _answer(answer: tuple) -> int:
    out, err, code = answer
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    return code


def cmd_orchestration_guard(ns: argparse.Namespace) -> int:
    adapter = ADAPTERS[ns.format]
    role = ns.role or orchestration_role()
    if ns.print_config:
        cfg = adapter.config_reviewer if ns.config_role == "reviewer" else adapter.config_executor
        print(cfg)
        print(f"# {adapter.notes}", file=sys.stderr)
        return 0
    try:
        resolve_repo_root(ns)
        command = ns.command or adapter.extract(read_payload(sys.stdin.read()))
        if not command:
            return _answer(adapter.on_allow(None))
        if role not in ROLE_CHOICES:
            return _answer(adapter.on_allow(None))
        v = decide_role(command, role=role)
    except Exception as e:  # noqa: BLE001 — fail closed
        return _answer(adapter.on_deny(f"internal error ({e}); refusing rather than failing open"))
    if v.denied:
        return _answer(adapter.on_deny(v.reason))
    return _answer(adapter.on_allow(None))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road orchestration guard")
    p.add_argument("--format", choices=sorted(ADAPTERS), required=True)
    p.add_argument("--command", metavar="CMD", help="Judge this command (default: harness stdin payload)")
    p.add_argument("--role", choices=sorted(ROLE_CHOICES), help="Override $SPECY_ROAD_ORCHESTRATION_ROLE")
    p.add_argument(
        "--print-config",
        action="store_true",
        help="Print hook JSON for --config-role on stdout; caveats on stderr",
    )
    p.add_argument(
        "--config-role",
        choices=("executor", "reviewer"),
        default="executor",
        help="Which role snippet --print-config emits (default: executor)",
    )
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_orchestration_guard)
    return p


def _guard_argv(argv: list[str]) -> list[str]:
    """Drop ``orchestration guard`` prefixes from argv forwarded by :mod:`specy_road.cli`."""
    if len(argv) >= 2 and argv[0] == "orchestration" and argv[1] == "guard":
        return argv[2:]
    if argv and argv[0] == "guard":
        return argv[1:]
    if not argv or argv[0].startswith("-"):
        return argv
    print("usage: specy-road orchestration guard --format …", file=sys.stderr)
    raise SystemExit(2)


def main(argv: list[str] | None = None) -> None:
    argv = _guard_argv(list(sys.argv[1:] if argv is None else argv))
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
