#!/usr/bin/env python3
"""CLI for `specy-road handoff status` and `specy-road review record`.

``handoff status`` is what a coordinator polls: for each node with a
``work/reviews/<NODE_ID>/`` directory it reports the READY hand-off, every
review record, and whether the review policy is met at the commit under
review. Records with no registry claim are listed without a commit unless
``--ref`` names one. ``review record`` validates one reviewer's notes, fills
in the family from the roster, labels same-family independence, and files the
record as ``REVIEW-<model>.md`` beside the READY file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.orchestration_config import substitute_for
from specy_road.review_files import (
    HUMAN,
    latest_ready,
    list_ready,
    list_reviews,
    load_review,
    node_ids_with_reviews,
    render_front_matter,
    review_path,
    verify_problems,
)
from specy_road.review_gate import GateResult, evaluate_gate, rerun_problem, trial_merge
from specy_road.review_signing import NOTES_KEY, SigningError, notes_digest, sign, verify
from specy_road.review_target import ReviewTarget, ReviewTargetError, resolve_target, same_commit
from specy_road.runtime_paths import add_repo_root_arg, resolve_repo_root
from specy_road.session_presence import list_sessions
from specy_road.worker_state import list_records


def _state(root: Path, t: ReviewTarget, gate: GateResult, ready_commit: str | None) -> str:
    """Counted reviews outrank the READY file: they bind to the current commit."""
    if gate.blocks:
        return "blocked"
    if gate.passed:
        return "approved"
    if ready_commit is None:
        return "waiting"
    if not same_commit(root, ready_commit, t.commit):
        return "stale"
    return "in-review"


def _node_status(root: Path, node_id: str, ref: str | None = None) -> dict[str, Any]:
    t = resolve_target(root, node_id, ref)
    gate = evaluate_gate(root, t.node, t.commit)
    branch = (t.entry or {}).get("branch")
    ready = latest_ready(root, node_id, branch)
    ready_commit = ready.data["commit"] if ready else None
    tm = trial_merge(root, t.ref, t.base_ref)
    merge_problem = [tm.problem()] if tm and tm.problem() else []
    return {
        "node_id": node_id,
        "state": _state(root, t, gate, ready_commit),
        "ref": t.ref,
        "commit": gate.commit,
        "ready": [
            {"file": r.path.name, "commit": r.data.get("commit"), "errors": r.errors}
            for r in list_ready(root, node_id, branch)
        ],
        "reviews": [
            {"file": c.review.path.name, "model": c.model, "family": c.family,
             "verdict": c.verdict, "counted": True, "signed": bool(c.review.data.get("signature"))}
            for c in gate.approvals + gate.blocks
        ],
        "policy": gate.summary(),
        "policy_met": gate.passed,
        "problems": merge_problem + gate.problems() + (verify_problems(ready) if ready else []),
    }


def _render(st: dict[str, Any]) -> list[str]:
    if "error" in st:
        return [f"{st['node_id']}: {st['state']} — {st['error']}"]
    where = f"{st['ref']} @ {(st['commit'] or '?')[:12]}" if st["ref"] else "no commit under review"
    lines = [f"{st['node_id']}: {st['state']} — {where}"]
    for r in st["ready"]:
        mark = "ok" if not r["errors"] else "INVALID: " + "; ".join(r["errors"])
        lines.append(f"  {r['file']} ({mark})")
    for r in st["reviews"]:
        lines.append(f"  {r['file']}: {r['verdict']} by {r['model']} ({r['family']}){' [signed]' if r['signed'] else ''}")
    lines.append(f"  policy: {st['policy']}")
    lines += [f"  - {p}" for p in st["problems"]]
    return lines


def _unclaimed(root: Path, nid: str) -> dict[str, Any]:
    """Records without a claim are listed, not called leftover: a repository may never push claims."""
    ready, reviews = list_ready(root, nid), list_reviews(root, nid)
    if not ready and not reviews:
        return {"node_id": nid, "state": "unclaimed",
                "error": "no open claim and no READY or REVIEW records; the directory can be deleted"}
    return {
        "node_id": nid,
        "state": "unclaimed",
        "ref": None,
        "commit": None,
        "ready": [{"file": r.path.name, "commit": r.data.get("commit"), "errors": r.errors} for r in ready],
        "reviews": [
            {"file": r.path.name, "model": r.data["model"], "family": r.data.get("family"),
             "verdict": r.data["verdict"], "counted": False, "signed": bool(r.data.get("signature"))}
            for r in reviews if r.ok
        ],
        "policy": "not evaluated: no claim names the commit under review",
        "policy_met": False,
        "problems": [f"no open claim: pass --ref <branch> to check these records against its commit, "
                     f"or claim the leaf in this checkout with `specy-road do-next-available-task "
                     f"--under {nid} --local`"]
                    + [f"{r.path.name}: invalid — {'; '.join(r.errors)}" for r in reviews if not r.ok],
    }


def _status_or_error(root: Path, nid: str, ref: str | None = None) -> dict[str, Any]:
    try:
        return _node_status(root, nid, ref)
    except ReviewTargetError as e:
        msg = str(e)
        if msg.startswith("no registry claim"):
            return _unclaimed(root, nid)
        return {"node_id": nid, "state": "error", "error": msg}


def cmd_handoff_status(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    if ns.ref and not ns.node_id:
        return _fail("--ref names one node's branch or commit; give the node id too")
    node_ids = [ns.node_id] if ns.node_id else node_ids_with_reviews(root)
    out = [_status_or_error(root, nid, ns.ref) for nid in node_ids]
    sessions = list_sessions(root)
    workers = list_records(root, active_only=True)
    if ns.json:
        print(json.dumps({"sessions": [s.to_dict() for s in sessions],
                          "workers": [w.to_dict() for w in workers], "nodes": out}, indent=2))
    else:
        if sessions:
            print("Live sessions: " + ", ".join(
                f"{s.agent} ({s.branch or '-'}: {', '.join(s.paths) or 'no paths'})" for s in sessions))
        if workers:
            print("Workers: " + ", ".join(
                f"{w.worker_id} ({w.node_id} {w.harness} {w.state}, lease {w.lease.get('holder')})" for w in workers))
        if not out:
            print("No hand-offs under work/reviews/.")
        else:
            print("\n".join(line for st in out for line in _render(st)))
    # Naming a node that cannot be resolved (unknown, or with neither a claim nor
    # records) is a caller error; a stale directory in the sweep is only reported.
    return 1 if ns.node_id and "error" in out[0] else 0


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return 1


def _relabel_independence(root: Path, gate: GateResult) -> None:
    """Rewrite every counted record's ``independence`` label from the current set."""
    counted = gate.approvals + gate.blocks
    for c in counted:
        shared = any(o.family == c.family and o.model != c.model for o in counted)
        label = "same-family" if shared else "distinct-family"
        if c.review.data.get("independence") != label:
            c.review.data["independence"] = label
            c.review.path.write_text(render_front_matter(c.review.data, c.review.body), encoding="utf-8")


def _check_record(ns: argparse.Namespace, root: Path, t: ReviewTarget) -> tuple[dict | None, str | None]:
    if ns.model == HUMAN:
        return None, ("a human review is filed only by the interactive approve in "
                      "specy-road mark-implementation-reviewed, so an agent cannot file one")
    rec = load_review(Path(ns.file), acceptance_ids(t.node))
    if not rec.ok:
        return None, f"{ns.file}: " + "; ".join(rec.errors)
    for key, want in (("node_id", ns.node_id), ("model", ns.model), ("verdict", ns.verdict)):
        if rec.data.get(key) != want:
            return None, f"{ns.file}: {key} is {rec.data.get(key)!r}, the command says {want!r}"
    if not same_commit(root, rec.data["commit"], t.commit):
        return None, (f"the record reviews {rec.data['commit']}, but the commit under review is "
                      f"{t.commit} ({t.ref}). Re-review the current commit.")
    return {"data": rec.data, "body": rec.body}, None


def cmd_review_record(ns: argparse.Namespace) -> int:  # noqa: C901 — baseline 2026-10-28; simplify, then drop this
    root = resolve_repo_root(ns)
    try:
        t = resolve_target(root, ns.node_id, ns.ref)
    except ReviewTargetError as e:
        return _fail(str(e))
    rec, err = _check_record(ns, root, t)
    if err:
        return _fail(err)
    gate = evaluate_gate(root, t.node, t.commit)
    if gate.config_error:
        return _fail(f"orchestration config: {gate.config_error}")
    config = gate.config
    entry = next((e for e in config["roster"] if e.get("id") == ns.model), None)
    if entry is None:
        return _fail(f"{ns.model!r} is not in the roster on the integration branch "
                     "(roadmap/orchestration.yaml); a review from it would not count")
    if "reviewer" not in (entry.get("roles") or []) and not substitute_for(config, ns.node_id, ns.model):
        return _fail(f"{ns.model!r} has no reviewer role and no active substitution covers {ns.node_id}")
    why = rerun_problem(config["policy"], rec["data"])
    if why:
        return _fail(f"{ns.file}: does not count — {why}; list what you re-ran in commands_rerun")
    # The body's hash rides in the front matter, so a signature covers the notes too.
    data = {**rec["data"], "commit": gate.commit, NOTES_KEY: notes_digest(rec["body"])}
    if ns.sign_key:
        if not entry.get("public_key"):
            return _fail(f"--sign-key given, but the roster entry for {ns.model!r} has no public_key; "
                         "the gate could not verify the record")
        try:
            data["signature"] = sign(data, Path(ns.sign_key))
        except SigningError as e:
            return _fail(f"could not sign: {e}")
        ok, why = verify(data, data["signature"], str(entry["public_key"]), ns.model)
        if not ok:
            return _fail(f"the signature does not verify against the roster public_key for {ns.model!r} "
                         f"({why}); wrong key?")
    elif config["policy"].get("signed_reviews"):
        return _fail("policy.signed_reviews is on: pass --sign-key <your private key>; the roster entry "
                     f"for {ns.model!r} must carry the matching public_key")
    data["family"] = entry["family"]
    dest = review_path(root, ns.node_id, ns.model)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_front_matter(data, rec["body"]), encoding="utf-8")
    print(f"Wrote {dest}")
    after = evaluate_gate(root, t.node, t.commit)
    if after.distinct_families:
        _relabel_independence(root, after)
        if any(o.family == entry["family"] and o.model != ns.model for o in after.approvals + after.blocks):
            print(f"note: another counted review is also from family {entry['family']!r}; "
                  "it is less independent and counts once toward the distinct-family policy.")
    print(f"policy: {after.summary()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)

    handoff = sub.add_parser("handoff", help="READY / review hand-off files under work/reviews/")
    hsub = handoff.add_subparsers(dest="handoff_cmd", required=True)
    st = hsub.add_parser("status", help="Report hand-offs, reviews, and whether review policy is met")
    st.add_argument("node_id", nargs="?", help="One node (default: every node under work/reviews/)")
    st.add_argument("--json", action="store_true", help="Machine-readable output for polling")
    st.add_argument("--ref", help="Branch or commit under review (default: the node's registered branch)")
    add_repo_root_arg(st)
    st.set_defaults(func=cmd_handoff_status)

    review = sub.add_parser("review", help="Review records")
    rsub = review.add_subparsers(dest="review_cmd", required=True)
    rec = rsub.add_parser("record", help="Validate a reviewer's notes and file them as a review record")
    rec.add_argument("node_id")
    rec.add_argument("--model", required=True, help="Reviewer model id from the roster (not human)")
    rec.add_argument("--verdict", required=True, choices=["approve", "block"])
    rec.add_argument("--file", required=True, help="Markdown with review-record front matter")
    rec.add_argument("--ref", help="Branch or commit under review (default: the node's registered branch)")
    rec.add_argument("--sign-key", metavar="PATH", help="Sign the record with this OpenSSH private key (ssh-keygen -Y sign)")
    add_repo_root_arg(rec)
    rec.set_defaults(func=cmd_review_record)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))


if __name__ == "__main__":
    main()
