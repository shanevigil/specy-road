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
from specy_road.bundled_scripts.brainstorm_prompt_evidence import shortlist
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    read_session,
    resolve_slug,
    set_status,
    write_session,
)
from specy_road.bundled_scripts.brainstorm_verify import confirm, pending, verify_session
from specy_road.runtime_paths import resolve_repo_root

DEFAULT_COUNT = 20


def _load(ns: argparse.Namespace) -> tuple:
    root = resolve_repo_root(ns)
    return root, read_session(root, resolve_slug(root, getattr(ns, "slug", None)))


def write_round_prompts(root, session: BrainstormSession, *, count: int) -> list:
    """The round prompt, plus one shard prompt per panel worker in round 1."""
    paths = [write_prompt(root, session, render_brainstorm_prompt(root, session, count=count))]
    if session.panel and session.round <= 1:
        per = max(1, -(-count // session.panel))
        for k in range(1, session.panel + 1):
            text = render_shard_prompt(root, session, count=per, shard=k, total=session.panel)
            paths.append(write_prompt(root, session, text, suffix=f"-s{k}"))
    return paths


def cmd_next_round(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    if not session.ideas:
        raise BrainstormError("no ideas yet — run the round-1 prompt first, or `brainstorm start` again")
    session.round += 1
    session.mode = "brainstorm"
    write_session(root, session)
    count = ns.count or DEFAULT_COUNT
    ppath = write_round_prompts(root, session, count=count)[0]
    print(f"round {session.round}: {ppath.relative_to(root)} ({len(session.ideas)} ideas in the pool)")
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
    return 0


def cmd_evidence(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    ideas = shortlist(session, list(ns.idea_id))
    if not ideas:
        raise BrainstormError("nothing to source — name idea ids, or run `recommend` so some are strong/consider")
    ppath = write_prompt(root, session, render_evidence_prompt(session, ideas), suffix="-evidence")
    print(f"prompt: {ppath.relative_to(root)} ({len(ideas)} idea(s) to source)")
    return 0


def cmd_add_evidence(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    idea = session.by_id(ns.idea_id)
    if len(ns.quote or "") > 300:
        raise BrainstormError("--quote must be 300 characters or fewer: quote, do not paraphrase")
    rec = source_record(ns.url, quote=ns.quote, supports=ns.supports, stance=ns.stance, tool=ns.tool,
                        source_type=ns.source_type, retrieved_at=ns.retrieved_at or date.today().isoformat())
    idea.sources.append(rec)
    if rec["url"] not in idea.evidence:
        idea.evidence.append(rec["url"])
    write_session(root, session)
    print(f"[ok] {idea.id} source {len(idea.sources)}: {rec['url']} ({rec['stance']})")
    return 0


def cmd_verify(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    ideas = [session.by_id(i) for i in ns.idea_id] if ns.idea_id else session.ideas
    todo = pending(ideas)
    if not todo:
        print("verify: nothing unverified")
        return 0
    if not confirm(sorted({str(s.get("url")) for _i, s in todo}), yes=ns.yes):
        return 1
    for line in verify_session(session, ideas):
        print(line)
    write_session(root, session)
    return 0


def cmd_park(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    for ident in ns.idea_id:
        idea = set_status(session, ident, "parked")
        idea.decision = {"status": "parked", "reason": ns.reason.strip(), "decided_at": date.today().isoformat()}
        if ns.revisit_when.strip():
            idea.decision["revisit_when"] = ns.revisit_when.strip()
        print(f"[ok] {idea.id} parked")
    write_session(root, session)
    return 0


HANDLERS_V2 = {
    "next-round": cmd_next_round,
    "frame": cmd_frame,
    "evidence": cmd_evidence,
    "add-evidence": cmd_add_evidence,
    "verify": cmd_verify,
    "park": cmd_park,
}

__all__ = ["HANDLERS_V2", "write_round_prompts", "sys"]
