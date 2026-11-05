#!/usr/bin/env python3
"""CLI for `specy-road handoff status`, `specy-road review record|list|delegate` and `specy-road ready`.

``handoff status`` is what a coordinator polls: for each node with a
``work/reviews/<NODE_ID>/`` directory it reports the READY hand-off, every
review record, and whether the review policy is met at the commit under
review. Records with no registry claim are listed without a commit unless
``--ref`` names one. Given one node it exits 0 when the gate is met or the node
is Complete, 1 when it is not met, and 2 when it cannot be determined. A leaf
whose review loop is not converging and has no root-cause analysis for it is
``escalated`` (exit 1), with the trigger named (``review_rca``).
With ``policy.max_fix_rounds`` set, a leaf that spent that many blocking rounds is ``fix_round_budget_spent``
(exit 1) with its next command; ``review defer`` applies an RCA's deferral (:mod:`review_defer`, human-only).
``review record`` validates one reviewer's notes, fills in the family from the
roster, labels same-family independence, and files the record as
``REVIEW-<model>.md`` beside the READY file, keeping a copy under ``history/``. It refuses an approve whose
findings or notes name a defect with neither a ``required_changes`` entry nor a ``not a defect because`` line
(:mod:`specy_road.review_record_rules`).
``review list`` prints the filed records, any RCA records, the escalation and the gate evaluation, and writes nothing.
Both commands report the leaf's review rounds (distinct reviewed commits), the time from its first review to the latest,
and each ``review delegate`` run with its commit; an older commit's record never reads as the current verdict.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from specy_road.bundled_scripts.brief_acceptance import acceptance_ids
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.red_green import cmd_red_green
from specy_road.review_files import (
    REVIEW_LAUNCH_MODES, executor_blocked_display_lines, latest_ready, list_ready,
    list_reviews, node_ids_with_reviews, non_gating_verify_problems, render_front_matter,
    review_path, reviews_dir, reviews_root, round_span, write_review,
)
from specy_road.review_gate import GateResult, evaluate_gate, trial_merge
from specy_road.review_rejected import run_review_record
from specy_road.review_delegate import add_parser as add_delegate_parser, run_lines, run_problems, run_states, gate_policy_summary
from specy_road.review_eligible import eligibility_lines, reviewer_eligibility
from specy_road.review_ready_merge import add_ready_parser
from specy_road.review_pre_existing import cmd_check_pre_existing
from specy_road.review_rca import LoopState, loop_state
from specy_road.review_next_step import fix_round_budget
from specy_road.bundled_scripts.review_defer import add_parser as add_defer_parser
from specy_road.orphaned_claims import orphaned_claims, report_lines
from specy_road.review_run_status import (extend_handoff_refused, print_refused_list, refused_by_model,
                                          review_list_payload, unreadable_rejected_lines)
from specy_road.review_target import (ReviewTarget, ReviewTargetError, milestone_status,
                                      resolve_target, same_commit)
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
    branch = (t.entry or {}).get("branch")
    aids = acceptance_ids(t.node)
    gate = evaluate_gate(root, t.node, t.commit, branch=branch)
    ready = latest_ready(root, node_id, branch, aids)
    ready_commit = ready.data["commit"] if ready else None
    # A current READY's blocked_on outranks reviewer blocks and escalation (A3).
    blocked_lines = executor_blocked_display_lines(ready) if same_commit(root, ready_commit, t.commit) else []
    loop = loop_state(root, node_id)
    escalated = loop.escalation is not None and not gate.passed
    budget = fix_round_budget(root, gate.config, loop, node_id, bool(gate.blocks))   # None: max_fix_rounds unset
    spent = bool(budget and budget["spent"])   # spent and a counted review still blocks
    state = ("executor_blocked" if blocked_lines else "fix_round_budget_spent" if spent
             else "escalated" if escalated else _state(root, t, gate, ready_commit))
    state, hints = milestone_status(t, state)
    tm = trial_merge(root, t.ref, t.base_ref)
    merge_problem = ([tm.problem()] if tm and tm.problem() else []) + hints
    return {
        "node_id": node_id,
        "state": state,
        "escalation": loop.escalation.to_dict() if escalated else None,
        "ref": t.ref,
        "commit": gate.commit,
        "executor_blocked": blocked_lines,
        "ready": [
            {"file": r.path.name, "commit": r.data.get("commit"), "errors": r.errors}
            for r in list_ready(root, node_id, branch, aids)
        ],
        "reviews": [
            {"file": c.review.path.name, "model": c.model, "family": c.family,
             "verdict": c.verdict, "counted": True, "signed": bool(c.review.data.get("signature")),
             "launch_mode": c.review.data.get("launch_mode"),
             "commands_rerun": list(c.review.data.get("commands_rerun") or [])}
            for c in gate.approvals + gate.blocks
        ],
        "review_rounds": round_span(root, node_id), "findings_trend": loop.findings_trend(),
        "review_runs": (runs := run_states(root, node_id, gate.commit)),
        "policy": gate_policy_summary(gate, runs), "reviewer_eligibility": reviewer_eligibility(root, t.node, gate, branch),
        "refused": refused_by_model(root, node_id, gate.commit),
        "refused_unreadable": unreadable_rejected_lines(reviews_dir(root, node_id)),
        "policy_met": gate.passed,
        "trial_merge": {"ref": tm.base_ref, "behind": tm.behind, "conflicts": tm.conflicts,
                        "blocking": tm.code_conflicts} if tm and tm.conflicts else None,
        **({"fix_round_budget": budget} if budget else {}),
        "problems": merge_problem + gate.problems() + non_gating_verify_problems(ready) + loop.problems() + run_problems(node_id, runs),
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
        rerun = r.get("commands_rerun") or []
        extra = f"; reviewer re-ran {', '.join(rerun)!r}" if rerun else ""
        mode = f", launch mode {r['launch_mode']}" if r.get("launch_mode") else ""
        at = "" if r["counted"] else f" at {str(r.get('commit') or '?')[:12]}, not evaluated"
        lines.append(f"  {r['file']}: {r['verdict']} by {r['model']} ({r['family']}){at}"
                     f"{' [signed]' if r['signed'] else ''}{mode}{extra}")
    lines += [f"  {line}" for line in run_lines(st.get("review_runs") or [])]
    extend_handoff_refused(st, lines)
    lines += [f"  {x}" for x in [st["review_rounds"]["line"], *(st.get("findings_trend") or {}).get("lines", [])]]
    lines += [f"  policy: {st['policy']}"] + eligibility_lines(st)   # who can still approve, when not met
    if tm := st.get("trial_merge"):
        kind = "" if tm["blocking"] else " (bookkeeping only, which does not block)"
        lines.append(f"  trial merge with {tm['ref']}: conflicts on {', '.join(tm['conflicts'])}{kind}")
    if st.get("escalation"):
        lines.append(_escalation_line(st["node_id"], st["escalation"]["describe"]))
    if st["state"] == "fix_round_budget_spent":
        b = st["fix_round_budget"]
        lines.append(f"  fix_round_budget_spent: {b['blocking_rounds']} blocking round(s), policy.max_fix_rounds "
                     f"{b['max_fix_rounds']}; {b['next_why']}; next: `{b['next']}`")
    for line in st.get("executor_blocked") or []:
        lines.append(f"  {line}")
    lines += [f"  - {p}" for p in st["problems"]]
    return lines


def _escalation_line(node_id: str, describe: str) -> str:
    return (f"  escalated: {describe}; next, a root-cause analysis: "
            f"`specy-road prompt {node_id} --role rca --model <reviewer that has not reviewed it>`")


def _print_rcas(loop: LoopState) -> None:
    for r in loop.rcas:
        if r.ok:
            c, a = r.data["classification"], r.data["recommended_action"]
            print(f"{r.path.name}: {c['primary']} ({c['confidence']}) by {r.data['model']}, through round "
                  f"{r.data['trigger']['round']} — {a['type']}")
    for p in loop.problems():
        print(p)


def _unclaimed(root: Path, nid: str) -> dict[str, Any]:
    """Records without a claim are listed, not called leftover: a repository may never push claims.

    A Complete node passed its gate before its claim was released, so it is
    ``complete_no_claim``, not an undeterminable ``unclaimed``.
    """
    node = next(n for n in load_roadmap(root)["nodes"] if n.get("id") == nid)
    complete = node.get("status") == "Complete"
    ready, reviews = list_ready(root, nid), list_reviews(root, nid)
    if not complete and not ready and not reviews:
        return {"node_id": nid, "state": "unclaimed",
                "error": "no open claim and no READY or REVIEW records; the directory can be deleted"}
    hint = ("Complete with no open claim: pass --ref <branch or commit> to check these records against it"
            if complete else
            f"no open claim: pass --ref <branch> to check these records against its commit, "
            f"or claim the leaf in this checkout with `specy-road do-next-available-task --under {nid} --local`")
    return {
        "node_id": nid,
        "state": "complete_no_claim" if complete else "unclaimed",
        "ref": None,
        "commit": None,
        "ready": [{"file": r.path.name, "commit": r.data.get("commit"), "errors": r.errors} for r in ready],
        "reviews": [
            {"file": r.path.name, "model": r.data["model"], "family": r.data.get("family"),
             "verdict": r.data["verdict"], "counted": False, "signed": bool(r.data.get("signature")),
             "launch_mode": r.data.get("launch_mode"), "commit": r.data.get("commit")}
            for r in reviews if r.ok
        ],
        "review_rounds": round_span(root, nid),
        "review_runs": run_states(root, nid, None),
        "policy": "not evaluated: no claim names the commit under review",
        "policy_met": False,
        "trial_merge": None,
        "problems": [hint] + [f"{r.path.name}: invalid — {'; '.join(r.errors)}" for r in reviews if not r.ok],
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
        return _fail("--ref names one node's branch or commit; give the node id too", 2)
    node_ids = [ns.node_id] if ns.node_id else node_ids_with_reviews(root)
    out = [_status_or_error(root, nid, ns.ref) for nid in node_ids]
    sessions = list_sessions(root)
    workers = list_records(root, active_only=True)
    if ns.json:
        print(json.dumps({"sessions": [s.to_dict() for s in sessions],
                          "workers": [w.to_dict() for w in workers], "nodes": out, "orphaned_claims": orphaned_claims(root)}, indent=2))
    else:
        if sessions:
            print("Live sessions: " + ", ".join(f"{s.agent} ({s.branch or '-'}: {', '.join(s.paths) or 'no paths'})" for s in sessions))
        if workers:
            print("Workers: " + ", ".join(f"{w.worker_id} ({w.node_id} {w.harness} {w.state}, lease {w.lease.get('holder')})" for w in workers))
        any(map(print, report_lines(orphaned_claims(root))))
        if not out:
            print(f"No hand-offs under {reviews_root(root)}.")
        else:
            print("\n".join(line for st in out for line in _render(st)))
    # A sweep only reports. For one named node a polling script reads the exit:
    # 0 gate met (or Complete), 1 not met, 2 undeterminable; `state` says which.
    return _EXIT.get(out[0]["state"], 1) if ns.node_id else 0


_EXIT = {"approved": 0, "complete_no_claim": 0, "unclaimed": 2, "error": 2, "executor_blocked": 1}


def _fail(msg: str, code: int = 1) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return code


def _relabel_independence(root: Path, gate: GateResult) -> None:
    """Rewrite every counted record's ``independence`` label from the current set."""
    counted = gate.approvals + gate.blocks
    for c in counted:
        shared = any(o.family == c.family and o.model != c.model for o in counted)
        label = "same-family" if shared else "distinct-family"
        if c.review.data.get("independence") != label:
            c.review.data["independence"] = label
            write_review(c.review.path, render_front_matter(c.review.data, c.review.body))


def cmd_review_record(ns: argparse.Namespace) -> int:
    return run_review_record(ns, resolve_repo_root(ns), _fail, _relabel_independence)


def _print_review_list_text(root: Path, ns: argparse.Namespace, t: ReviewTarget | None) -> int:
    reviews = list_reviews(root, ns.node_id)
    if not reviews:
        print(f"No review records for {ns.node_id}.")
    for r in reviews:
        d = r.data
        stale = t is not None and r.ok and not same_commit(root, d.get("commit"), t.commit)
        print(f"{r.path.name}: {d.get('verdict')} by {d.get('model')} ({d.get('family')}) "
              f"at {str(d.get('commit') or '?')[:12]}{' [signed]' if d.get('signature') else ''}"
              + ("" if r.ok else f" — invalid: {'; '.join(r.errors)}") + (" — stale: not the commit under review" if stale else ""))
    if t:
        print_refused_list(root, ns.node_id, t.commit)
    for line in unreadable_rejected_lines(reviews_dir(root, ns.node_id)):
        print(line)
    print("\n".join(run_lines(run_states(root, ns.node_id, t.commit if t else None))) or "No delegated review runs.")
    print(round_span(root, ns.node_id)["line"])
    loop = loop_state(root, ns.node_id)
    _print_rcas(loop)
    gate = None
    if t is None:
        print("gate: not evaluated — no registry claim names the commit under review; "
              "pass --ref <branch or commit>")
    else:
        gate = evaluate_gate(root, t.node, t.commit, branch=(t.entry or {}).get("branch"))
        print(f"gate at {t.ref} @ {(gate.commit or '?')[:12]}: {gate.summary()}")
        for p in gate.problems():
            print(f"  - {p}")
        for line in milestone_status(t, "approved" if gate.passed else "waiting")[1]:
            print(line)
    if loop.escalation and (t is None or gate is None or not gate.passed):
        print(_escalation_line(ns.node_id, loop.escalation.describe()).strip())
    return 0


def cmd_review_list(ns: argparse.Namespace) -> int:
    """Filed records and RCA records, the gate at the commit under review, then any escalation; reads only."""
    root = resolve_repo_root(ns)
    if ns.json:
        payload = review_list_payload(root, ns.node_id, ns.ref)
        print(json.dumps(payload, indent=2))
        if payload.get("error"):
            return _fail(payload["error"])
        return 0
    try:
        t = resolve_target(root, ns.node_id, ns.ref)
    except ReviewTargetError as e:
        if not str(e).startswith("no registry claim"):
            return _fail(str(e))
        t = None
    return _print_review_list_text(root, ns, t)


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
    rec.add_argument("--launch-mode", choices=REVIEW_LAUNCH_MODES, help="How your harness was started; stored on the record")
    add_repo_root_arg(rec)
    rec.set_defaults(func=cmd_review_record)
    for name, about, fn in (("list", "Print a node's filed review records and the gate evaluation; writes nothing", cmd_review_list),
                            ("check-pre-existing", "Re-run claimed pre-existing verifier failures twice on the integration tip",
                             cmd_check_pre_existing),
                            ("red-green", "Run the tests a leaf adds or changes at its merge base and at head", cmd_red_green)):
        sp = rsub.add_parser(name, help=about)
        sp.add_argument("node_id")
        sp.add_argument("--ref", help="Branch or commit under review (default: the node's registered branch)")
        if name == "list":
            sp.add_argument("--json", action="store_true", help="Machine-readable output including refused markers")
        add_repo_root_arg(sp)
        sp.set_defaults(func=fn)
    add_delegate_parser(rsub)
    add_defer_parser(rsub)
    add_ready_parser(sub)
    return p


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    ns = build_parser().parse_args(argv)
    raise SystemExit(ns.func(ns))
if __name__ == "__main__":
    main()
