#!/usr/bin/env python3
"""CLI for `specy-road why-blocked` and `specy-road list-gates`.

Both answer questions `grind-session --plan` could already answer, but only by
rendering a whole session plan and reading it. Asking about one node — or about
the gates alone — is common enough during a grind to deserve its own entrypoint.

For a leaf with nothing in its way, `why-blocked` still asks that plan whether
it holds the leaf out of a parallel batch for sharing a touch zone, so the two
commands never disagree about one leaf.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from specy_road.bundled_scripts.roadmap_explain import DependencyNode, Explanation, explain, open_gates
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.session_plan_git import gather_session_plan
from specy_road.bundled_scripts.session_plan_render import zone_overlaps
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root

#: Exit 1 for "the question has an answer and the answer is: blocked". A caller
#: scripting around this wants to branch on that without parsing prose.
EXIT_BLOCKED = 1
EXIT_BAD_NODE = 2

#: Pickup (``do-next-available-task``, and the ``grind-session`` loop through it)
#: claims the head of ``ready`` and never reads ``parallel_batches``, so a
#: touch-zone hold shapes only the plan's dispatch sets. A held leaf therefore
#: still exits 0: it is pickable, just better dispatched after its holder.
PICKUP_HONOURS_ZONE_HOLDS = False


def _render_chain(deps: list[DependencyNode], indent: int = 1) -> list[str]:
    lines: list[str] = []
    for d in deps:
        tag = "GATE" if d.is_gate else d.status
        claimed = f" — claimed on {d.claimed_by}" if d.claimed_by else ""
        title = f" {d.title}" if d.title else ""
        lines.append(f"{'  ' * indent}- {d.node_id} [{tag}]{title}{claimed}")
        lines.extend(_render_chain(d.waiting_on, indent + 1))
    return lines


def plan_hold(root, node_id: str) -> dict | None:
    """The touch-zone hold ``grind-session --plan`` puts on ``node_id``, or ``None``.

    Read from the plan ``--plan`` prints without ``--under`` (git-enriched, in
    pickup order), via the same ``zone_overlaps`` its "Held for the next batch"
    section renders. A scoped plan can hold fewer leaves: a holder outside the
    scope is not in it.
    """
    _nodes, _reg, plan = gather_session_plan(root, None)
    for h in zone_overlaps(plan):
        if h["node_id"] == node_id:
            return {
                "waits_for": h["waits_for"],
                "zones": list(h["zones"]),
                "pickup_honours": PICKUP_HONOURS_ZONE_HOLDS,
            }
    return None


def _render_hold(node_id: str, hold: dict) -> list[str]:
    holder = hold["waits_for"]
    mine, theirs = hold["zones"]
    honour = (
        "Pickup honours this hold."
        if hold["pickup_honours"]
        else (
            "Pickup does not honour this hold: do-next-available-task and the "
            "grind-session loop claim in ready order regardless of touch zones, "
            f"so {node_id} can still be claimed while {holder} is open. Dispatch "
            f"it once {holder} lands to keep the two off the same files."
        )
    )
    return [
        "",
        f"grind-session --plan holds {node_id} for a later parallel batch, "
        f"behind {holder}: touch zone `{mine}` overlaps `{theirs}`.",
        honour,
    ]


def _render_explanation(exp: Explanation, hold: dict | None = None) -> str:
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
    if hold is not None:
        lines += _render_hold(exp.node_id, hold)
    return "\n".join(lines)


def cmd_why_blocked(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    nodes = load_roadmap(root)["nodes"]
    reg = read_registry(registry_path(root))
    exp = explain(nodes, reg, ns.node_id)
    hold = plan_hold(root, ns.node_id) if exp.state == "ready" else None
    if ns.json:
        print(json.dumps({**asdict(exp), "plan_hold": hold}, indent=2))
    else:
        print(_render_explanation(exp, hold))
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
            "codename. For a pickable leaf, also whether grind-session --plan "
            "holds it behind another leaf that shares a touch zone, and that "
            "pickup does not honour that hold. Exits 1 when the node really is "
            "blocked or gated, 0 when it is pickable (held or not) or already "
            "closed, 2 when the id does not exist."
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
