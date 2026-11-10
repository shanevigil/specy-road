"""``specy-road grind-session --status``: a goal's leaves by state, a completion range, and what waits on a person.

Read-only (M22.68). The scope is ``--until`` (the goal's leaves and everything they need), ``--under`` (a
subtree), both (their intersection), or the parent in ``work/.milestone-session.yaml``. Leaves are bucketed
from the same git-enriched plan ``--plan`` computes (:func:`gather_session_plan` with no scope, filtered here),
and each claimed leaf's review state comes from :func:`review_cli.review_state`, which runs no trial merge.
The estimate reads ``history_index`` (it may write its cache under ``.specyrd/cache/``, as ``specy-road
history`` does); nothing else is written, nothing is fetched and no harness is called. Every option,
recommendation and next step printed is the record's own text.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from specy_road.brainstorm_session import BrainstormError, list_slugs, read_session, session_path
from specy_road.bundled_scripts.review_cli import rca_command, review_state
from specy_road.decisions import open_questions
from specy_road.decisions_local import LOCAL, SHARED, load_merged
from specy_road.git_subprocess import git_ok, head_sha
from specy_road.git_workflow_config import load_git_workflow_config
from specy_road.history_events import STATUS
from specy_road.history_index import events, history_index
from specy_road.milestone_session import milestone_session_path, read_milestone_session
from specy_road.milestone_subtree import leaf_ids_under_parent, subtree_node_ids
from specy_road.node_kinds import is_gate
from specy_road.review_target import ReviewTargetError
from specy_road.roadmap_index import RoadmapIndex
from specy_road.roadmap_layout import natural_id_sort_key
from specy_road.session_plan_git import gather_session_plan
from specy_road.session_presence import list_sessions
from specy_road.worker_state import FLAG_NEEDS_PERSON, list_records

INTERVAL_KEY = "grind_session_status_interval_minutes"
DEFAULT_INTERVAL_MINUTES = 30
MIN_COMPLETIONS = 5
MIN_SPAN = timedelta(hours=24)
WINDOW = timedelta(days=7)
HELD_REVIEW_STATES = ("escalated", "fix_round_budget_spent", "executor_blocked")
UNMERGED = "Complete on its feature branch; the integration branch has not merged it"
NO_OPTIONS = "no options recorded (not a ledger entry)"
PROS_CONS = "not recorded: the decisions schema has no field for them"
NO_RECENT = "none at the recent pace (no completions in 7 days)"
ASSUMPTION = "held and waiting leaves are assumed to clear at the past pace"
SEPARATOR = "-" * 72


class StatusError(Exception):
    """A scope or interval the command cannot use; exit 2 with this message."""


# --- scope -------------------------------------------------------------------


def _leaves_of(index: RoadmapIndex, node: dict) -> list[dict]:
    if node["id"] in index.leaf_ids:
        return [node]
    return [index.by_id[i] for i in leaf_ids_under_parent(node["id"], index.nodes)]


def until_closure(index: RoadmapIndex, goal_id: str) -> set[str]:
    """Display ids ``goal_id`` needs before it closes: its leaves, then the effective dependencies of every node
    added that is not Complete, a group adding its leaves; a Complete dependency adds its leaves, not followed."""
    out = {goal_id}
    seen: set[str] = set()
    stack = [(leaf, True) for leaf in _leaves_of(index, index.by_id[goal_id])]
    while stack:
        node, follow = stack.pop()
        key = node.get("node_key") or node["id"]
        if key in seen:
            continue
        seen.add(key)
        out.add(node["id"])
        if not follow or index.status.get(key) == "complete":
            continue
        for dep_key in index.effective_dependencies.get(key, ()):
            dep = index.by_key[dep_key]
            out.add(dep["id"])
            done = index.status.get(dep_key) == "complete"
            stack.extend((leaf, not done) for leaf in _leaves_of(index, dep))
    return out


def resolve_scope(root: Path, index: RoadmapIndex, until: str | None, under: str | None) -> dict[str, Any]:
    """``{rule, until, under, nodes, leaves}``; :class:`StatusError` for no scope or an unknown node."""
    source = None
    if not until and not under:
        session = read_milestone_session(milestone_session_path(root / "work"))
        if session is None:
            raise StatusError("grind-session --status needs a scope: pass --until NODE or --under NODE, or start "
                              "a milestone session with `specy-road start-milestone-session <PARENT_NODE_ID>`")
        under, source = session.parent_node_id, "work/.milestone-session.yaml"
    for nid in (until, under):
        if nid and nid not in index.by_id:
            raise StatusError(f"no node {nid}")
    nodes = until_closure(index, until) if until else subtree_node_ids(under, index.nodes)
    if until and under:
        nodes &= subtree_node_ids(under, index.nodes)
        rule = f"until {until} within under {under}: the leaves {until} needs, inside {under}'s subtree"
    elif until:
        rule = f"until {until}: {until}'s leaves and everything they need"
    else:
        rule = f"under {under}: its subtree" + (f" (from {source})" if source else "")
    leaves = [i for i in nodes if i in index.leaf_ids and not is_gate(index.by_id[i].get("type"))]
    return {"rule": rule, "until": until, "under": under, "nodes": nodes,
            "leaves": sorted(leaves, key=natural_id_sort_key)}


# --- buckets -----------------------------------------------------------------


def _worker_dict(w) -> dict[str, Any]:
    return {"id": w.worker_id, "harness": w.harness, "state": w.state, "lease": w.lease.get("holder"),
            "flags": list(w.flags)}


def _held_reasons(root: Path, index: RoadmapIndex, node: dict, claimed: bool, worker) -> tuple[list, dict]:
    """``(reasons, review)`` for one open leaf: each reason names its record's next step."""
    nid = node["id"]
    reasons: list[dict[str, Any]] = []
    for gate in sorted((index.by_key[d]["id"] for d in index.unmet(node) if is_gate(index.by_key[d].get("type"))),
                       key=natural_id_sort_key):
        reasons.append({"kind": "gate", "reason": f"open gate {gate} among its unmet dependencies",
                        "next": [f"specy-road set-gate-status {gate} --status Complete"]})
    review: dict[str, Any] = {}
    if claimed:
        try:
            rs = review_state(root, nid)
        except ReviewTargetError as e:   # a claim whose branch this clone does not have
            review = {"state": None, "error": f"not evaluated: {e}"}
        else:
            review = {"state": rs.state}
            reasons += _review_reasons(nid, rs)
    if worker is not None and (worker.lease.get("holder") == "human" or FLAG_NEEDS_PERSON in worker.flags):
        why = "leased to human" if worker.lease.get("holder") == "human" else f"flagged {FLAG_NEEDS_PERSON}"
        nxt = (f"specy-road worker reclaim {worker.worker_id}" if worker.lease.get("holder") == "human"
               else f"specy-road worker status {worker.worker_id}")
        reasons.append({"kind": "worker", "reason": f"worker {worker.worker_id} {why}", "next": [nxt]})
    return reasons, review


def _review_reasons(nid: str, rs) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if rs.state == "escalated":
        out.append({"kind": "escalated", "reason": f"escalated: {rs.loop.escalation.describe()}",
                    "next": [rca_command(nid)]})
    elif rs.state == "fix_round_budget_spent":
        b = rs.budget
        out.append({"kind": "fix_round_budget_spent",
                    "reason": f"fix_round_budget_spent: {b['blocking_rounds']} blocking round(s), "
                              f"policy.max_fix_rounds {b['max_fix_rounds']}; {b['next_why']}",
                    "next": [b["next"]] if b.get("next") else []})
    elif rs.state == "executor_blocked":
        out.append({"kind": "executor_blocked", "reason": "executor blocked", "next": list(rs.executor_blocked)})
    if rs.gate.policy_pin:
        out.append({"kind": "policy_pin", "reason": rs.gate.policy_pin,
                    "next": [f"specy-road review accept-policy {nid}"]})
    return out


def _open_bucket(plan, node: dict, item: dict, own: str, claimed: bool, reasons: list, review: dict,
                 waiting: dict, unauthored: dict) -> tuple[str | None, dict]:
    """The bucket of one open leaf and its entry, first match wins (A2); ``(None, item)`` when none matches."""
    nid = item["id"]
    if reasons:
        return "held", {**item, "claimed": claimed, "reasons": reasons, **review}
    if claimed or own == "in progress":
        note = {"note": f"feature tip is {UNMERGED}"} if nid in plan.finished_claimed else {}
        error = {"review_error": review["error"]} if "error" in review else {}
        return "active", {**item, "claimed": claimed, "status": node.get("status"),
                          "review": review.get("state"), **error, **note}
    if nid in plan.ready:
        return "ready", item
    if nid in waiting:
        return "waiting", {**item, "waiting_on": list(waiting[nid].waiting_on)}
    if nid in plan.finished_unmerged:
        return "awaiting_merge", {**item, "reason": UNMERGED}
    if nid in unauthored:
        return "not_pickable", {**item, "reason": unauthored[nid]}
    if nid in plan.needs_codename:
        return "not_pickable", {**item, "reason": "needs a codename"}
    return None, item


def classify(root: Path, index: RoadmapIndex, plan, reg: dict, leaves: list[str]) -> dict[str, list]:
    """Each scoped non-gate leaf in one bucket, first match wins (A2)."""
    claimed = {e.get("node_id") for e in reg.get("entries") or [] if e.get("node_id")}
    workers = {w.node_id: w for w in list_records(root, active_only=True)}   # worker_state.active_for_node
    waiting = {b.node_id: b for b in plan.blocked if b.reason == "dependency"}
    unauthored = {u.node_id: u.reason for u in plan.unauthored}
    out: dict[str, list] = {k: [] for k in ("done", "cancelled", "held", "active", "ready", "waiting",
                                            "awaiting_merge", "not_pickable")}
    for nid in leaves:
        node = index.by_id[nid]
        item: dict[str, Any] = {"id": nid, "title": node.get("title") or ""}
        own = (node.get("status") or "Not Started").lower()
        if own in ("complete", "cancelled"):
            out["done" if own == "complete" else "cancelled"].append(item)
            continue
        worker = workers.get(nid)
        reasons, review = _held_reasons(root, index, node, nid in claimed, worker)
        if worker is not None:
            item["worker"] = _worker_dict(worker)
        bucket, entry = _open_bucket(plan, node, item, own, nid in claimed, reasons, review, waiting, unauthored)
        if bucket:
            out[bucket].append(entry)
    return out


def totals(buckets: dict[str, list]) -> dict[str, int]:
    t = {k: len(v) for k, v in buckets.items()}
    t["total"] = sum(t.values())
    t["remaining"] = t["total"] - t["done"] - t["cancelled"]
    return t


# --- estimate ----------------------------------------------------------------


def completions(root: Path, index: RoadmapIndex, done_ids: list[str]) -> list[tuple[datetime, str]]:
    """``(at, id)`` of each done leaf's earliest status event to Complete, matched by its current ``node_key``."""
    keys = {index.by_id[i].get("node_key"): i for i in done_ids if index.by_id[i].get("node_key")}
    first: dict[str, datetime] = {}
    for e in events(history_index(root)):
        key = e.get("node_key")
        if key in keys and e.get("kind") == STATUS and e.get("to") == "Complete" and e.get("at"):
            at = datetime.fromisoformat(str(e["at"]))
            first[key] = min(first.get(key, at), at)
    return sorted((at, keys[k]) for k, at in first.items())


def estimate(found: list[tuple[datetime, str]], remaining: int, now: datetime) -> dict[str, Any]:
    """The completion range from two observed rates (A3); ``reason`` set when there is not enough data."""
    n = len(found)
    inputs: dict[str, Any] = {
        "n": n, "first": found[0][0].isoformat() if found else None, "last": found[-1][0].isoformat() if found else None,
        "recent": sum(1 for at, _ in found if now - WINDOW <= at <= now), "window_days": WINDOW.days,
        "minimum": MIN_COMPLETIONS, "minimum_span_hours": int(MIN_SPAN.total_seconds() // 3600),
        "remaining": remaining, "completions": [{"id": i, "at": at.isoformat()} for at, i in found],
    }
    method = ("overall rate (n-1)/(last-first) and recent rate (completions in the last 7 days)/7 days; earliest is "
              "now + remaining / the faster rate, latest now + remaining / the slower; " + ASSUMPTION)
    out = {"method": method, "inputs": inputs, "earliest": None, "latest": None, "reason": None}
    if n < MIN_COMPLETIONS:
        out["reason"] = f"not enough data: {n} completion(s) in scope, minimum {MIN_COMPLETIONS}"
        return out
    span = found[-1][0] - found[0][0]
    if span < MIN_SPAN:
        out["reason"] = (f"not enough data: {n} completions span {span.total_seconds() / 3600:.1f} hours, "
                         f"minimum {inputs['minimum_span_hours']} hours")
        return out
    overall = (n - 1) / span.total_seconds()   # per second
    recent = inputs["recent"] / WINDOW.total_seconds()
    if recent == 0:
        out["earliest"] = (now + timedelta(seconds=round(remaining / overall))).isoformat()
        out["latest"] = NO_RECENT
        return out
    fast, slow = max(overall, recent), min(overall, recent)
    out["earliest"] = (now + timedelta(seconds=round(remaining / fast))).isoformat()
    out["latest"] = (now + timedelta(seconds=round(remaining / slow))).isoformat()
    return out


# --- decisions and sessions --------------------------------------------------

_LEDGER_FIELDS = ("node", "summary", "why_now", "options", "recommendation", "recommendation_reason",
                  "default_if_unanswered", "needed_by")


def ledger(root: Path, scope_nodes: set[str], missing: list[dict]) -> tuple[list, list]:
    """Open decision and human-action entries, in scope (every recorded field) and outside it (one line)."""
    doc, local_ids, problems = load_merged(root)
    missing += [{"record": "decisions ledger", "field": p} for p in problems]
    inside, outside = [], []
    for e in open_questions(doc):
        if e.get("node") not in scope_nodes:
            outside.append({"id": e["id"], "node": e.get("node"), "summary": e.get("summary")})
            continue
        row = {"id": e["id"], "kind": e.get("kind"), **{f: e.get(f) for f in _LEDGER_FIELDS},
               "pros_cons": PROS_CONS, "ledger": LOCAL if e["id"] in local_ids else SHARED}
        missing += [{"record": e["id"], "field": f} for f in _LEDGER_FIELDS if e.get(f) in (None, "", [])]
        inside.append(row)
    return inside, outside


def sessions(root: Path, now: datetime, missing: list[dict]) -> dict[str, list]:
    """Open brainstorm sessions and live presence sessions, whatever the goal scope."""
    brainstorm = []
    for slug in list_slugs(root):
        try:
            s = read_session(root, slug)
        except BrainstormError as e:   # one bad file is named and hides nothing else
            missing.append({"record": f"work/{session_path(root, slug).name}", "field": f"unreadable: {e}"})
            continue
        brainstorm.append({"slug": slug, "mode": s.mode, "ideas": len(s.ideas)})
    presence = []
    for s in list_sessions(root, live_only=True, now=now):
        presence.append({"agent": s.agent, "branch": s.branch, "note": s.note, "expires": s.expires,
                         "stale_reason": s.stale_reason()})
        missing += [{"record": f"session {s.agent}", "field": f} for f in ("branch", "note") if not getattr(s, f)]
    return {"brainstorm": brainstorm, "presence": presence}


# --- report ------------------------------------------------------------------


def build_report(root: Path, until: str | None, under: str | None, now: datetime) -> dict[str, Any]:
    """The status object (A6). :class:`StatusError` for a bad scope."""
    nodes, reg, plan = gather_session_plan(root, None)
    index = RoadmapIndex(nodes)
    scope = resolve_scope(root, index, until, under)
    buckets = classify(root, index, plan, reg, scope["leaves"])
    tot = totals(buckets)
    missing: list[dict] = []
    inside, outside = ledger(root, scope["nodes"], missing)
    held = [{"node": h["id"], **r, "options": NO_OPTIONS} for h in buckets["held"] for r in h["reasons"]]
    ok, branch = git_ok(["symbolic-ref", "-q", "--short", "HEAD"], root)
    return {
        "generated_at": now.isoformat(),
        "source": {"branch": branch.strip() if ok else None, "head": head_sha(root), "fetched": False},
        "goal": until or scope["under"],
        "scope": {"rule": scope["rule"], "until": scope["until"], "under": scope["under"], "leaves": scope["leaves"]},
        "totals": tot,
        **{k: buckets[k] for k in ("held", "active", "ready", "waiting", "awaiting_merge", "not_pickable")},
        "estimate": estimate(completions(root, index, [d["id"] for d in buckets["done"]]), tot["remaining"], now),
        "decisions": {"ledger": inside, "ledger_outside_scope": outside, "held": held},
        "sessions": sessions(root, now, missing),
        "missing": missing,
    }


def _leaf_lines(title: str, items: list[dict], fmt: Callable[[dict], str]) -> list[str]:
    return [f"{title} ({len(items)}):"] + ([f"  {fmt(i)}" for i in items] or ["  (none)"])


def _active_line(a: dict) -> str:
    w = a.get("worker")
    parts = [f"review {a['review'] or a.get('review_error') or 'none (no claim)'}"]
    if w:
        parts.append(f"worker {w['id']} ({w['harness']}, {w['state']})")
    if a.get("note"):
        parts.append(a["note"])
    return f"{a['id']} {a['title']}: " + "; ".join(parts)


def _estimate_lines(e: dict) -> list[str]:
    i = e["inputs"]
    lines = ["Estimate:", f"  method: {e['method']}",
             f"  inputs: n={i['n']}, first {i['first'] or '-'}, last {i['last'] or '-'}, recent {i['recent']} in "
             f"{i['window_days']} days, minimum {i['minimum']} completions over {i['minimum_span_hours']} hours, "
             f"remaining {i['remaining']}"]
    if e["reason"]:
        return lines + [f"  {e['reason']}"]
    return lines + [f"  earliest: {e['earliest']}", f"  latest: {e['latest']}"]


def _decision_lines(d: dict) -> list[str]:
    lines = ["Decisions waiting on a person:"]
    for e in d["ledger"]:
        opts = "; ".join(f"{o['label']} ({o['effect']})" for o in e["options"] or []) or "-"
        lines += [f"  {e['id']} [{e['kind']}] node {e['node']} ({e['ledger']} ledger), needed-by {e['needed_by'] or '-'}",
                  f"    {e['summary']}", f"    why now: {e['why_now']}", f"    options: {opts}",
                  f"    recommendation: {e['recommendation']} — {e['recommendation_reason']}",
                  f"    default if unanswered: {e['default_if_unanswered']}", f"    pros/cons: {e['pros_cons']}"]
    lines += [f"  outside scope: {e['id']} node {e['node']}: {e['summary']}" for e in d["ledger_outside_scope"]]
    for h in d["held"]:
        lines += [f"  held {h['node']}: {h['reason']}"] + [f"    next: `{n}`" for n in h["next"]]
        lines.append(f"    {h['options']}")
    return lines + (["  (none)"] if len(lines) == 1 else [])


def render_text(r: dict[str, Any]) -> str:
    t, src = r["totals"], r["source"]
    when = datetime.fromisoformat(r["generated_at"]).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [f"Grind status: goal {r['goal']}", f"  scope: {r['scope']['rule']}",
             "  totals: " + ", ".join(f"{k.replace('_', ' ')} {t[k]}" for k in (
                 "total", "done", "cancelled", "remaining", "held", "active", "ready", "waiting",
                 "awaiting_merge", "not_pickable")),
             f"  as of {src['branch'] or '(detached HEAD)'} @ {(src['head'] or '?')[:12]}, this checkout, not fetched",
             f"  last updated {when}"]
    lines += _leaf_lines("Held", r["held"], lambda h: f"{h['id']} {h['title']}: "
                         + "; ".join(x["reason"] for x in h["reasons"]))
    lines += _leaf_lines("Active", r["active"], _active_line)
    lines += _leaf_lines("Ready", r["ready"], lambda x: f"{x['id']} {x['title']}")
    lines += _leaf_lines("Waiting", r["waiting"], lambda x: f"{x['id']} {x['title']}: waiting on "
                         + ", ".join(x["waiting_on"]))
    lines += _leaf_lines("Finished, awaiting merge", r["awaiting_merge"], lambda x: f"{x['id']} {x['title']}: {x['reason']}")
    lines += _leaf_lines("Not pickable", r["not_pickable"], lambda x: f"{x['id']} {x['title']}: {x['reason']}")
    lines += _estimate_lines(r["estimate"]) + _decision_lines(r["decisions"])
    s = r["sessions"]
    lines += _leaf_lines("Open brainstorm sessions", s["brainstorm"],
                         lambda b: f"{b['slug']} ({b['mode']}, {b['ideas']} ideas)")
    lines += _leaf_lines("Live sessions", s["presence"], lambda p: f"{p['agent']} on {p['branch'] or '-'}, "
                         f"expires {p['expires']}, note: {p['note'] or '-'}"
                         + (f", stale: {p['stale_reason']}" if p["stale_reason"] else ""))
    if r["missing"]:
        lines += ["Missing:"] + [f"  {m['record']}: {m['field']}" for m in r["missing"]]
    return "\n".join(lines)


# --- command -----------------------------------------------------------------


def watch_seconds(root: Path, watch) -> int:
    """``--watch MINUTES``, else ``grind_session_status_interval_minutes``, else 30, in seconds."""
    if watch is not True:
        return int(watch) * 60
    data, err = load_git_workflow_config(root)
    if err:
        raise StatusError(err)
    return int((data or {}).get(INTERVAL_KEY) or DEFAULT_INTERVAL_MINUTES) * 60


def _local_now() -> datetime:
    return datetime.now().astimezone()


def run_status(root: Path, args, *, clock: Callable[[], datetime] = _local_now,
               sleep: Callable[[float], None] = time.sleep) -> int:
    """Print the report (``--json``: one object per line), every interval with ``--watch``; 2 on a bad scope."""
    try:
        seconds = watch_seconds(root, args.watch) if args.watch is not None else None
        while True:
            report = build_report(root, args.until, args.under, clock())
            if args.json:
                print(json.dumps(report), flush=True)
            else:
                print(("\n" + SEPARATOR + "\n" if seconds is not None else "") + render_text(report), flush=True)
            if seconds is None:
                return 0
            sleep(seconds)
    except StatusError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
