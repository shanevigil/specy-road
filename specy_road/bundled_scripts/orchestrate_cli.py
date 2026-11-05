#!/usr/bin/env python3
"""CLI for `specy-road orchestrate plan [PARENT]`.

Prints the ref the roster was read from, then, per parallel batch, which roster
model should coordinate, execute, and review each ready leaf, with the reason
for each pick, and names every leaf the roster cannot staff under the current
policy, with each `policy.strong_review` item a leaf's touch zones meet and the
reviewers that can satisfy it. Ready means what pickup and `grind-session --plan`
mean, so leaves pickup skips are listed apart, not assigned. Exit 1 when any
ready leaf is unstaffable, so a coordinator script stops before dispatching. With no
rostered coordinator the line reads `coordinator: this session`; `--spread` assigns
executors round-robin among the capable entries by leaf order. Assigns
only: dispatch is `specy-road prompt`. Ends with the human's active routing
preferences from `roadmap/decisions.yaml`, which the plan does not apply itself.
`--roster-from-worktree` plans with the working tree's roster as a dry run: a banner
comes first and `--json` carries `roster_ref: worktree`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from specy_road.decisions import format_preference
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.orchestrate_plan import OrchestrationPlan, build_orchestration_plan
from specy_road.orchestration_pinned import WORKTREE_REF
from specy_road.planning_scaffold_check import needs_approach_line
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root

DRY_RUN_BANNER = "DRY RUN: roster from the working tree, nothing may launch from this plan"


def render(plan: OrchestrationPlan, needs_approach: str | None = None) -> list[str]:
    pol = plan.policy
    unit = "distinct-family" if pol.get("reviewers_distinct_families") else "any-family"
    dry = plan.roster_ref == WORKTREE_REF
    lines = [DRY_RUN_BANNER] if dry else []
    lines += [f"policy: {pol.get('reviewers_required')} {unit} reviewer(s)"
              + (f"; scope {plan.under}" if plan.under else ""),
              # Routing reads the integration branch's roster, not necessarily the file you are looking at.
              "roster: roadmap/orchestration.yaml "
              + ("in the working tree (--roster-from-worktree)" if dry else
                 f"at {plan.roster_ref}" if plan.roster_ref else "in the working tree (not a git checkout)")]
    if plan.local_roster:
        lines.append("local roster entries (roadmap/orchestration.local.yaml roster_add, this clone only): "
                     + ", ".join(plan.local_roster))
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
            coord = a.coordinator or ("this session" if a.coordinator_is_session else "-")
            lines.append(f"    coordinator: {coord}   executor: {a.executor or '-'}   "
                         f"reviewers: {', '.join(a.reviewers) or '-'}")
            lines += [f"    strong review {s['item']}: one approval from {', '.join(s['require_one_of'])}; "
                      f"can satisfy it: {', '.join(s['can_satisfy']) or 'none'}" for s in a.strong_review]
            lines += [f"    {n}" for n in a.notes]
            lines += [f"    ! {p}" for p in a.problems]
    if plan.blocked:
        lines.append(f"blocked (not assigned): {', '.join(plan.blocked)}")
    if plan.active:
        lines.append(f"active claims (not reassigned): {', '.join(plan.active)}")
    if plan.unauthored:
        lines.append(f"unauthored (not assigned; pickup skips them): {', '.join(plan.unauthored)}")
    if needs_approach:
        lines.append(needs_approach)
    return lines + preference_lines(plan)


def preference_lines(plan: OrchestrationPlan) -> list[str]:
    if plan.preferences_error:
        return [f"! preferences: {plan.preferences_error}"]
    if not plan.preferences_not_applied:
        return []
    lines = ["preferences not applied automatically (roadmap/decisions.yaml; "
             "apply them when you delegate or launch a review):"]
    for p in plan.preferences_not_applied:
        lines += [f"  {line}" for line in format_preference(p).splitlines()]
        lines += [f"    ! {n} (roster)" for n in p["roster_notes"]]
    return lines


def cmd_plan(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    today = date.fromisoformat(ns.today) if ns.today else None
    plan, err = build_orchestration_plan(root, under=ns.parent, today=today, spread=ns.spread,
                                         roster_from_worktree=ns.roster_from_worktree)
    if err or plan is None:
        print(f"error: {err}", file=sys.stderr)
        return 1
    if ns.json:
        if ns.roster_from_worktree:   # stdout stays JSON; roster_ref says worktree there
            print(DRY_RUN_BANNER, file=sys.stderr)
        print(json.dumps(plan.to_dict(), indent=2))
    else:
        nodes = load_roadmap(root)["nodes"]
        needs = needs_approach_line(root, nodes, list(plan.unauthored))
        print("\n".join(render(plan, needs)))
    return 0 if plan.ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    orch = sub.add_parser("orchestrate", help="Model assignment for ready leaves")
    osub = orch.add_subparsers(dest="orchestrate_cmd", required=True)
    plan = osub.add_parser("plan", help="Assign coordinator, executor, and reviewers per ready leaf")
    plan.add_argument("parent", nargs="?", help="Limit to leaves under this node (default: whole roadmap)")
    plan.add_argument("--today", help="YYYY-MM-DD, for availability and substitution checks")
    plan.add_argument("--spread", action="store_true",
                      help="Assign executors round-robin among the capable, available entries by leaf order, "
                           "instead of always the cheapest")
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--roster-from-worktree", action="store_true",
                      help="Dry run: plan with the working tree's roadmap/orchestration.yaml (uncommitted); "
                           "nothing may launch from this plan, and delegation never reads it")
    add_repo_root_arg(plan)
    plan.set_defaults(func=cmd_plan)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
