"""Handlers for the brainstorm v2 subcommands (rounds, frame, evidence, verify, park, merge, cluster)
and for ``add-idea`` / ``revise --from-file``."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timezone

from specy_road.bundled_scripts.brainstorm_cli_args import file_namespaces
from specy_road.bundled_scripts.brainstorm_fields import parse_origin, source_record
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
    add_idea,
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


def idea_fields(ns: argparse.Namespace) -> dict:
    """``add_idea`` keyword arguments from an ``add-idea`` namespace (a flag line or a file record)."""
    return dict(title=ns.title or "", rationale=ns.rationale or "", kind=ns.kind or "feature", effort=ns.effort or "",
                evidence=list(ns.evidence or []), origin=parse_origin(ns.origin), hypothesis=ns.hypothesis or "",
                assumptions=list(ns.assumption or []), raised_in="converge" if ns.from_gap else None)


def _refuse_flags_with_file(ns: argparse.Namespace, positional: str | None, *flags: str) -> None:
    given = [f"--{f.replace('_', '-')}" for f in flags if getattr(ns, f) not in (None, False, [])]
    if positional is not None or given:
        raise BrainstormError(f"--from-file takes every value from the file; drop {', '.join(given) or positional}")


def cmd_add_ideas_from_file(ns: argparse.Namespace) -> int:
    _refuse_flags_with_file(ns, None, "title", "rationale", "kind", "effort", "evidence", "origin", "hypothesis",
                            "assumption", "from_gap")
    root, session = _load(ns)
    ideas = []
    for n, rec in enumerate(file_namespaces(ns, "add-idea"), 1):
        try:
            ideas.append(add_idea(session, **idea_fields(rec)))
        except BrainstormError as e:
            raise BrainstormError(f"{ns.from_file} record {n}: {e} — nothing was written") from e
    write_session(root, session)   # once, after every record validated: all or none
    for idea in ideas:
        print(f"[ok] {idea.id} {idea.title}")
    print(f"recorded {len(ideas)} idea(s)")
    print(next_step(session, stage(session)))
    return 0


def cmd_revise_any(ns: argparse.Namespace) -> int:
    """``revise IDEA_ID …`` as before, or ``revise --from-file`` with every verdict in one write."""
    from specy_road.bundled_scripts.brainstorm_cli_revise import _apply_revise, cmd_revise  # imports this module

    if ns.from_file is None:
        if not ns.idea_id:
            raise BrainstormError("revise needs IDEA_ID, or --from-file PATH")
        return cmd_revise(ns)
    _refuse_flags_with_file(ns, ns.idea_id, "title", "rationale", "kind", "effort", "codename", "recommendation",
                            "why", "append_why", "cluster", "target_parent", "overlap", "critic")
    root, session = _load(ns)
    records = file_namespaces(ns, "revise")
    ideas = [session.by_id(rec.idea_id) for rec in records]   # every id resolves before any change
    for idea, rec in zip(ideas, records):
        _apply_revise(idea, rec)
    write_session(root, session)
    for idea in {i.id: i for i in ideas}.values():
        print(f"[ok] {idea.id} {idea.status} (recommendation: {idea.recommendation or '-'})")
    print(f"applied {len(records)} verdict record(s)")
    print(next_step(session, stage(session)))
    return 0


def cmd_merge(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    idea = session.by_id(ns.idea_id)
    ids = [part.strip() for item in ns.into for part in item.split(",") if part.strip()]
    targets = list({t.id: t for t in (session.by_id(i) for i in ids)}.values())
    if not targets or idea in targets:
        raise BrainstormError(f"--into must name ideas other than {idea.id}")
    for t in targets:
        if t.status == "merged":
            raise BrainstormError(f"idea {t.id} is itself merged into {', '.join(t.merged_into)}; merge into that")
    set_status(session, idea.id, "merged")   # refuses a promoted or already merged idea
    idea.merged_into = [t.id for t in targets]
    for t in targets:
        t.merged_from = [*t.merged_from, idea.id] if idea.id not in t.merged_from else t.merged_from
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    idea.decision = {"status": "merged", "decided_at": now, "into": ", ".join(idea.merged_into)}
    write_session(root, session)
    print(f"[ok] {idea.id} merged into {', '.join(idea.merged_into)}; promote skips it")
    print(next_step(session, stage(session)))
    return 0


def cmd_cluster(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    cid = ns.cluster_id.strip()
    if not cid:
        raise BrainstormError("cluster id is empty")
    entry = dict(session.clusters.get(cid, {}))
    if ns.name is not None:
        entry["name"] = ns.name.strip()
    if (ns.best or "").strip():
        best = session.by_id(ns.best)
        if best.cluster_id != cid:
            raise BrainstormError(f"idea {best.id} is in cluster {best.cluster_id or '(none)'}, not {cid}; "
                                  f"`specy-road brainstorm revise {best.id} --cluster {cid}` first")
        entry["best"] = best.id
    elif ns.best is not None:
        entry["best"] = ""
    for item in ns.critic or []:
        role, _sep, text = item.partition(":")
        entry["critic"] = {**entry.get("critic", {}), role.strip() or "critic": text.strip()}
    session.clusters[cid] = {k: v for k, v in entry.items() if v}   # '' clears name or best
    write_session(root, session)
    members = [i.id for i in session.ideas if i.cluster_id == cid]
    print(f"[ok] cluster {cid}: {entry.get('name') or '(no name)'}, best {entry.get('best') or '-'}, "
          f"{len(members)} member(s)")
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
    "revise": cmd_revise_any,
    "merge": cmd_merge,
    "cluster": cmd_cluster,
}

__all__ = ["HANDLERS_V2", "cmd_add_ideas_from_file", "idea_fields", "integration_branch_warning", "next_step",
           "stage", "write_round_prompts", "sys"]
