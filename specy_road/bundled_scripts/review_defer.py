"""``specy-road review defer <NODE_ID> --rca <RCA file>``: a human applies an RCA's ``defer_findings`` record.

Human-only, as ``mark-implementation-reviewed`` is for the human approval: it refuses unless stdin is a
terminal, has no ``--yes``, and asks before writing. It refuses the whole record when any item may not be
deferred (:func:`specy_road.review_deferral.deferral_problems`). Otherwise it adds one follow-up leaf per
distinct ``follow_up_title`` beside the leaf (the ``add-node`` write), records a closed ``decision`` in
``roadmap/decisions.yaml`` naming every deferred finding, the follow-up leaf and the approver, and writes
``DEFERRAL-<round>.yaml`` beside the RCA record; the review gate then counts only those blocks (reviewer and
commit) as resolved. Design: ``docs/design-notes/review-loop-rca.md``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.roadmap_crud_ops import append_node_to_chunk
from specy_road.bundled_scripts.roadmap_crud_prepare import next_sibling_order
from specy_road.bundled_scripts.roadmap_layout import next_child_id
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.roadmap_node_keys import new_node_key
from specy_road.decisions import add_entry, close_entry
from specy_road.git_subprocess import git_text
from specy_road.milestone_lock import assert_pm_nodes_not_milestone_locked
from specy_road.review_deferral import deferral_problems, list_applied, marker_path, write_marker
from specy_road.review_files import reviews_dir
from specy_road.review_rca import loop_state
from specy_road.review_target import full_sha
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def _approver(root: Path) -> str | None:
    name, email = (git_text(["config", f"user.{k}"], root) for k in ("name", "email"))
    return f"{name} <{email}>" if name and email else name or email or None


def _add_follow_ups(root: Path, parent: str | None, items: list[dict[str, Any]]) -> dict[str, str]:
    """One ``Not Started`` task per distinct follow-up title, beside the leaf; title -> new id."""
    groups: dict[str, list[str]] = {}
    for x in items:
        lines = groups.setdefault(x["follow_up_title"].strip(), [])
        if x["follow_up_acceptance"].strip() not in lines:
            lines.append(x["follow_up_acceptance"].strip())
    ids = {}
    for title, acceptance in groups.items():
        node = {"id": next_child_id(load_roadmap(root)["nodes"], parent), "node_key": new_node_key(),
                "parent_id": parent, "type": "task", "title": title, "status": "Not Started",
                "acceptance": acceptance, "sibling_order": next_sibling_order(root, parent, None)}
        append_node_to_chunk(root, None, {k: v for k, v in node.items() if v is not None})
        ids[title] = node["id"]
    return ids


def _checked_record(root: Path, node_id: str, rca_arg: str) -> tuple[Any, str | None]:
    """``(the RCA record, None)`` when it may be applied, else ``(None, why)``; nothing is written."""
    loop = loop_state(root, node_id)
    rca = next((r for r in loop.rcas if r.path.name == Path(rca_arg).name), None)
    if rca is None:
        return None, f"{rca_arg}: no RCA record of {node_id} by that name in {reviews_dir(root, node_id)}"
    if not rca.ok:
        return None, f"{rca.path.name}: invalid — {'; '.join(rca.errors)}"
    if rca.data["recommended_action"]["type"] != "defer_findings":
        return None, f"{rca.path.name} recommends {rca.data['recommended_action']['type']}, not defer_findings"
    if marker_path(root, node_id, rca.path.name).exists():
        return None, f"{rca.path.name} is already applied ({marker_path(root, node_id, rca.path.name).name})"
    others, applied = [r for r in loop.rcas if r is not rca], list_applied(root, node_id)
    problems = [p for x in rca.data["deferred_findings"] for p in deferral_problems(loop.rounds, others, applied, x)]
    if problems:
        return None, (f"{rca.path.name} cannot be applied; nothing was written. A finding on an input class an "
                      "earlier round named, or a correctness finding on an acceptance id an earlier round "
                      "passed, is fixed in this leaf:\n" + "\n".join(f"  - {p}" for p in problems))
    return rca, None


def cmd_review_defer(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    if not sys.stdin.isatty():
        return _fail("review defer is human-only: run it yourself in an interactive terminal. An agent or "
                     "unattended run may not apply a deferral, and there is no --yes.")
    rca, why = _checked_record(root, ns.node_id, ns.rca)
    if why:
        return _fail(why)
    approver = _approver(root)
    if not approver:
        return _fail("set git user.name or user.email: the decision entry names the approver")
    nodes = load_roadmap(root)["nodes"]
    leaf = next((n for n in nodes if n.get("id") == ns.node_id), None)
    if leaf is None:
        return _fail(f"no roadmap node {ns.node_id!r}")
    parent = leaf.get("parent_id")
    try:
        if parent:
            assert_pm_nodes_not_milestone_locked(nodes, parent)
    except ValueError as e:
        return _fail(str(e))
    items = rca.data["deferred_findings"]
    print(f"{rca.path.name} defers {len(items)} finding(s) of {ns.node_id} to a follow-up leaf:")
    for x in items:
        print(f"  - {x['finding']} [{x['category']} on {x['acceptance_id']}, input class {x['input_class']!r}]"
              f" -> {x['follow_up_title']!r}: {x['follow_up_acceptance']}")
    if input(f"Apply as {approver}? [y/N] ").strip().lower() not in ("y", "yes"):
        print("Aborted (nothing written).")
        return 0
    try:
        ids = _add_follow_ups(root, parent if isinstance(parent, str) else None, items)
    except (ValueError, SystemExit) as e:
        return _fail(f"could not add the follow-up leaf: {e}")
    answer = f"Deferred by {approver} from {rca.path.name}: " + "; ".join(
        f"{x['finding']} (input class {x['input_class']!r}) -> {ids[x['follow_up_title'].strip()]}" for x in items)
    entry = add_entry(
        root, node_id=ns.node_id, kind="decision",
        summary=f"Defer {len(items)} review finding(s) of {ns.node_id} to {', '.join(sorted(set(ids.values())))}",
        why_now=f"{rca.path.name} recommends defer_findings: {rca.data['recommended_action']['instructions']}",
        options=[{"label": "defer", "effect": "the follow-up leaf owns the findings; the gate stops counting "
                  "those blocks at their commit"},
                 {"label": "keep fixing", "effect": "the findings stay must-fix in this leaf"}],
        recommendation="defer", recommendation_reason="the findings name input classes no earlier round named",
        default_if_unanswered="keep fixing")
    close_entry(root, entry["id"], answer, sheet_text=None, ledger_only=True)
    marker = marker_path(root, ns.node_id, rca.path.name)
    write_marker(marker, {
        "node_id": ns.node_id, "rca": rca.path.name, "decision": entry["id"], "approver": approver,
        "follow_up": sorted(set(ids.values())),
        "deferred": [{"reviewer": x["reviewer"], "commit": full_sha(root, x["commit"]) or x["commit"],
                      "finding": x["finding"], "category": x["category"], "acceptance_id": x["acceptance_id"],
                      "input_class": x["input_class"]} for x in items]})
    print(f"[ok] added {', '.join(sorted(set(ids.values())))}; decision {entry['id']} closed; wrote {marker}")
    print("  Commit roadmap/ (the follow-up leaf and decisions.yaml), then "
          f"`specy-road handoff status {ns.node_id}`.")
    return 0


def add_parser(rsub: Any) -> None:
    sp = rsub.add_parser("defer", help="Human-only: apply an RCA's defer_findings record (follow-up leaf, "
                                       "decision entry, gate marker)")
    sp.add_argument("node_id")
    sp.add_argument("--rca", required=True, help="The RCA-<round>.md record to apply")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_review_defer)
