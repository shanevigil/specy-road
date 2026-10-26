#!/usr/bin/env python3
"""CLI for `specy-road handoff status` and `specy-road review record`.

``handoff status`` is what a coordinator polls: for each node with a
``work/reviews/<NODE_ID>/`` directory it reports the READY hand-off, every
review record, and whether the review policy is met at the commit under
review. ``review record`` validates one reviewer's notes, fills in the family
from the roster, labels same-family independence, and files the record as
``REVIEW-<model>.md`` beside the READY file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.orchestration_config import effective_config, family_of, substitute_for
from specy_road.review_files import (
    latest_ready,
    list_ready,
    load_review,
    node_ids_with_reviews,
    render_front_matter,
    review_path,
)
from specy_road.review_gate import GateResult, evaluate_gate
from specy_road.review_target import ReviewTarget, resolve_target, same_commit
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root


def _state(t: ReviewTarget, gate: GateResult, ready_commit: str | None) -> str:
    if ready_commit is None:
        return "waiting"
    if not same_commit(ready_commit, t.commit):
        return "stale"
    if gate.blocks:
        return "blocked"
    if gate.passed:
        return "approved"
    return "in-review"


def _node_status(root: Path, node_id: str) -> dict[str, Any]:
    t = resolve_target(root, node_id)
    gate = evaluate_gate(root, t.node, t.commit)
    ready = latest_ready(root, node_id)
    ready_commit = ready.data["commit"] if ready else None
    return {
        "node_id": node_id,
        "state": _state(t, gate, ready_commit),
        "ref": t.ref,
        "commit": t.commit,
        "ready": [
            {"file": r.path.name, "commit": r.data.get("commit"), "errors": r.errors}
            for r in list_ready(root, node_id)
        ],
        "reviews": [
            {"file": c.review.path.name, "model": c.model, "family": c.family,
             "verdict": c.verdict, "counted": True}
            for c in gate.approvals + gate.blocks
        ],
        "policy": gate.summary(),
        "policy_met": gate.passed,
        "problems": gate.problems(),
    }


def _render(st: dict[str, Any]) -> list[str]:
    lines = [f"{st['node_id']}: {st['state']} — {st['ref']} @ {(st['commit'] or '?')[:12]}"]
    for r in st["ready"]:
        mark = "ok" if not r["errors"] else "INVALID: " + "; ".join(r["errors"])
        lines.append(f"  {r['file']} ({mark})")
    for r in st["reviews"]:
        lines.append(f"  {r['file']}: {r['verdict']} by {r['model']} ({r['family']})")
    lines.append(f"  policy: {st['policy']}")
    lines += [f"  - {p}" for p in st["problems"]]
    return lines


def cmd_handoff_status(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    node_ids = [ns.node_id] if ns.node_id else node_ids_with_reviews(root)
    out = []
    for nid in node_ids:
        try:
            out.append(_node_status(root, nid))
        except SystemExit:
            out.append({"node_id": nid, "state": "unknown-node"})
    if ns.json:
        print(json.dumps(out, indent=2))
        return 0
    if not out:
        print("No hand-offs under work/reviews/.")
    for st in out:
        if st["state"] == "unknown-node":
            print(f"{st['node_id']}: not in the roadmap")
            continue
        print("\n".join(_render(st)))
    return 0


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def _family(config: dict[str, Any], ns: argparse.Namespace) -> str | None:
    rostered = family_of(config, ns.model)
    if rostered and ns.family and ns.family != rostered:
        print(f"warning: --family {ns.family} ignored; roster says {rostered}", file=sys.stderr)
    if rostered:
        return rostered
    if not substitute_for(config, ns.node_id, ns.model):
        print(
            f"warning: {ns.model!r} is not a rostered reviewer and no active substitution "
            f"covers {ns.node_id}; this record will not count toward the gate. Add it to "
            "roadmap/orchestration.yaml.",
            file=sys.stderr,
        )
    return ns.family


def _independence(gate: GateResult, model: str, family: str) -> str:
    others = {a.family for a in gate.approvals + gate.blocks if a.model != model}
    return "same-family" if family in others else "distinct-family"


def cmd_review_record(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    t = resolve_target(root, ns.node_id, ns.ref)
    rec = load_review(Path(ns.file), acceptance_ids(t.node))
    if not rec.ok:
        return _fail(f"{ns.file}: " + "; ".join(rec.errors))
    data = rec.data
    for key, want in (("node_id", ns.node_id), ("model", ns.model), ("verdict", ns.verdict)):
        if data.get(key) != want:
            return _fail(f"{ns.file}: {key} is {data.get(key)!r}, the command says {want!r}")
    if not same_commit(data["commit"], t.commit):
        return _fail(
            f"the record reviews {data['commit']}, but the commit under review is "
            f"{t.commit} ({t.ref}). Re-review the current commit."
        )
    config, err = effective_config(root)
    if err:
        return _fail(f"orchestration config: {err}")
    family = _family(config, ns)
    if not family:
        return _fail(f"{ns.model!r} is not in the roster; pass --family or add it to the roster")
    data["family"] = family
    if config["policy"]["reviewers_distinct_families"]:
        data["independence"] = _independence(evaluate_gate(root, t.node, t.commit), ns.model, family)
    dest = review_path(root, ns.node_id, ns.model)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_front_matter(data, rec.body), encoding="utf-8")
    print(f"Wrote {dest}")
    if data.get("independence") == "same-family":
        print(f"note: another counted review is also from family {family!r}; "
              "it is less independent and counts once toward the distinct-family policy.")
    print(f"policy: {evaluate_gate(root, t.node, t.commit).summary()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)

    handoff = sub.add_parser("handoff", help="READY / review hand-off files under work/reviews/")
    hsub = handoff.add_subparsers(dest="handoff_cmd", required=True)
    st = hsub.add_parser("status", help="Report hand-offs, reviews, and whether review policy is met")
    st.add_argument("node_id", nargs="?", help="One node (default: every node under work/reviews/)")
    st.add_argument("--json", action="store_true", help="Machine-readable output for polling")
    add_repo_root_arg(st)
    st.set_defaults(func=cmd_handoff_status)

    review = sub.add_parser("review", help="Review records")
    rsub = review.add_subparsers(dest="review_cmd", required=True)
    rec = rsub.add_parser("record", help="Validate a reviewer's notes and file them as a review record")
    rec.add_argument("node_id")
    rec.add_argument("--model", required=True, help="Reviewer model id (roster id), or human")
    rec.add_argument("--verdict", required=True, choices=["approve", "block"])
    rec.add_argument("--file", required=True, help="Markdown with review-record front matter")
    rec.add_argument("--family", help="Family for a model that is not in the roster")
    rec.add_argument("--ref", help="Branch or commit under review (default: the node's registered branch, else HEAD)")
    add_repo_root_arg(rec)
    rec.set_defaults(func=cmd_review_record)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
