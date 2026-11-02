#!/usr/bin/env python3
"""CLI for ``specy-road decisions add|list|close`` (M11.34)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir, resolve_planning_path
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.decisions import (
    add_entry,
    close_entry,
    decisions_path,
    format_open_entry,
    open_entries,
    read_decisions,
    schema_errors,
    schema_path_for_write,
    sort_for_list,
)
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def _parse_option(raw: str) -> dict[str, str]:
    if "|" not in raw:
        print(f"error: --option must be label|effect, got {raw!r}", file=sys.stderr)
        raise SystemExit(1)
    label, effect = raw.split("|", 1)
    label, effect = label.strip(), effect.strip()
    if not label or not effect:
        print(f"error: --option label and effect must be non-empty: {raw!r}", file=sys.stderr)
        raise SystemExit(1)
    return {"label": label, "effect": effect}


def _sheet_for_node(root: Path, node_id: str) -> tuple[str, str]:
    by_id = {n["id"]: n for n in load_roadmap(root)["nodes"]}
    node = by_id.get(node_id)
    if not node:
        print(f"error: unknown node {node_id!r}", file=sys.stderr)
        raise SystemExit(1)
    rel = normalize_planning_dir(node.get("planning_dir") or "")
    if not rel:
        print(f"error: node {node_id} has no planning_dir", file=sys.stderr)
        raise SystemExit(1)
    path = resolve_planning_path(root, rel)
    try:
        return rel, path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"error: could not read {rel}: {e}", file=sys.stderr)
        raise SystemExit(1) from e


def cmd_add(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    options = [_parse_option(o) for o in ns.option]
    entry = add_entry(
        root,
        node_id=ns.node,
        kind=ns.kind,
        summary=ns.summary,
        why_now=ns.why,
        options=options,
        recommendation=ns.recommendation,
        recommendation_reason=ns.recommendation_reason,
        default_if_unanswered=ns.default,
        decision_id=ns.id,
        needed_by=ns.needed_by,
        asked=ns.asked,
    )
    print(f"added {entry['id']} (open) → {decisions_path(root)}")
    return 0


def cmd_list(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    path = decisions_path(root)
    doc = read_decisions(path)
    errs = schema_errors(doc, schema_path_for_write(root))
    if errs:
        for line in errs:
            print(f"decisions.schema: {line}", file=sys.stderr)
        return 1
    entries = sort_for_list(open_entries(doc))
    if ns.json:
        print(json.dumps(entries, indent=2))
        return 0
    if not entries:
        print("No open decisions in roadmap/decisions.yaml.")
        return 0
    for e in entries:
        print(format_open_entry(e))
        print()
    return 0


def cmd_close(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    doc = read_decisions(decisions_path(root))
    target = next((e for e in doc.get("entries") or [] if isinstance(e, dict) and e.get("id") == ns.decision_id), None)
    if not target:
        print(f"error: no decision {ns.decision_id!r} in roadmap/decisions.yaml", file=sys.stderr)
        return 1
    _, sheet = _sheet_for_node(root, target["node"])
    close_entry(root, ns.decision_id, ns.answer, sheet_text=sheet)
    print(f"closed {ns.decision_id!r}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    dec = sub.add_parser("decisions", help="Tracked open human decisions in roadmap/decisions.yaml")
    dsub = dec.add_subparsers(dest="decisions_cmd", required=True)

    add = dsub.add_parser("add", help="Open a self-contained human decision in the ledger")
    add.add_argument("node", metavar="NODE", help="Roadmap node id this decision belongs to")
    add.add_argument("--kind", required=True, choices=["decision", "human-action"])
    add.add_argument("--summary", required=True, help="Plain-words summary")
    add.add_argument("--why", required=True, help="Why now and what it blocks")
    add.add_argument("--option", action="append", required=True, metavar="LABEL|EFFECT",
                     help="Repeat for each option (label|effect)")
    add.add_argument("--recommendation", required=True)
    add.add_argument("--recommendation-reason", required=True)
    add.add_argument("--default", required=True, dest="default", help="Default if unanswered")
    add.add_argument("--id", dest="id", help="Decision id (default: next D#)")
    add.add_argument("--needed-by", help="ISO date by which an answer is needed")
    add.add_argument("--asked", help="ISO date when asked (default: today)")
    add_repo_root_arg(add)
    add.set_defaults(func=cmd_add)

    lst = dsub.add_parser("list", help="List open entries ordered by needed-by")
    lst.add_argument("--json", action="store_true")
    add_repo_root_arg(lst)
    lst.set_defaults(func=cmd_list)

    close = dsub.add_parser("close", help="Close an entry after its answer is on the planning sheet")
    close.add_argument("decision_id", metavar="ID")
    close.add_argument("--answer", required=True)
    add_repo_root_arg(close)
    close.set_defaults(func=cmd_close)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
