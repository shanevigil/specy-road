"""Handlers for the brainstorm v2 subcommands (rounds, frame, evidence, verify, park)."""

from __future__ import annotations

import argparse
import sys
from datetime import date

from specy_road.bundled_scripts.brainstorm_fields import source_record
from specy_road.bundled_scripts.brainstorm_prompt import (
    render_brainstorm_prompt,
    render_evidence_prompt,
    render_shard_prompt,
    write_prompt,
)
from specy_road.bundled_scripts.brainstorm_prompt_evidence import MAX_EVIDENCE_IDEAS, shortlist
from specy_road.bundled_scripts.brainstorm_promote import pending_ideas
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    read_session,
    resolve_slug,
    session_lock,
    set_status,
    write_session,
)
from specy_road.bundled_scripts.roadmap_load import load_roadmap
from specy_road.bundled_scripts.brainstorm_verify import confirm, pending, verify_session
from specy_road.git_subprocess import current_branch_name
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.runtime_paths import resolve_repo_root

DEFAULT_COUNT = 20


def print_idea_summary(session: BrainstormSession) -> None:
    from specy_road.bundled_scripts.brainstorm_session import IDEA_STATUSES, RECOMMENDATIONS

    by_status = {s: 0 for s in IDEA_STATUSES}
    for idea in session.ideas:
        by_status[idea.status] += 1
    by_rec = {r: 0 for r in RECOMMENDATIONS}
    by_rec["-"] = 0
    for idea in session.ideas:
        key = idea.recommendation if idea.recommendation in RECOMMENDATIONS else "-"
        by_rec[key] += 1
    print("status:")
    for name in IDEA_STATUSES:
        print(f"  {name}: {by_status[name]}")
    print("recommendation:")
    for name in (*RECOMMENDATIONS, "-"):
        print(f"  {name}: {by_rec[name]}")


def _load(ns: argparse.Namespace) -> tuple:
    root = resolve_repo_root(ns)
    return root, read_session(root, resolve_slug(root, getattr(ns, "slug", None)))


def write_round_prompts(root, session: BrainstormSession, *, count: int) -> list:
    """The round prompt, plus one shard prompt per panel worker in round 1."""
    text = render_brainstorm_prompt(root, session, count=count)
    paths = [write_prompt(root, session, text, pass_name=f"r{session.round}")]
    if session.panel and session.round <= 1:
        paths += _write_shard_prompts(root, session, count=count)
    return paths


def _write_shard_prompts(root, session: BrainstormSession, *, count: int) -> list:
    per = max(1, -(-count // session.panel))
    return [write_prompt(root, session, render_shard_prompt(root, session, count=per, shard=k, total=session.panel),
                         pass_name=f"r{session.round}-s{k}") for k in range(1, session.panel + 1)]


def next_step(session: BrainstormSession, done: str) -> str:
    """The command that follows ``done``: round -> recommend -> evidence/verify -> triage -> promote."""
    cmd = f"specy-road brainstorm {{}} --slug {session.slug}".format
    if done == "round":
        follow = (f"`{cmd('next-round')}` (round {session.round + 1} of {session.rounds})"
                  if session.round < session.rounds else f"`{cmd('recommend')}`")
        return f"next: when the agent has recorded its ideas, {follow}"
    return "next: " + {
        "recommend": f"when the verdicts are recorded, `{cmd('evidence')}` for the shortlist, "
                     f"then `{cmd('verify')}`",
        "evidence": f"when the sources are recorded, `{cmd('verify')}`",
        "verify": f"triage: `{cmd('list --by cluster')}`, then accept / reject --reason / park --reason",
        "triage": f"when triage is done, `{cmd('promote --dry-run')}`, then `{cmd('promote')}`",
        "dry-run": f"`{cmd('promote')}` to apply",
        "promote": f"`specy-road export && specy-road digest`, then `{cmd('close')}`",
    }[done]


def stage(session: BrainstormSession) -> str:
    """The pass ``session`` is in, read from what it records: the ``done`` key for ``next_step``."""
    if session.mode != "roadmap":
        return "round"
    if any(i.promoted_node_key for i in session.ideas) and not pending_ideas(session):
        return "promote"
    if any(i.status in ("accepted", "rejected", "parked") for i in session.ideas):
        return "triage"
    if any(i.sources for i in session.ideas):
        return "evidence" if pending(session.ideas) else "verify"
    return "recommend"


def integration_branch_warning(root, slug: str) -> str | None:
    """A warning when ``start`` runs on the integration branch, where the tracked session would land."""
    base, _remote, _warnings = resolve_integration_defaults(root, explicit_base=None, explicit_remote=None)
    if current_branch_name(root) != base:
        return None
    return (f"warning: on the integration branch {base!r}; the session file is tracked, so brainstorm "
            f"on a branch of its own: git checkout -b chore/brainstorm-{slug}")


def cmd_next_round(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    if not session.ideas:
        raise BrainstormError("no ideas yet — run the round-1 prompt first, or `brainstorm start` again")
    session.round += 1
    session.mode = "brainstorm"
    write_session(root, session)
    count = ns.count or DEFAULT_COUNT
    ppath = write_round_prompts(root, session, count=count)[0]
    print(f"round {session.round} of {session.rounds}: {ppath.relative_to(root)} ({len(session.ideas)} ideas in the pool)")
    if session.round > session.rounds:
        print(f"note: past the {session.rounds} round(s) planned at `start --rounds`; converge is usually next",
              file=sys.stderr)
    print(next_step(session, "round"))
    return 0


def cmd_frame(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    for item in ns.answer:
        key, sep, text = item.partition("=")
        if not sep or not key.strip() or not text.strip():
            raise BrainstormError(f"--answer {item!r}: expected KEY=TEXT")
        session.frame[key.strip()] = text.strip()
    if ns.allocation is not None:
        session.allocation = ns.allocation.strip()
    write_session(root, session)
    print(f"[ok] frame: {len(session.frame)} answer(s)" + (", allocation recorded" if session.allocation else ""))
    if session.panel and session.round <= 1:
        # Shards are written at `start`, before any frame exists; rewrite them so they carry it.
        for path in _write_shard_prompts(root, session, count=session.count or DEFAULT_COUNT):
            print(f"shard:   {path.relative_to(root)} (rewritten)")
    print(next_step(session, stage(session)))
    return 0


def cmd_evidence(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    ideas = shortlist(session, list(ns.idea_id))
    if not ideas:
        raise BrainstormError("nothing to source — name idea ids, or run `recommend` so some are strong")
    if len(ideas) > MAX_EVIDENCE_IDEAS:
        print(f"warning: {len(ideas)} ideas selected; an evidence pass over more than {MAX_EVIDENCE_IDEAS} "
              "gets shallow — name the ids to source and run `evidence` in batches", file=sys.stderr)
    ppath = write_prompt(root, session, render_evidence_prompt(session, ideas), pass_name="evidence")
    print(f"prompt: {ppath.relative_to(root)} ({len(ideas)} idea(s) to source)")
    print(next_step(session, "evidence"))
    return 0


def cmd_add_evidence(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    idea = session.by_id(ns.idea_id)
    if not (ns.quote or "").strip():
        raise BrainstormError("--quote is required: a URL with no quote is not evidence (verify checks the quote)")
    if len(ns.quote or "") > 300:
        raise BrainstormError("--quote must be 300 characters or fewer: quote, do not paraphrase")
    rec = source_record(ns.url, quote=ns.quote, supports=ns.supports, stance=ns.stance, tool=ns.tool,
                        source_type=ns.source_type, retrieved_at=ns.retrieved_at or date.today().isoformat())
    idea.sources.append(rec)
    if rec["url"] not in idea.evidence:
        idea.evidence.append(rec["url"])
    write_session(root, session)
    print(f"[ok] {idea.id} source {len(idea.sources)}: {rec['url']} ({rec['stance']})")
    print(next_step(session, stage(session)))
    return 0


def cmd_verify(ns: argparse.Namespace) -> int:
    """Ask and fetch without the brainstorm lock; take it only to merge the results into a fresh read."""
    root, session = _load(ns)
    ideas = [session.by_id(i) for i in ns.idea_id] if ns.idea_id else session.ideas
    todo = pending(ideas)
    if not todo:
        print("verify: nothing unverified")
        print(next_step(session, "verify"))
        return 0
    if not confirm(sorted({str(s.get("url")) for _i, s in todo}), yes=ns.yes):
        return 1
    for line in verify_session(session, ideas):
        print(line)
    results = {(i.id, s.get("url"), s.get("quote")): s["verification"] for i, s in todo}
    with session_lock(root):   # ideas and sources added meanwhile are kept
        fresh = read_session(root, session.slug)
        for idea, src in pending(fresh.ideas):
            src["verification"] = results.get((idea.id, src.get("url"), src.get("quote")), "unverified")
        write_session(root, fresh)
    print(next_step(fresh, "verify"))
    return 0


def cmd_park(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    ideas = [set_status(session, ident, "parked") for ident in ns.idea_id]
    for idea in ideas:
        idea.decision = {"status": "parked", "reason": ns.reason.strip(), "decided_at": date.today().isoformat()}
        if ns.revisit_when.strip():
            idea.decision["revisit_when"] = ns.revisit_when.strip()
        print(f"[ok] {idea.id} parked")
    write_session(root, session)
    print(next_step(session, "triage"))
    return 0


def cmd_realize(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    idea = session.by_id(ns.idea_id)
    if idea.promoted_node_key:
        raise BrainstormError(
            f"idea {idea.id} is already on the roadmap as {idea.promoted_node_key} — "
            "edit the node instead"
        )
    node_id = (ns.node or "").strip()
    match = next((n for n in load_roadmap(root)["nodes"] if n.get("id") == node_id), None)
    if match is None:
        raise BrainstormError(f"node {node_id!r} is not in the roadmap")
    idea.promoted_node_key = match["node_key"]
    write_session(root, session)
    print(f"[ok] {idea.id} -> {node_id} ({idea.promoted_node_key[:8]})")
    print(next_step(session, stage(session)))
    return 0


HANDLERS_V2 = {
    "next-round": cmd_next_round,
    "frame": cmd_frame,
    "evidence": cmd_evidence,
    "add-evidence": cmd_add_evidence,
    "verify": cmd_verify,
    "park": cmd_park,
    "realize": cmd_realize,
}

__all__ = ["HANDLERS_V2", "integration_branch_warning", "next_step", "stage", "write_round_prompts", "sys"]
