#!/usr/bin/env python3
"""CLI for ``specy-road decisions add|list|close`` (M11.34; preferences M11.58)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from specy_road.bundled_scripts.planning_artifacts import normalize_planning_dir, resolve_planning_path
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.decisions import (
    PREFERENCE,
    active_preferences,
    add_entry,
    add_preference,
    close_entry,
    decisions_path,
    format_open_entry,
    format_preference,
    open_questions,
)
from specy_road.decisions_local import LOCAL, SHARED, load_merged, next_free_id
from specy_road.model_profiles import ROLES
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


_QUESTION_FLAGS = (("node", "NODE"), ("why", "--why"), ("option", "--option"),
                   ("recommendation", "--recommendation"),
                   ("recommendation_reason", "--recommendation-reason"), ("default", "--default"))
_QUESTION_ONLY = (("option", "--option"), ("recommendation", "--recommendation"),
                  ("recommendation_reason", "--recommendation-reason"), ("default", "--default"),
                  ("needed_by", "--needed-by"))
_PREFERENCE_ONLY = (("role", "--role"), ("model", "--model"), ("applies_to", "--applies-to"),
                    ("expires", "--expires"), ("supersedes", "--supersedes"))


def _kind_flag_error(ns: argparse.Namespace) -> str | None:
    """Which flags this kind needs or refuses; argparse cannot say it per ``--kind``."""
    if ns.kind == PREFERENCE:
        bad = [flag for attr, flag in _QUESTION_ONLY if getattr(ns, attr)]
        return f"--kind preference does not take {', '.join(bad)}" if bad else None
    missing = [flag for attr, flag in _QUESTION_FLAGS if not getattr(ns, attr)]
    if missing:
        return f"--kind {ns.kind} needs {', '.join(missing)}"
    bad = [flag for attr, flag in _PREFERENCE_ONLY if getattr(ns, attr)]
    return f"{', '.join(bad)} apply only to --kind preference" if bad else None


def _add_preference(root: Path, ns: argparse.Namespace) -> int:
    try:
        entry = add_preference(
            root, summary=ns.summary, role=ns.role, models=ns.model, applies_to=ns.applies_to,
            expires=ns.expires, why=ns.why, node_id=ns.node, preference_id=ns.id,
            supersedes=ns.supersedes, asked=ns.asked, local=ns.local,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    tail = f"; closed {ns.supersedes}" if ns.supersedes else ""
    print(f"added {entry['id']} (preference){tail} → {decisions_path(root, ns.local)}")
    return 0


def cmd_add(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    if err := _kind_flag_error(ns):
        print(f"error: {err}", file=sys.stderr)
        return 1
    # One id sequence across both ledgers: a new entry must not shadow, or be shadowed by, the other's.
    ns.id = ns.id or next_free_id(root, "P" if ns.kind == PREFERENCE else "D")
    if ns.kind == PREFERENCE:
        return _add_preference(root, ns)
    options = [_parse_option(o) for o in ns.option]
    try:
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
            local=ns.local,
        )
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(f"added {entry['id']} (open) → {decisions_path(root, ns.local)}")
    return 0


def cmd_list(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    doc, local_ids, errs = load_merged(root)
    if errs:
        for line in errs:
            print(f"decisions.schema: {line}", file=sys.stderr)
        return 1
    prefs, questions = active_preferences(doc), open_questions(doc)
    if ns.json:
        print(json.dumps([{**e, "source": LOCAL if e["id"] in local_ids else SHARED} for e in prefs + questions],
                         indent=2))
        return 0
    if not prefs and not questions:
        print("No open decisions in roadmap/decisions.yaml or roadmap/decisions.local.yaml.")
        return 0
    for e in prefs + questions:   # each entry names its ledger: local wins over shared for the same id
        head, rest = (format_preference(e) if e in prefs else format_open_entry(e)).split("\n", 1)
        print(f"{head}  ({LOCAL if e['id'] in local_ids else SHARED})\n{rest}")
        print()
    return 0


def cmd_close(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    doc, local_ids, errs = load_merged(root)
    if errs:
        print(f"error: {errs[0]}", file=sys.stderr)
        return 1
    target = next((e for e in doc["entries"] if e.get("id") == ns.decision_id), None)
    if not target:
        print(f"error: no decision {ns.decision_id!r} in roadmap/decisions.yaml or roadmap/decisions.local.yaml",
              file=sys.stderr)
        return 1
    sheet = None if target.get("kind") == PREFERENCE else _sheet_for_node(root, target["node"])[1]
    close_entry(root, ns.decision_id, ns.answer, sheet_text=sheet, local=ns.decision_id in local_ids)
    print(f"closed {ns.decision_id!r}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)
    dec = sub.add_parser("decisions", help="Tracked open human decisions in roadmap/decisions.yaml")
    dsub = dec.add_subparsers(dest="decisions_cmd", required=True)

    add = dsub.add_parser("add", help="Open a self-contained human decision, or record a routing preference")
    add.add_argument("node", metavar="NODE", nargs="?",
                     help="Roadmap node id this entry belongs to (optional for a preference)")
    add.add_argument("--kind", required=True, choices=["decision", "human-action", PREFERENCE])
    add.add_argument("--summary", required=True, help="Plain-words summary; for a preference, the rule")
    add.add_argument("--why", help="Why now and what it blocks (decision); the human's reason (preference)")
    add.add_argument("--option", action="append", metavar="LABEL|EFFECT",
                     help="Repeat for each option (label|effect); decision and human-action")
    add.add_argument("--recommendation")
    add.add_argument("--recommendation-reason")
    add.add_argument("--default", dest="default", help="Default if unanswered")
    add.add_argument("--id", dest="id", help="Entry id (default: next D#, or P# for a preference)")
    add.add_argument("--needed-by", help="ISO date by which an answer is needed")
    add.add_argument("--asked", help="ISO date when asked or stated (default: today)")
    add.add_argument("--role", choices=ROLES, help="Preference: the role the rule routes")
    add.add_argument("--model", action="append", metavar="ROSTER_ID",
                     help="Preference: a preferred roster id; repeat, most preferred first. "
                          "Availability is not a preference: set available/paused_until in the roster")
    add.add_argument("--applies-to", action="append", metavar="LEAF_KIND",
                     help="Preference: a leaf kind it covers, such as docs or data; repeat (default: every leaf)")
    add.add_argument("--expires", help="Preference: active through this date (YYYY-MM-DD) or until this datetime")
    add.add_argument("--supersedes", metavar="ID", help="Preference: close this open preference in the same write")
    add.add_argument("--local", action="store_true",
                     help="Write the gitignored roadmap/decisions.local.yaml (this clone only, no commit needed) "
                          "instead of roadmap/decisions.yaml; readers merge it over the tracked ledger, local wins")
    add_repo_root_arg(add)
    add.set_defaults(func=cmd_add)

    lst = dsub.add_parser("list", help="List active preferences, then open entries ordered by needed-by")
    lst.add_argument("--json", action="store_true")
    add_repo_root_arg(lst)
    lst.set_defaults(func=cmd_list)

    close = dsub.add_parser("close", help="Close an entry after its answer is on the planning sheet "
                                          "(a preference closes with --answer alone)")
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
