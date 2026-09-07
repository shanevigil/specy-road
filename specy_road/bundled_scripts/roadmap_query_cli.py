#!/usr/bin/env python3
"""CLI for `specy-road why-blocked` and `specy-road list-gates`.

Both answer questions `grind-session --plan` could already answer, but only by
rendering a whole session plan and reading it. Asking about one node — or about
the gates alone — is common enough during a grind to deserve its own entrypoint.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from specy_road.bundled_scripts.roadmap_explain import DependencyNode, Explanation, explain, open_gates
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root

#: Exit 1 for "the question has an answer and the answer is: blocked". A caller
#: scripting around this wants to branch on that without parsing prose.
EXIT_BLOCKED = 1
EXIT_BAD_NODE = 2


def _render_chain(deps: list[DependencyNode], indent: int = 1) -> list[str]:
    lines: list[str] = []
    for d in deps:
        tag = "GATE" if d.is_gate else d.status
        claimed = f" — claimed on {d.claimed_by}" if d.claimed_by else ""
        title = f" {d.title}" if d.title else ""
        lines.append(f"{'  ' * indent}- {d.node_id} [{tag}]{title}{claimed}")
        lines.extend(_render_chain(d.waiting_on, indent + 1))
    return lines


def _render_explanation(exp: Explanation) -> str:
    header = f"{exp.node_id}" + (f" — {exp.title}" if exp.title else "")
    lines = [header, "", exp.summary]
    if exp.waiting_on:
        lines += ["", "waiting on:"]
        lines += _render_chain(exp.waiting_on)
        lines += [
            "",
            "Nested entries are what those dependencies are themselves waiting "
            "on. Work the deepest item first.",
        ]
    if exp.state == "gated":
        lines += [
            "",
            "A gate needs a human decision; it is never auto-picked. Clear it "
            "with specy-road set-gate-status <NODE_ID> --status Complete.",
        ]
    return "\n".join(lines)


def cmd_why_blocked(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    nodes = load_roadmap(root)["nodes"]
    reg = read_registry(registry_path(root))
    exp = explain(nodes, reg, ns.node_id)
    if ns.json:
        print(json.dumps(asdict(exp), indent=2))
    else:
        print(_render_explanation(exp))
    if exp.state == "unknown":
        return EXIT_BAD_NODE
    return EXIT_BLOCKED if exp.state in ("blocked", "gated") else 0


def cmd_list_gates(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    nodes = load_roadmap(root)["nodes"]
    gates = open_gates(nodes, ns.under)
    if ns.json:
        print(json.dumps([asdict(g) for g in gates], indent=2))
        return 0
    if not gates:
        scope = f" under {ns.under}" if ns.under else ""
        print(f"No open gates{scope}.")
        return 0
    scope = f" (blocking work under {ns.under})" if ns.under else ""
    print(f"Open gates{scope}:\n")
    for g in gates:
        title = f" — {g.title}" if g.title else ""
        print(f"- {g.node_id} [{g.status}]{title}")
        if g.blocks:
            print(f"    blocks: {', '.join(g.blocks)}")
    print(
        "\nClear one with: specy-road set-gate-status <NODE_ID> --status Complete"
    )
    return 0


def _add_why_blocked(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "why-blocked",
        help="Explain why one node is not pickable",
        description=(
            "Why a node cannot be picked up: the transitive chain of unmet "
            "dependencies, an open gate, an existing claim, or a missing "
            "codename. Exits 1 when the node really is blocked or gated, 0 when "
            "it is pickable or already closed, 2 when the id does not exist."
        ),
    )
    p.add_argument("node_id", metavar="NODE_ID")
    p.add_argument("--json", action="store_true", help="Machine-readable output.")
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_why_blocked)


def _add_list_gates(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "list-gates",
        help="List gate nodes that are not Complete",
        description=(
            "Gate nodes still holding work back, and what each one blocks. "
            "--under scopes by the work being blocked, not by where the gate "
            "lives, because a phase is routinely held by a gate defined "
            "elsewhere in the graph."
        ),
    )
    p.add_argument(
        "--under", default=None, metavar="NODE_ID",
        help="Only gates blocking work in this node's subtree.",
    )
    p.add_argument("--json", action="store_true", help="Machine-readable output.")
    add_repo_root_arg(p)
    p.set_defaults(func=cmd_list_gates)


def build_parser() -> argparse.ArgumentParser:
    """One parser for both commands.

    Unlike the other forwarded scripts this keeps the command name in ``argv``
    and lets a subparser consume it, because the two share the graph-loading
    code and neither is big enough to own a file.
    """
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="query_cmd", required=True)
    _add_why_blocked(sub)
    _add_list_gates(sub)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
