#!/usr/bin/env python3
"""CLI for `specy-road review status|packet|record|delegate` and `specy-road ready`.

``review status`` is what a coordinator polls: for each node with a
``work/reviews/<NODE_ID>/`` directory it reports the READY hand-off, every
review record, and whether the review policy is met at the commit under
review. Given one node it also prints what ``review list`` printed that the report above does not (each record's
commit, stale and invalid records, RCA records, the gate line), and ``--json`` adds that node's ``records``. Records with no registry claim are listed without a commit unless
``--ref`` names one. Given one node it exits 0 when the gate is met or the node
is Complete, 1 when it is not met, and 2 when it cannot be determined. A leaf
whose review loop is not converging and has no root-cause analysis for it is
``escalated`` (exit 1), with the trigger named (``review_rca``).
With ``policy.max_fix_rounds`` set, a leaf that spent that many blocking rounds is ``fix_round_budget_spent``
(exit 1) with its next command; ``review defer`` applies an RCA's deferral (:mod:`review_defer`, human-only).
``review accept-policy`` accepts a review policy change made since the claim (:mod:`review_policy_pin`, human-only);
``--all-open`` asks once for every open claim whose pin differs and writes one acceptance file per leaf.
``review operator-decision`` records an operator's review decision, or the coordinator's acceptance with limits
under a standing operator rule (:mod:`specy_road.review_override`, coordinator only).
``review record`` validates one reviewer's notes, fills in the family from the
roster, labels same-family independence, and files the record as
``REVIEW-<model>.md`` beside the READY file, keeping a copy under ``history/``. It refuses an approve whose
findings or notes name a defect with neither a ``required_changes`` entry nor a ``not a defect because`` line
(:mod:`specy_road.review_record_rules`).
It reports the leaf's review rounds (distinct reviewed commits), the time from its first review to the latest,
and each ``review delegate`` run with its commit; an older commit's record never reads as the current verdict.
``review packet`` writes the reviewer's packet (:mod:`review_packet`).
``handoff status`` (the report without the records) and ``review list`` (the records and the gate alone) are
deprecated aliases of ``review status``, each printing one deprecation line first.
"""

from __future__ import annotations

import argparse
import contextlib
import getpass
import io
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from specy_road.bundled_scripts.finish_task import undecided_human_items
from specy_road.cli_args import add_json_arg, add_model_arg, add_ref_arg
from specy_road.cli import ALIASES_REMOVED_IN, warn_deprecated
from specy_road.cli_entry import run_cli
from specy_road.clock import utc_now_iso
from specy_road.decisions import DECISIONS_REL
from specy_road.git_subprocess import git_text
from specy_road.brief_acceptance import acceptance_ids
from specy_road.roadmap_load import load_roadmap
from specy_road.red_green import cmd_red_green
from specy_road.registry_yaml import read_registry, registry_path
from specy_road.review_files import (
    REVIEW_LAUNCH_MODES, executor_blocked_display_lines, list_ready, project_of,
    list_reviews, node_ids_with_reviews, non_gating_verify_problems, render_front_matter,
    review_path, reviews_dir, reviews_root, round_span, write_review,
)
from specy_road.review_gate_ready import empty_ready_error
from specy_road.review_gate import GateResult, evaluate_gate, trial_merge
from specy_road import review_caller, review_lock, safe_write
from specy_road.review_lock import ReviewRunBusy, filing_busy
from specy_road.review_rejected import run_review_record
from specy_road.review_delegate import add_parser as add_delegate_parser, run_lines, run_problems, run_states, gate_policy_summary
from specy_road.review_eligible import eligibility_lines, reviewer_eligibility
from specy_road.review_ready_merge import add_ready_parser
from specy_road.review_pre_existing import cmd_check_pre_existing
from specy_road.review_rca import LoopState, loop_state
from specy_road.review_next_step import fix_round_budget
from specy_road.review_defer import add_parser as add_defer_parser
from specy_road.review_policy_pin import (
    PolicyUnreadable,
    _asked_because,
    _pin_state,
    acceptance_path,
)
from specy_road.review_override import (
    ACCEPT_WITH_LIMITS,
    APPROVE,
    _coordinator_problem,
    append_decision,
    blocks_to_settle,
    recorder,
    role_refusal,
    write_operator_marker,
)
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


@dataclass
class ReviewState:
    """One claimed node's review state without the trial merge: what ``review status`` and
    ``grind-session --status`` (M22.68) share, so the state names keep one definition."""

    target: ReviewTarget
    gate: GateResult
    files: list[Any]
    ready: Any
    loop: LoopState
    escalated: bool
    budget: dict[str, Any] | None
    executor_blocked: list[str]
    state: str
    hints: list[str]


def review_state(root: Path, node_id: str, ref: str | None = None) -> ReviewState:
    """The gate, READY, loop escalation, fix-round budget and policy pin of ``node_id``; no trial merge.

    Raises :class:`ReviewTargetError` when no claim or ``ref`` names a commit to review."""
    t = resolve_target(root, node_id, ref)
    branch = (t.entry or {}).get("branch")
    aids = acceptance_ids(t.node)
    gate = evaluate_gate(root, t.node, t.commit, branch=branch)
    files = list_ready(root, node_id, branch, aids)
    for item in files:   # an old empty hand-off is not an offer of review; a blocked one still is
        if item.ok and (msg := empty_ready_error(root, t.touch_zones, item.data)):
            item.errors.append(msg)
    valid = [item for item in files if item.ok]
    ready = max(valid, key=lambda r: (r.path.stat().st_mtime, r.path.name), default=None)
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
    return ReviewState(t, gate, files, ready, loop, escalated, budget, blocked_lines, state, hints)


def _node_status(root: Path, node_id: str, ref: str | None = None) -> dict[str, Any]:
    rs = review_state(root, node_id, ref)
    t, gate, files, ready, loop, budget = rs.target, rs.gate, rs.files, rs.ready, rs.loop, rs.budget
    state, hints, escalated, blocked_lines = rs.state, rs.hints, rs.escalated, rs.executor_blocked
    branch = (t.entry or {}).get("branch")
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
            for r in files
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
        "human_criteria_undecided": undecided_human_items(root, t.node, t.base_ref, t.ref),
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
    if st.get("human_criteria_undecided"):   # an unclaimed node's status has none
        lines.append(f"  human criteria undecided: {', '.join(st['human_criteria_undecided'])} (a person closes each "
                     "one's entry in roadmap/decisions.yaml before finish-this-task)")
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


def rca_command(node_id: str) -> str:
    """The root-cause analysis an escalated leaf needs next (``review status``, ``grind-session --status``)."""
    return f"specy-road prompt {node_id} --role rca --model <reviewer that has not reviewed it>"


def _escalation_line(node_id: str, describe: str) -> str:
    return f"  escalated: {describe}; next, a root-cause analysis: `{rca_command(node_id)}`"


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


def _status_report(ns: argparse.Namespace, *, records: bool) -> int:
    """The hand-off report; with ``records`` and one node, ``review list``'s lines and payload too."""
    root = resolve_repo_root(ns)
    if ns.ref and not ns.node_id:
        return _fail("--ref names one node's branch or commit; give the node id too", 2)
    node_ids = [ns.node_id] if ns.node_id else node_ids_with_reviews(root)
    out = [_status_or_error(root, nid, ns.ref) for nid in node_ids]
    sessions = list_sessions(root)
    workers = list_records(root, active_only=True)
    if ns.json:
        payload = {"sessions": [s.to_dict() for s in sessions], "workers": [w.to_dict() for w in workers],
                   "nodes": out, "orphaned_claims": orphaned_claims(root)}
        if records and ns.node_id:
            payload["records"] = review_list_payload(root, ns.node_id, ns.ref)
        print(json.dumps(payload, indent=2))
    else:
        lines = _handoff_lines(root, out, sessions, workers)
        if records and ns.node_id:
            seen = {line.strip() for line in lines}
            lines += [line for line in _review_list_lines(root, ns.node_id, ns.ref) if line.strip() not in seen]
        print("\n".join(lines))
    # A sweep only reports. For one named node a polling script reads the exit:
    # 0 gate met (or Complete), 1 not met, 2 undeterminable; `state` says which.
    return _EXIT.get(out[0]["state"], 1) if ns.node_id else 0


def _handoff_lines(root: Path, out: list[dict[str, Any]], sessions: list[Any], workers: list[Any]) -> list[str]:
    lines = []
    if sessions:
        lines.append("Live sessions: " + ", ".join(f"{s.agent} ({s.branch or '-'}: {', '.join(s.paths) or 'no paths'})"
                                                   for s in sessions))
    if workers:
        lines.append("Workers: " + ", ".join(f"{w.worker_id} ({w.node_id} {w.harness} {w.state}, lease "
                                             f"{w.lease.get('holder')})" for w in workers))
    lines += report_lines(orphaned_claims(root))
    if not out:
        return [*lines, f"No hand-offs under {reviews_root(root)}."]
    return lines + [line for st in out for line in _render(st)]


def cmd_review_status(ns: argparse.Namespace) -> int:
    """``review status``: the hand-off report, and for one node its records and gate line too; reads only."""
    return _status_report(ns, records=True)


def cmd_handoff_status(ns: argparse.Namespace) -> int:
    """``handoff status``, the deprecated alias: the report without ``review list``'s lines."""
    warn_deprecated("handoff status", "review status")
    return _status_report(ns, records=False)


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
    try:
        return run_review_record(ns, resolve_repo_root(ns), _fail, _relabel_independence)
    except safe_write.SafeWriteError as e:   # a symlink on the live record or history/: nothing was written
        return _fail(str(e))


def cmd_review_record_locked(ns: argparse.Namespace) -> int:
    """``review record`` from the command line: waits for, then refuses during, a reviewer run on the leaf.
    A run's own filing (``file_review``) calls :func:`cmd_review_record` inside the lock it holds."""
    root = resolve_repo_root(ns)
    if not any(n.get("id") == ns.node_id for n in load_roadmap(root)["nodes"]):   # before any mkdir or lock file
        return _fail(f"unknown node id: {ns.node_id}")
    if why := review_caller.refusal(root, ns):   # before the lock: a refused caller writes nothing (M21.31)
        return _fail(why)
    try:
        with review_lock.review_run_lock(reviews_dir(root, ns.node_id), wait=review_lock.FILING_WAIT):
            return cmd_review_record(ns)
    except ReviewRunBusy:
        return _fail(f"{filing_busy(ns.node_id)} — file again when it ends (review status {ns.node_id})")
    except safe_write.SafeWriteError as e:   # a symlink at the hand-off directory or the lock
        return _fail(str(e))


def _print_review_list_text(root: Path, node_id: str, t: ReviewTarget | None) -> int:
    reviews = list_reviews(root, node_id)
    if not reviews:
        print(f"No review records for {node_id}.")
    for r in reviews:
        d = r.data
        stale = t is not None and r.ok and not same_commit(root, d.get("commit"), t.commit)
        print(f"{r.path.name}: {d.get('verdict')} by {d.get('model')} ({d.get('family')}) "
              f"at {str(d.get('commit') or '?')[:12]}{' [signed]' if d.get('signature') else ''}"
              + ("" if r.ok else f" — invalid: {'; '.join(r.errors)}") + (" — stale: not the commit under review" if stale else ""))
    if t:
        print_refused_list(root, node_id, t.commit)
    for line in unreadable_rejected_lines(reviews_dir(root, node_id)):
        print(line)
    print("\n".join(run_lines(run_states(root, node_id, t.commit if t else None))) or "No delegated review runs.")
    print(round_span(root, node_id)["line"])
    loop = loop_state(root, node_id)
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
    if loop.escalation and (t is None or not gate.passed):
        print(_escalation_line(node_id, loop.escalation.describe()).strip())
    return 0


def _review_target(root: Path, node_id: str, ref: str | None) -> ReviewTarget | None:
    """The commit under review; ``None`` with no claim. Raises :class:`ReviewTargetError` for any other failure."""
    try:
        return resolve_target(root, node_id, ref)
    except ReviewTargetError as e:
        if not str(e).startswith("no registry claim"):
            raise
        return None


def _review_list_lines(root: Path, node_id: str, ref: str | None) -> list[str]:
    """What ``review list`` printed for ``node_id``; none when the target does not resolve (it exited 1)."""
    try:
        t = _review_target(root, node_id, ref)
    except ReviewTargetError:
        return []
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        _print_review_list_text(root, node_id, t)
    return buf.getvalue().splitlines()


def cmd_review_list(ns: argparse.Namespace) -> int:
    """``review list``, the deprecated alias: filed records and RCA records, the gate at the commit under
    review, then any escalation; reads only."""
    warn_deprecated("review list", "review status")
    root = resolve_repo_root(ns)
    if ns.json:
        payload = review_list_payload(root, ns.node_id, ns.ref)
        print(json.dumps(payload, indent=2))
        if payload.get("error"):
            return _fail(payload["error"])
        return 0
    try:
        t = _review_target(root, ns.node_id, ns.ref)
    except ReviewTargetError as e:
        return _fail(str(e))
    return _print_review_list_text(root, ns.node_id, t)


def _user(root: Path) -> str:
    name, email = (git_text(["config", f"user.{k}"], root) for k in ("name", "email"))
    return f"{name} <{email}>" if name and email else name or email or getpass.getuser()


def _open_policy_changes(root: Path) -> list[dict[str, Any]]:
    """Open claims whose pinned review policy differs from the integration branch, in registry order."""
    nodes = load_roadmap(root)["nodes"]
    changes = []
    for entry in read_registry(registry_path(root)).get("entries") or []:
        if not isinstance(entry, dict) or not entry.get("node_id"):
            continue
        target = resolve_target(root, str(entry["node_id"]), None, nodes=nodes)
        state = _pin_state(root, target.node, target.commit or "HEAD")
        if state is None:
            continue
        ref, pinned, at, current, lines = state
        changes.append({"node_id": str(entry["node_id"]), "ref": ref, "pinned": pinned, "at": at,
                        "current": current, "lines": tuple(lines)})
    return changes


def _change_groups(changes: list[dict[str, Any]]) -> list[tuple[tuple[str, ...], list[dict[str, Any]]]]:
    """Each distinct set of change lines once, with the leaves it affects, earliest leaf id first."""
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for change in changes:
        grouped.setdefault(change["lines"], []).append(change)
    return sorted(grouped.items(), key=lambda item: min(row["node_id"] for row in item[1]))


def _write_acceptances(root: Path, rows: list[dict[str, Any]]) -> int:
    """One ``POLICY-ACCEPTED.yaml`` per leaf, under that leaf's review lock.

    Nothing is written when a lock is held, or when any acceptance path is a symlink.
    """
    ordered = sorted(rows, key=lambda row: row["node_id"])
    user = _user(root)
    at = utc_now_iso()
    with contextlib.ExitStack() as stack:
        for row in ordered:
            try:
                stack.enter_context(review_lock.review_run_lock(
                    reviews_dir(root, row["node_id"]), wait=review_lock.FILING_WAIT))
            except review_lock.ReviewRunBusy:
                print(f"error: {review_lock.filing_busy(row['node_id'])}", file=sys.stderr)
                return 1
            except safe_write.SafeWriteError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
        prepared: list[tuple[Path, str]] = []
        for row in ordered:
            path = acceptance_path(root, row["node_id"])
            record = {"node_id": row["node_id"], "pinned_sha256": row["pinned"], "accepted_sha256": row["current"],
                      "user": user, "at": at}
            try:
                safe_write.check(project_of(path), path)
            except safe_write.SafeWriteError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            prepared.append((path, yaml.safe_dump(record, sort_keys=False)))
        for path, body in prepared:
            try:
                safe_write.write(project_of(path), path, body)
            except safe_write.SafeWriteError as e:
                print(f"error: {e}", file=sys.stderr)
                return 1
            print(f"wrote {path}")
    return 0


def _accept_one(root: Path, node_id: str, ref: str | None) -> int:
    target = resolve_target(root, node_id, ref, nodes=load_roadmap(root)["nodes"])
    state = _pin_state(root, target.node, target.commit or "HEAD")
    if state is None:
        print(f"{node_id}: the review policy is unchanged since the claim (or not pinned); nothing to accept")
        return 0
    where, pinned, at, current, lines = state
    print(f"review policy changed on {where} since {node_id} was claimed ({at[:12]}):")
    print(_asked_because())
    for line in lines:
        print(f"  - {line}")
    if input(f"Type {node_id} to accept this policy for {node_id}: ").strip() != node_id:
        print("not accepted; nothing was written", file=sys.stderr)
        return 1
    return _write_acceptances(root, [{"node_id": node_id, "pinned": pinned, "current": current}])


def _print_groups(changes: list[dict[str, Any]]) -> None:
    print(f"Open claims whose pinned review policy differs from {changes[0]['ref']}:")
    print(_asked_because())
    for lines, leaves in _change_groups(changes):
        ordered = sorted(leaves, key=lambda row: row["node_id"])
        print(", ".join(row["node_id"] for row in ordered) + ":")
        for row in ordered:
            print(f"  {row['node_id']}: pinned {row['pinned']} accepted {row['current']}")
        for line in lines:
            print(f"  - {line}")


def _accept_all(root: Path) -> int:
    """``--all-open``: one confirmation, then one acceptance file per leaf that differs."""
    changes = _open_policy_changes(root)
    if not changes:
        print("no open claim has a review policy that differs from its pin; nothing to accept")
        return 0
    _print_groups(changes)
    token = " ".join(sorted(row["node_id"] for row in changes))
    if input(f"Type {token} to accept this policy for {token}: ").strip() != token:
        print("not accepted; nothing was written", file=sys.stderr)
        return 1
    return _write_acceptances(root, changes)


def _usage_error(ns: argparse.Namespace) -> str | None:
    if bool(ns.node_id) == bool(ns.all_open):
        return "pass one node id or --all-open, not both and not neither"
    if ns.all_open and ns.ref:
        return "--ref is for one node; --all-open uses each claim's registered branch"
    return None


def cmd_accept_policy(ns: argparse.Namespace) -> int:
    """``review accept-policy``: a human, in a terminal, accepts the policy change since the claim.

    One node id is that leaf. ``--all-open`` is every open claim whose pin differs: one confirmation, then
    one acceptance file per leaf.
    """
    if not sys.stdin.isatty():
        print("error: a human accepts a review policy change in a terminal; nothing was written", file=sys.stderr)
        return 1
    if reason := _usage_error(ns):
        print(f"error: {reason}; nothing was written", file=sys.stderr)
        return 1
    root = resolve_repo_root(ns)
    try:
        if ns.all_open:
            return _accept_all(root)
        return _accept_one(root, ns.node_id, ns.ref)
    except (ReviewTargetError, PolicyUnreadable) as e:
        print(f"error: {e}; nothing was written", file=sys.stderr)
        return 1


def add_accept_policy_parser(rsub: Any) -> None:
    sp = rsub.add_parser("accept-policy", help="Human-only: accept a review policy change made on the integration "
                                               "branch since the leaf was claimed")
    sp.add_argument("node_id", nargs="?", help="One leaf; omit it with --all-open")
    sp.add_argument("--all-open", action="store_true",
                    help="Every open claim whose pinned policy differs: print each distinct change once, "
                         "ask once, write one POLICY-ACCEPTED.yaml per leaf")
    add_ref_arg(sp)
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_accept_policy)


def _form_problem(ns: argparse.Namespace) -> str | None:
    """Why the flags are neither the operator form (``--quote``) nor the coordinator form (``--rule``)."""
    if ns.rule is None:
        if ns.rca or ns.alignment or ns.limit:
            return "--rca, --alignment and --limit belong to the coordinator form (--rule)"
        if not (ns.quote or "").strip():
            return "--quote is empty: give the operator's words as they said them, or the coordinator form --rule"
    elif ns.quote is not None:
        return "--quote and --rule are two forms; give one"
    elif ns.decision != ACCEPT_WITH_LIMITS:
        return f"the coordinator form (--rule) records only --decision {ACCEPT_WITH_LIMITS}"
    if not (ns.session or "").strip():
        return "--session is empty: name the session the operator decided in"
    return None


def cmd_operator_decision(ns: argparse.Namespace) -> int:
    if why := role_refusal():   # before anything is read or written
        return _fail(why)
    root = resolve_repo_root(ns)
    if why := _form_problem(ns):
        return _fail(why)
    who = recorder(root)
    if not who:
        return _fail("set git user.name and user.email: the decision entry names who recorded it")
    nodes = load_roadmap(root)["nodes"]
    if any(n.get("parent_id") == ns.node_id for n in nodes):
        return _fail(f"{ns.node_id} has children: an operator decision is for one leaf and one commit")
    try:
        t = resolve_target(root, ns.node_id, nodes=nodes)
    except ReviewTargetError as e:
        return _fail(f"the commit under review does not resolve: {e}")
    gate = evaluate_gate(root, t.node, t.commit, branch=(t.entry or {}).get("branch"))
    sha = gate.commit
    blocks = blocks_to_settle(root, gate, sha)
    cited: list[dict[str, str]] = []
    if ns.rule:
        why, cited = _coordinator_problem(root, ns, gate, t.node, blocks)
        if why:
            return _fail(why)
    try:
        entry, settles = append_decision(root, ns, gate, blocks, who, cited)
    except ValueError as e:   # a copied schema from before decided_by
        return _fail(f"{e}; nothing was written. Run `specy-road refresh-schemas` and try again")
    marker = write_operator_marker(root, entry, sha, ns.session)
    print(f"[ok] decision {entry['id']} closed (decided_by: {entry['decided_by']}) for {ns.node_id} at {sha[:12]}: "
          f"{'; '.join(settles) or 'nothing to settle'}; wrote {marker}")
    print(f"  Commit {DECISIONS_REL.as_posix()} on the integration branch, then `specy-road review status "
          f"{ns.node_id}`. A later commit on the leaf beyond its sheet or review bookkeeping ends the decision.")
    return 0


def add_operator_decision_parser(rsub: Any) -> None:
    sp = rsub.add_parser("operator-decision", help="Coordinator: record the operator's review decision for the "
                                                   "commit under review, or accept with limits under a standing rule")
    sp.add_argument("node_id")
    sp.add_argument("--decision", required=True, choices=[APPROVE, ACCEPT_WITH_LIMITS])
    sp.add_argument("--quote", help="The operator's words, as they said them (operator form)")
    sp.add_argument("--session", required=True, help="The session the operator decided in; kept in the marker")
    sp.add_argument("--rule", metavar="ID", help="Coordinator form: an open standing-rule entry in "
                                                 "roadmap/decisions.yaml; only --decision accept-with-limits")
    sp.add_argument("--rca", action="append", default=[], metavar="MODEL=PATH",
                    help="Coordinator form: a root-cause analysis; give two, of two roster families")
    sp.add_argument("--alignment", action="append", default=[], metavar="MODEL=PATH",
                    help="Coordinator form: an alignment review; give two, of two roster families")
    sp.add_argument("--limit", action="append", default=[], metavar="TEXT",
                    help="Coordinator form: an accepted limit; each counted finding is named in exactly one")
    add_repo_root_arg(sp)
    sp.set_defaults(func=cmd_operator_decision)


def _add_status_parser(subparsers: Any, about: str, func: Any) -> None:
    """``review status`` and its deprecated alias ``handoff status``: one node or every node, ``--json``, ``--ref``."""
    st = subparsers.add_parser("status", help=about)
    st.add_argument("node_id", nargs="?", help="One node (default: every node under work/reviews/)")
    add_json_arg(st, help="Machine-readable output for polling")
    add_ref_arg(st)
    add_repo_root_arg(st)
    st.set_defaults(func=func)


def _add_packet_parser(subparsers: Any) -> None:
    """``review packet``: the flags of :func:`review_packet.build_parser`, which ``review-packet`` also reads."""
    from specy_road.bundled_scripts import review_packet

    packet = review_packet.build_parser()
    sp = subparsers.add_parser("packet", parents=[packet], add_help=False, description=packet.description,
                               formatter_class=packet.formatter_class,
                               help="Write work/reviews/<NODE_ID>/PACKET.md, the verification packet reviewers read")
    sp.set_defaults(func=cmd_review_packet)


def cmd_review_packet(ns: argparse.Namespace) -> int:
    """``review packet``: write the packet, as ``review-packet`` does."""
    from specy_road.bundled_scripts.review_packet import write_packet

    write_packet(ns)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="specy-road")
    sub = p.add_subparsers(dest="cmd", required=True)

    handoff = sub.add_parser("handoff", help=f"Deprecated: use review status (removed in {ALIASES_REMOVED_IN})")
    hsub = handoff.add_subparsers(dest="handoff_cmd", required=True)
    _add_status_parser(hsub, f"Deprecated: use review status (removed in {ALIASES_REMOVED_IN}). Report "
                             "hand-offs, reviews, and whether review policy is met", cmd_handoff_status)

    review = sub.add_parser("review", help="Review records")
    rsub = review.add_subparsers(dest="review_cmd", required=True)
    _add_status_parser(rsub, "Report hand-offs, review records (verdict, commit, family), and whether review "
                             "policy is met; reads only", cmd_review_status)
    _add_packet_parser(rsub)
    rec = rsub.add_parser("record", help="Validate a reviewer's notes and file them as a review record")
    rec.add_argument("node_id")
    add_model_arg(rec, help="Reviewer model id from the roster (not human)", required=True)
    rec.add_argument("--verdict", required=True, choices=["approve", "block"])
    rec.add_argument("--file", required=True, help="Markdown with review-record front matter")
    add_ref_arg(rec)
    rec.add_argument("--sign-key", metavar="PATH", help="Sign the record with this OpenSSH private key (ssh-keygen -Y sign)")
    rec.add_argument("--launch-mode", choices=REVIEW_LAUNCH_MODES, help="How your harness was started; stored on the record")
    rec.add_argument("--human-filed", metavar="WHO_AND_WHY",
                     help="Required when no harness or worker is identified (a human filing by hand): one non-blank line saying "
                          "who files this and why; stored as human_filed, which counts only signed or under "
                          "policy.count_human_filed_reviews")
    add_repo_root_arg(rec)
    rec.set_defaults(func=cmd_review_record_locked)
    for name, about, fn in (("list", f"Deprecated: use review status (removed in {ALIASES_REMOVED_IN}). Print a "
                                     "node's filed review records and the gate evaluation; writes nothing",
                             cmd_review_list),
                            ("check-pre-existing", "Re-run claimed pre-existing verifier failures twice on the integration tip",
                             cmd_check_pre_existing),
                            ("red-green", "Run the tests a leaf adds or changes at its merge base and at head", cmd_red_green)):
        sp = rsub.add_parser(name, help=about)
        sp.add_argument("node_id")
        add_ref_arg(sp)
        if name == "list":
            add_json_arg(sp, help="Machine-readable output including refused markers")
        add_repo_root_arg(sp)
        sp.set_defaults(func=fn)
    add_delegate_parser(rsub)
    add_defer_parser(rsub)
    add_accept_policy_parser(rsub)
    add_operator_decision_parser(rsub)
    add_ready_parser(sub)
    return p


def main(argv: list[str] | None = None) -> None:
    """Run a review command. A command error is printed once and becomes its exit code."""
    run_cli(build_parser, argv)
if __name__ == "__main__":
    main()
