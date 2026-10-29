#!/usr/bin/env python3
"""CLI for `specy-road orchestrate plan [PARENT]`.

Prints the ref the roster was read from, then, per parallel batch, which roster
model should coordinate, execute, and review each ready leaf, with the reason
for each pick, and names every leaf the roster cannot staff under the current
policy. Exit 1 when any ready leaf
is unstaffable, so a coordinator script stops before dispatching. Assigns
only: dispatch is `specy-road prompt`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from specy_road.orchestrate_plan import OrchestrationPlan, build_orchestration_plan
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def render(plan: OrchestrationPlan) -> list[str]:
    pol = plan.policy
    unit = "distinct-family" if pol.get("reviewers_distinct_families") else "any-family"
    lines = [f"policy: {pol.get('reviewers_required')} {unit} reviewer(s)"
             + (f"; scope {plan.under}" if plan.under else ""),
             # Routing reads the integration branch's roster, not necessarily the file you are looking at.
             "roster: roadmap/orchestration.yaml "
             + (f"at {plan.roster_ref}" if plan.roster_ref else "in the working tree (not a git checkout)")]
    if plan.roster_drift:
        lines.append(f"! {plan.roster_drift}")
    if not plan.batches:
        lines.append("no ready leaves to assign"
                     + (f" ({len(plan.blocked)} blocked, {len(plan.active)} active)" if plan.blocked or plan.active else ""))
    for i, batch in enumerate(plan.batches):
        lines.append(f"batch {i}:")
        for a in batch:
            tag = "" if a.sensitivity == "public" and a.eligibility == "any" else f"  [{a.sensitivity}, {a.eligibility}]"
            lines.append(f"  {a.node_id}{tag}")
            lines.append(f"    coordinator: {a.coordinator or '-'}   executor: {a.executor or '-'}   "
                         f"reviewers: {', '.join(a.reviewers) or '-'}")
            lines += [f"    {n}" for n in a.notes]
            lines += [f"    ! {p}" for p in a.problems]
    if plan.blocked:
        lines.append(f"blocked (not assigned): {', '.join(plan.blocked)}")
    if plan.active:
        lines.append(f"active claims (not reassigned): {', '.join(plan.active)}")
    return lines


def cmd_plan(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    today = date.fromisoformat(ns.today) if ns.today else None
    plan, err = build_orchestration_plan(root, under=ns.parent, today=today)
    if err or plan is None:
        print(f"error: {err}", file=sys.stderr)
        return 1
    if ns.json:
        print(json.dumps(plan.to_dict(), indent=2))
    else:
        print("\n".join(render(plan)))
    return 0 if plan.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    orch = sub.add_parser("orchestrate", help="Model assignment for ready leaves")
    osub = orch.add_subparsers(dest="orchestrate_cmd", required=True)
    plan = osub.add_parser("plan", help="Assign coordinator, executor, and reviewers per ready leaf")
    plan.add_argument("parent", nargs="?", help="Limit to leaves under this node (default: whole roadmap)")
    plan.add_argument("--today", help="YYYY-MM-DD, for availability and substitution checks")
    plan.add_argument("--json", action="store_true")
    add_repo_root_arg(plan)
    plan.set_defaults(func=cmd_plan)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
