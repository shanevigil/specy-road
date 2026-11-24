#!/usr/bin/env python3
"""CLI for roadmap brainstorming: ``specy-road brainstorm``.

Two modes over one session file. ``start`` emits a divergent prompt and the
agent records what it generates with ``add-idea``; ``recommend`` emits the
convergent prompt; the PM triages with ``accept`` / ``reject`` / ``revise``;
``promote`` turns what survived into roadmap nodes; ``close`` moves the
finished session out of the open set.

Nothing here calls a model. The prompts are written for whichever agent is
already driving the IDE, which is the one with a web search tool. The PM GUI
runs the same prompt text against its own configured model.

The handlers live here; the flags they read are built in ``brainstorm_cli_args``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

from specy_road.brainstorm_prompt import (
    render_brainstorm_prompt,
    render_evidence_prompt,
    render_recommend_prompt,
    render_shard_prompt,
    write_prompt,
)
from specy_road.brainstorm_promote import (
    decided_policies,
    pending_ideas,
    promote_session,
    unverified_strong,
)
from specy_road.brainstorm_session import (
    IDEA_STATUSES,
    PROMPT_SUFFIX,
    RECOMMENDATIONS,
    SESSION_PREFIX,
    BrainstormError,
    BrainstormSession,
    add_idea,
    list_slugs,
    read_session,
    resolve_slug,
    session_lock,
    session_path,
    set_status,
    slugify,
    validate_slug,
    work_dir,
    write_session,
)
from specy_road.bundled_scripts.brainstorm_cli_args import (
    bound_parser,
    evidence_record,
    execution_milestone_from_promote_sets,
    file_namespaces,
    frame_answers,
    quoted_sources,
)
from specy_road.bundled_scripts.brainstorm_fields import parse_origin, parse_overlap
from specy_road.bundled_scripts.brainstorm_promote_plan import below_recommendation
from specy_road.bundled_scripts.brainstorm_prompt_evidence import MAX_EVIDENCE_IDEAS, shortlist
from specy_road.bundled_scripts.brainstorm_verify import confirm, is_local, pending, verify_session
from specy_road.cli_entry import run_handler
from specy_road.clock import utc_now
from specy_road.git_subprocess import current_branch_name
from specy_road.git_workflow_config import resolve_integration_defaults
from specy_road.roadmap_load import load_roadmap
from specy_road.runtime_paths import resolve_repo_root

DEFAULT_COUNT = 20

CLOSED_DIRNAME = "brainstorm-closed"

#: The pass part of a prompt name ``prompt_path`` writes (``-r<N>``, ``-r1-s<K>``, ``-recommend``,
#: ``-evidence``, ``-authoring``), plus the bare and ``-s<K>`` names older versions wrote.
PROMPT_PASS_RE = r"(?:-r\d+(?:-s\d+)?|-recommend|-evidence|-authoring|-s\d+)?"


def _load(ns: argparse.Namespace) -> tuple:
    """Repo root plus the session named by ``--slug`` (or the only one open)."""
    root = resolve_repo_root(ns)
    slug = resolve_slug(root, getattr(ns, "slug", None))
    return root, read_session(root, slug)


def print_idea_summary(session: BrainstormSession) -> None:
    """Print the idea counts per status and per recommendation (``list --summary``)."""
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


def next_step(session: BrainstormSession, done: str) -> str:
    """The command that follows ``done``: round -> recommend -> evidence/verify -> triage
    -> promote."""
    cmd = f"specy-road brainstorm {{}} --slug {session.slug}".format
    if done == "round":
        follow = (f"`{cmd('next-round')}` (round {session.round + 1} of {session.rounds})"
                  if session.round < session.rounds else f"`{cmd('recommend')}`")
        return f"next: when the agent has recorded its ideas, {follow}"
    return "next: " + {
        "recommend": f"when the verdicts are recorded, `{cmd('evidence')}` for the shortlist, "
                     f"then `{cmd('verify')}`",
        "evidence": f"when the sources are recorded, `{cmd('verify')}`",
        "verify": (f"triage: `{cmd('list --by cluster')}`, "
                   "then accept / reject --reason / park --reason"),
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
    if any(i.status in ("accepted", "rejected", "parked", "decided") for i in session.ideas):
        return "triage"
    if any(i.sources for i in session.ideas):
        return "evidence" if pending(session.ideas) else "verify"
    return "recommend"


def write_round_prompts(root, session: BrainstormSession, *, count: int) -> list:
    """The round prompt, plus one shard prompt per panel worker in round 1."""
    text = render_brainstorm_prompt(root, session, count=count)
    paths = [write_prompt(root, session, text, pass_name=f"r{session.round}")]
    if session.panel and session.round <= 1:
        paths += _write_shard_prompts(root, session, count=count)
    return paths


def _write_shard_prompts(root, session: BrainstormSession, *, count: int) -> list:
    per = max(1, -(-count // session.panel))
    return [write_prompt(root, session,
                         render_shard_prompt(root, session, count=per, shard=k,
                                             total=session.panel),
                         pass_name=f"r{session.round}-s{k}") for k in range(1, session.panel + 1)]


def integration_branch_warning(root, slug: str) -> str | None:
    """A warning when ``start`` runs on the integration branch, where the tracked session
    would land."""
    base, _remote, _warnings = resolve_integration_defaults(
        root, explicit_base=None, explicit_remote=None)
    if current_branch_name(root) != base:
        return None
    return (f"warning: on the integration branch {base!r}; the session file is tracked, "
            f"so brainstorm "
            f"on a branch of its own: git checkout -b chore/brainstorm-{slug}")


def cmd_start(ns: argparse.Namespace) -> int:
    """``start``: open or reopen a session and write its round prompt (plus panel shards)."""
    root = resolve_repo_root(ns)
    topic = (ns.topic or "").strip()
    slug = (ns.slug or "").strip() or slugify(topic)
    if not slug:
        raise BrainstormError(
            "cannot derive a session name — pass --topic '<question>' or --slug SLUG"
        )
    warning = integration_branch_warning(root, slug)
    if warning:
        print(warning, file=sys.stderr)
    if session_path(root, slug).is_file():
        session = read_session(root, slug)
        if topic:
            session.topic = topic
        if ns.under is not None:
            session.under = ns.under or None
        session.mode = "brainstorm"
    else:
        session = BrainstormSession(
            slug=slug,
            topic=topic,
            under=(ns.under or None),
            mode="brainstorm",
        )
    if ns.profile:
        session.profile = ns.profile
    if ns.panel is not None:
        session.panel = max(0, ns.panel)
    if ns.rounds:
        session.rounds = max(1, ns.rounds)
    session.count = max(1, ns.count)
    spath = write_session(root, session)
    paths = write_round_prompts(root, session, count=ns.count)
    print(f"session: {spath.relative_to(root)} ({len(session.ideas)} ideas, "
          f"round {session.round} of {session.rounds}, profile {session.profile})")
    print(f"prompt:  {paths[0].relative_to(root)}")
    for extra in paths[1:]:
        print(f"shard:   {extra.relative_to(root)}")
    print("\nHand the prompt to your agent.")
    print(next_step(session, "round"))
    return 0


def cmd_next_round(ns: argparse.Namespace) -> int:
    """``next-round``: open the next diverge round and write its prompt against the pool."""
    root, session = _load(ns)
    if not session.ideas:
        raise BrainstormError(
            "no ideas yet — run the round-1 prompt first, or `brainstorm start` again")
    session.round += 1
    session.mode = "brainstorm"
    write_session(root, session)
    count = ns.count or DEFAULT_COUNT
    ppath = write_round_prompts(root, session, count=count)[0]
    print(f"round {session.round} of {session.rounds}: {ppath.relative_to(root)} "
          f"({len(session.ideas)} ideas in the pool)")
    if session.round > session.rounds:
        print(f"note: past the {session.rounds} round(s) planned at `start --rounds`; "
              f"converge is usually next",
              file=sys.stderr)
    print(next_step(session, "round"))
    return 0


def _set_answer(session: BrainstormSession, key: str, text: str, now: str) -> None:
    """Record one frame answer; a different answer it replaces goes to ``frame_history``."""
    old = session.frame.get(key)
    if old is not None and old != text:
        session.frame_history.append({"key": key, "answer": old, "replaced_at": now})
    session.frame[key] = text


def cmd_frame(ns: argparse.Namespace) -> int:
    """``frame``: record frame answers, the allocation grid and the frame's state."""
    root, session = _load(ns)
    answers = frame_answers(ns)
    if ns.amend is not None and ns.amend.strip() not in session.frame:
        raise BrainstormError(f"--amend {ns.amend.strip()!r}: the frame has no such answer to "
                              f"amend; "
                              f"record it with --answer {ns.amend.strip()}=TEXT")
    now = utc_now().isoformat(timespec="milliseconds")
    for key, text in answers:
        _set_answer(session, key, text, now)
    if ns.allocation is not None:
        session.allocation = ns.allocation.strip()
    if ns.provisional or ns.confirm:
        if not session.frame:
            raise BrainstormError("no frame recorded yet — record it with --answer KEY=TEXT first")
        session.frame_state = "provisional" if ns.provisional else "confirmed"
    write_session(root, session)
    print(f"[ok] frame: {len(session.frame)} answer(s)"
          + (", allocation recorded" if session.allocation else "")
          + (f", {session.frame_state}" if session.frame_state else "")
          + (f", {ns.amend.strip()} amended "
             "(previous answer kept in frame_history)" if ns.amend else ""))
    if session.panel and session.round <= 1:
        # Shards are written at `start`, before any frame exists; rewrite them so they carry it.
        for path in _write_shard_prompts(root, session, count=session.count or DEFAULT_COUNT):
            print(f"shard:   {path.relative_to(root)} (rewritten)")
    print(next_step(session, stage(session)))
    return 0


def idea_fields(ns: argparse.Namespace) -> dict:
    """``add_idea`` keyword arguments from an ``add-idea`` namespace
    (a flag line or a file record)."""
    return dict(title=ns.title or "", rationale=ns.rationale or "", kind=ns.kind or "feature",
                effort=ns.effort or "",
                evidence=list(ns.evidence or []), origin=parse_origin(ns.origin),
                hypothesis=ns.hypothesis or "",
                assumptions=list(ns.assumption or []),
                raised_in="converge" if ns.from_gap else None,
                sources=quoted_sources(ns))


def _refuse_flags_with_file(ns: argparse.Namespace, positional: str | None, *flags: str) -> None:
    given = [f"--{f.replace('_', '-')}" for f in flags if getattr(ns, f) not in (None, False, [])]
    if positional is not None or given:
        raise BrainstormError(f"--from-file takes every value from the file; "
                              f"drop {', '.join(given) or positional}")


def cmd_add_ideas_from_file(ns: argparse.Namespace) -> int:
    """``add-idea --from-file``: record every idea in the file in one write, or none."""
    _refuse_flags_with_file(ns, None, "title", "rationale", "kind", "effort", "evidence", "quote",
                            "origin",
                            "hypothesis", "assumption", "from_gap")
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


def cmd_add_idea(ns: argparse.Namespace) -> int:
    """``add-idea``: record one idea from its flags, or a file of them."""
    if ns.from_file is not None:
        return cmd_add_ideas_from_file(ns)
    if not (ns.title or "").strip():
        raise BrainstormError("add-idea needs --title, or --from-file PATH")
    root, session = _load(ns)
    idea = add_idea(session, **idea_fields(ns))
    write_session(root, session)
    print(f"[ok] {idea.id} {idea.title}")
    print(next_step(session, stage(session)))
    return 0


def _idea_payload(session: BrainstormSession) -> dict:
    return {
        "slug": session.slug,
        "topic": session.topic,
        "under": session.under,
        "mode": session.mode,
        "round": session.round,
        "profile": session.profile,
        "frame": dict(session.frame),
        "frame_state": session.frame_state,
        "frame_history": [dict(h) for h in session.frame_history],
        "clusters": session.clusters,
        "ideas": [i.to_dict() for i in session.ideas],
    }


def _print_rows(ideas: list, *, verdicts: bool) -> None:
    for i in ideas:
        rec = (i.recommendation or "-") if verdicts else ""
        mark = f" -> {i.promoted_node_key[:8]}" if i.promoted_node_key else ""
        mark += f" => {', '.join(i.merged_into)}" if i.merged_into else ""
        mark += " [gap]" if i.raised_in else ""
        src = f" [{len(i.sources)} src]" if i.sources else ""
        print(f"  {i.id:<5} {i.status:<9} {rec:<9} {i.kind:<11} {i.title}{src}{mark}")
        if i.status == "decided" and (i.decision or {}).get("decision"):
            print(f"        decision: {i.decision['decision']}")
        if verdicts and i.verdict_why:
            print(f"        why: {i.verdict_why}")
        if verdicts and i.critic:
            for role, text in i.critic.items():
                print(f"        {role}: {text}")


def _print_cluster(cid: str, members: list, obj: dict, *, verdicts: bool) -> None:
    """A cluster header (the `brainstorm cluster` object's name and best, when recorded),
    then its rows."""
    best = f"best: {obj['best']}" if obj.get("best") else ""
    print("  ".join(filter(None, (cid, obj.get("name", ""), f"({len(members)})", best))))
    for role, text in (obj.get("critic") or {}).items() if verdicts else ():
        print(f"    {role}: {text}")
    _print_rows(members, verdicts=verdicts)


def cmd_list(ns: argparse.Namespace) -> int:
    """``list``: the session's ideas as rows, by cluster, as counts or as JSON."""
    root, session = _load(ns)
    if ns.summary:
        print_idea_summary(session)
        print(next_step(session, stage(session)))
        return 0
    ideas = session.ideas
    if ns.status:
        ideas = [i for i in ideas if i.status == ns.status]
    if ns.json:
        payload = _idea_payload(session)
        payload["ideas"] = [i.to_dict() for i in ideas]
        print(json.dumps(payload, indent=2))
        print(next_step(session, stage(session)), file=sys.stderr)   # stdout stays JSON
        return 0
    anchor = session.under or "(roadmap root)"
    print(f"{session.slug} — {session.topic or '(no topic)'}")
    print(f"mode: {session.mode}   anchor: {anchor}   ideas: {len(session.ideas)}")
    if not ideas and not (ns.by == "cluster" and session.clusters and not ns.status):
        print("\n(no ideas match)")
    elif ns.by == "cluster":   # recorded cluster objects show even before any idea joins them
        print("")
        clusters: dict[str, list] = {} if ns.status else {cid: [] for cid in session.clusters}
        for i in ideas:
            clusters.setdefault(i.cluster_id or "(unclustered)", []).append(i)
        for cid, members in sorted(clusters.items(),
                                   key=lambda kv: (kv[0] == "(unclustered)", kv[0])):
            _print_cluster(cid, members, session.clusters.get(cid, {}), verdicts=ns.show_verdicts)
    else:
        print("")
        _print_rows(ideas, verdicts=ns.show_verdicts)
    print(next_step(session, stage(session)))
    return 0


def _next_decision_seq(session: BrainstormSession) -> int:
    seqs: list[int] = []
    for idea in session.ideas:
        raw = (idea.decision or {}).get("seq")
        try:
            seqs.append(int(str(raw)))
        except (TypeError, ValueError):
            continue
    return (max(seqs) + 1) if seqs else 1


def _triage(ns: argparse.Namespace, status: str) -> int:
    root, session = _load(ns)
    reason = (ns.reason or "").strip()
    if status == "rejected" and not reason:
        raise BrainstormError(
            "reject needs --reason: the record of why is worth more than the reject")
    ideas = [set_status(session, ident, status) for ident in ns.idea_id]
    seq = _next_decision_seq(session)
    now = utc_now().isoformat(timespec="milliseconds")
    for idea in ideas:
        dec = {"status": status, "decided_at": now, "seq": str(seq)}
        if reason:
            dec["reason"] = reason
        idea.decision = dec
        seq += 1
        print(f"[ok] {idea.id} {status}")
    write_session(root, session)
    print(next_step(session, "triage"))
    return 0


def cmd_accept(ns: argparse.Namespace) -> int:
    """``accept``: keep one or more ideas."""
    return _triage(ns, "accepted")


def cmd_reject(ns: argparse.Namespace) -> int:
    """``reject``: discard one or more ideas, with the required reason."""
    return _triage(ns, "rejected")


def cmd_park(ns: argparse.Namespace) -> int:
    """``park``: set ideas aside with a reason and an optional revisit condition."""
    root, session = _load(ns)
    ideas = [set_status(session, ident, "parked") for ident in ns.idea_id]
    for idea in ideas:
        idea.decision = {"status": "parked", "reason": ns.reason.strip(),
                         "decided_at": date.today().isoformat()}
        if ns.revisit_when.strip():
            idea.decision["revisit_when"] = ns.revisit_when.strip()
        print(f"[ok] {idea.id} parked")
    write_session(root, session)
    print(next_step(session, "triage"))
    return 0


def cmd_decide(ns: argparse.Namespace) -> int:
    """``decide``: record the decision an idea settled, for the anchor's sheet."""
    root, session = _load(ns)
    text = (ns.decision or "").strip()
    if not text:
        raise BrainstormError("decide needs --decision TEXT: "
                              "the decision is what promote writes into the sheet")
    idea = set_status(session, ns.idea_id, "decided")   # refuses a promoted or merged idea
    now = utc_now().isoformat(timespec="milliseconds")
    idea.decision = {"status": "decided", "decision": text, "decided_at": now}
    write_session(root, session)
    print(f"[ok] {idea.id} decided: {text}")
    print(next_step(session, stage(session)))
    return 0


def cmd_realize(ns: argparse.Namespace) -> int:
    """``realize``: link an idea to a roadmap node created outside promote."""
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


def cmd_merge(ns: argparse.Namespace) -> int:
    """``merge``: fold a duplicate idea into others, linked both ways."""
    root, session = _load(ns)
    idea = session.by_id(ns.idea_id)
    ids = [part.strip() for item in ns.into for part in item.split(",") if part.strip()]
    targets = list({t.id: t for t in (session.by_id(i) for i in ids)}.values())
    if not targets or idea in targets:
        raise BrainstormError(f"--into must name ideas other than {idea.id}")
    for t in targets:
        if t.status == "merged":
            raise BrainstormError(f"idea {t.id} is itself merged into "
                                  f"{', '.join(t.merged_into)}; merge into that")
    set_status(session, idea.id, "merged")   # refuses a promoted or already merged idea
    idea.merged_into = [t.id for t in targets]
    for t in targets:
        t.merged_from = [*t.merged_from, idea.id] if idea.id not in t.merged_from else t.merged_from
    now = utc_now().isoformat(timespec="milliseconds")
    idea.decision = {"status": "merged", "decided_at": now, "into": ", ".join(idea.merged_into)}
    write_session(root, session)
    print(f"[ok] {idea.id} merged into {', '.join(idea.merged_into)}; promote skips it")
    print(next_step(session, stage(session)))
    return 0


def cmd_cluster(ns: argparse.Namespace) -> int:
    """``cluster``: record a converge cluster's name, best member and critics."""
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
            raise BrainstormError(f"idea {best.id} is in cluster "
                                  f"{best.cluster_id or '(none)'}, not {cid}; "
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
    print(f"[ok] cluster {cid}: {entry.get('name') or '(no name)'}, "
          f"best {entry.get('best') or '-'}, "
          f"{len(members)} member(s)")
    print(next_step(session, stage(session)))
    return 0


def _revise_content(idea, ns: argparse.Namespace) -> bool:
    # A recommendation is the agent's advice; only a content edit is a revision,
    # so recording advice must not consume the PM's triage decision.
    content_changed = False
    for attr in ("title", "rationale", "kind", "effort", "codename"):
        value = getattr(ns, attr, None)
        if value is not None:
            setattr(idea, attr, value.strip() if attr == "codename" else value)
            content_changed = True
    return content_changed


def _revise_why(idea, ns: argparse.Namespace) -> None:
    if ns.append_why is not None:
        addition = ns.append_why.strip()
        if addition:
            idea.verdict_why = (f"{idea.verdict_why}\n{addition}".strip()
                                if idea.verdict_why else addition)
    elif ns.why is not None:
        idea.verdict_why = ns.why.strip()


def _revise_links(idea, ns: argparse.Namespace) -> None:
    if ns.cluster is not None:
        idea.cluster_id = ns.cluster.strip() or None
    if ns.target_parent is not None:
        idea.target_parent = ns.target_parent.strip() or None
    for item in ns.overlap or []:
        idea.overlap.append(parse_overlap(item))
    for item in ns.critic or []:
        role, _sep, text = item.partition(":")
        idea.critic = {**(idea.critic or {}), role.strip() or "critic": text.strip()}


def _apply_revise(idea, ns: argparse.Namespace) -> None:
    content_changed = _revise_content(idea, ns)
    if ns.recommendation is not None:
        idea.recommendation = ns.recommendation
    _revise_why(idea, ns)
    _revise_links(idea, ns)
    if content_changed and idea.status == "proposed":
        idea.status = "revised"


def _revise_one(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    idea = session.by_id(ns.idea_id)
    _apply_revise(idea, ns)
    write_session(root, session)
    print(f"[ok] {idea.id} {idea.status} (recommendation: {idea.recommendation or '-'})")
    print(next_step(session, stage(session)))
    return 0


def cmd_revise(ns: argparse.Namespace) -> int:
    """``revise IDEA_ID …`` for one idea, or ``revise --from-file`` with every verdict
    in one write."""
    if ns.from_file is None:
        if not ns.idea_id:
            raise BrainstormError("revise needs IDEA_ID, or --from-file PATH")
        return _revise_one(ns)
    _refuse_flags_with_file(ns, ns.idea_id, "title", "rationale", "kind", "effort", "codename",
                            "recommendation",
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


def _check_converge(session: BrainstormSession) -> int:
    """Exit 1, listing each idea the converge pass left without a cluster or a recommendation."""
    missed = 0
    # a merged idea's verdict is its target's
    for i in (i for i in session.ideas if i.status != "merged"):
        gaps = [name for name, value in (("cluster", i.cluster_id),
                                         ("recommendation", i.recommendation))
                if not value]
        if gaps:
            missed += 1
            print(f"  {i.id:<5} no {' and no '.join(gaps)}  {i.title}"
                  f"{' [gap]' if i.raised_in else ''}")
    if missed:
        print(f"recommend --check: {missed} of {len(session.ideas)} idea(s) not converged; "
              f"record each with "
              f"`specy-road brainstorm revise <IDEA_ID> --cluster CID --recommendation … "
              f"--slug {session.slug}`")
        return 1
    print(f"recommend --check: all {len(session.ideas)} idea(s) have a cluster "
          f"and a recommendation")
    print(next_step(session, "recommend"))
    return 0


def cmd_recommend(ns: argparse.Namespace) -> int:
    """``recommend``: switch to roadmap mode and write the convergent prompt."""
    root, session = _load(ns)
    if ns.check:
        return _check_converge(session)
    session.mode = "roadmap"
    write_session(root, session)
    ppath = write_prompt(root, session, render_recommend_prompt(root, session),
                         pass_name="recommend")
    print(f"prompt: {ppath.relative_to(root)} ({len(session.ideas)} ideas to assess)")
    for i in (i for i in session.ideas if i.raised_in and not i.recommendation):
        print(f"gap idea {i.id} (raised in the converge pass) needs a verdict: {i.title}")
    print(next_step(session, "recommend"))
    return 0


def cmd_evidence(ns: argparse.Namespace) -> int:
    """``evidence``: write the evidence prompt for the shortlisted ideas."""
    root, session = _load(ns)
    ideas = shortlist(session, list(ns.idea_id))
    if not ideas:
        raise BrainstormError(
            "nothing to source — name idea ids, or run `recommend` so some are strong")
    if len(ideas) > MAX_EVIDENCE_IDEAS:
        print(f"warning: {len(ideas)} ideas selected; an evidence pass over more than "
              f"{MAX_EVIDENCE_IDEAS} "
              "gets shallow — name the ids to source and run `evidence` in batches",
              file=sys.stderr)
    ppath = write_prompt(root, session, render_evidence_prompt(session, ideas),
                         pass_name="evidence")
    print(f"prompt: {ppath.relative_to(root)} ({len(ideas)} idea(s) to source)")
    print(next_step(session, "evidence"))
    return 0


def cmd_add_evidence(ns: argparse.Namespace) -> int:
    """``add-evidence``: record one source on an idea."""
    root, session = _load(ns)
    idea = session.by_id(ns.idea_id)
    rec = evidence_record(ns, root)
    idea.sources.append(rec)
    if ns.url is not None and rec["url"] not in idea.evidence:   # evidence lists pages only
        idea.evidence.append(rec["url"])
    write_session(root, session)
    print(f"[ok] {idea.id} source {len(idea.sources)}: {rec['url']} ({rec['stance']})")
    print(next_step(session, stage(session)))
    return 0


def cmd_verify(ns: argparse.Namespace) -> int:
    """Ask and fetch without the brainstorm lock; take it only to merge the results
    into a fresh read."""
    root, session = _load(ns)
    ideas = [session.by_id(i) for i in ns.idea_id] if ns.idea_id else session.ideas
    todo = pending(ideas)
    if not todo:
        print("verify: nothing unverified")
        print(next_step(session, "verify"))
        return 0
    # repo sources are read, not fetched
    urls = sorted({str(s.get("url")) for _i, s in todo if not is_local(s)})
    fetched = not urls or confirm(urls, yes=ns.yes)
    if not fetched and len(urls) == len(todo):
        return 1
    for line in verify_session(session, ideas, root=root, web=fetched):
        print(line)
    results = {(i.id, s.get("url"), s.get("quote")): s["verification"] for i, s in todo}
    with session_lock(root):   # ideas and sources added meanwhile are kept
        fresh = read_session(root, session.slug)
        for idea, src in pending(fresh.ideas):
            src["verification"] = results.get((idea.id, src.get("url"), src.get("quote")),
                                              "unverified")
        write_session(root, fresh)
    print(next_step(fresh, "verify"))
    return 0 if fetched else 1


def _promote_warnings(session: BrainstormSession, ns: argparse.Namespace) -> None:
    for idea in below_recommendation(pending_ideas(session), ns.min_recommendation):
        print(f"skipped {idea.id} ({idea.recommendation or 'no verdict'}): "
              f"below --min-recommendation "
              f"{ns.min_recommendation}; it stays accepted", file=sys.stderr)
    for idea in unverified_strong(session):
        states = ", ".join(s["verification"] for s in idea.sources) or "no sources"
        fix = "verify" if idea.sources else f"evidence {idea.id}"
        print(f"warning: {idea.id} is recommended strong but no source is matched ({states}); "
              f"`specy-road brainstorm {fix} --slug {session.slug}`", file=sys.stderr)


def cmd_promote(ns: argparse.Namespace) -> int:
    """``promote``: turn accepted ideas (or a plan file) into roadmap nodes."""
    root, session = _load(ns)
    anchor = ns.under if ns.under is not None else session.under
    # Short-circuit: the policy check (which may warn) runs only when no accepted idea is pending.
    if not ns.plan and not pending_ideas(session) and decided_policies(
            root, load_roadmap(root)["nodes"], anchor, session) is None:
        print(
            "nothing to promote — no accepted idea is pending and the anchor's decided "
            "policies are current; "
            f"accept ideas with `specy-road brainstorm accept <IDEA_ID> --slug {session.slug}` "
            "or record a decision with `specy-road brainstorm decide <IDEA_ID> --decision TEXT`"
        )
        return 0
    if not ns.plan:
        _promote_warnings(session, ns)
    results = promote_session(
        root,
        session,
        under=ns.under,
        node_type=ns.type,
        execution_milestone=execution_milestone_from_promote_sets(getattr(ns, "set", None)),
        dry_run=ns.dry_run,
        by_cluster=ns.by_cluster,
        min_recommendation=ns.min_recommendation,
        plan=Path(ns.plan) if ns.plan else None,
    )
    if not ns.dry_run:
        write_session(root, session)
    prefix = "would add" if ns.dry_run else "[ok] added"
    for r in results:
        parent = r.parent_id or "(root)"
        source = f"from {', '.join(filter(None, (r.idea_id, *r.linked)))}" if r.idea_id else "plan"
        print(f"{prefix} {r.node_id} under {parent} — {r.title}  ({source})")
    if ns.dry_run:
        print("\nDry run — nothing written.")
        print(next_step(session, "dry-run"))
    else:
        print(f"\nPromoted {len(results)} node(s).")
        print(next_step(session, "promote"))
    return 0


def cmd_sessions(ns: argparse.Namespace) -> int:
    """``sessions``: list every open session; exit 1 when one is unreadable."""
    root = resolve_repo_root(ns)
    slugs = list_slugs(root)
    if not slugs:
        print("no brainstorm sessions in work/")
        print("next: `specy-road brainstorm start --topic '<question>'`")
        return 0
    unreadable = 0
    for slug in slugs:
        # One bad file must not hide the sessions after it; it is reported, not repaired.
        try:
            session = read_session(root, slug)
        except BrainstormError as e:
            unreadable += 1
            print(f"{slug}: unreadable — {e}", file=sys.stderr)
            continue
        print(f"  {slug:<24} {session.mode:<10} {len(session.ideas):>3} ideas")
    print("next: `specy-road brainstorm list --slug SLUG` shows a session's ideas "
          "and its next step")
    return 1 if unreadable else 0


# A session has no closed state inside the file; ``list_slugs`` simply globs
# ``work/brainstorm-*.yaml``, so a finished session kept counting as open and
# forced ``--slug`` on every later command. ``close`` moves it one directory down,
# out of that glob, while keeping the tracked record of what was considered.


def closed_dir(root: Path) -> Path:
    """Where ``close`` moves a finished session's files: ``work/brainstorm-closed/``."""
    return work_dir(root) / CLOSED_DIRNAME


def _prompt_names(slug: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(SESSION_PREFIX + slug)}{PROMPT_PASS_RE}"
                      rf"{re.escape(PROMPT_SUFFIX)}$")


def session_files(root: Path, slug: str) -> list[Path]:
    """The session file plus the prompts written beside it.

    Those are exactly what ``write_prompt`` emits for a slug: one per pass
    (``-r<N>``, ``-r1-s<K>``, ``-recommend``, ``-evidence``, ``-authoring``), plus the bare and
    ``-s<K>`` names older versions wrote. The pattern is anchored on the whole
    slug, so closing ``a`` never touches ``ab``'s files.
    """
    safe = validate_slug(slug)
    own = _prompt_names(safe)
    others = [_prompt_names(s) for s in list_slugs(root) if s != safe]
    out = [session_path(root, safe)]
    for p in sorted(work_dir(root).iterdir()):
        # `a-s1` and `a-r1` are valid slugs too: a name another open session could own is
        # not `a`'s to move.
        if p.is_file() and own.match(p.name) and not any(o.match(p.name) for o in others):
            out.append(p)
    return out


def close_session(root: Path, slug: str) -> list[tuple[Path, Path]]:
    """Move the session's files into ``work/brainstorm-closed/``; ``(src, dst)`` pairs.

    Checks every destination before moving anything, so a refusal leaves the
    session exactly as it was.
    """
    safe = validate_slug(slug)
    if not session_path(root, safe).is_file():
        raise BrainstormError(f"no open brainstorm session {safe!r} "
                              f"(looked for {SESSION_PREFIX}{safe}.yaml in work/)")
    dest = closed_dir(root)
    moves = [(p, dest / p.name) for p in session_files(root, safe)]
    for _src, dst in moves:
        if dst.exists():
            raise BrainstormError(
                f"{dst.relative_to(root).as_posix()} already exists — a session named {safe!r} was "
                "closed before; rename or remove that file, then close again"
            )
    dest.mkdir(parents=True, exist_ok=True)
    for src, dst in moves:
        src.rename(dst)
    return moves


def cmd_close(ns: argparse.Namespace) -> int:
    """``close``: move a finished session to ``work/brainstorm-closed/``."""
    root = resolve_repo_root(ns)
    slug = resolve_slug(root, ns.slug)
    for src, dst in close_session(root, slug):
        print(f"moved {src.relative_to(root).as_posix()} -> {dst.relative_to(root).as_posix()}")
    print(f"[ok] closed {slug}; it no longer counts as an open session")
    print("done: nothing follows for this session; "
          "`specy-road brainstorm start --topic '<question>'` opens another")
    return 0


def _serialised(handler):
    """Run ``handler`` under the repo's brainstorm lock (``session_lock``)."""
    def run(ns: argparse.Namespace) -> int:
        with session_lock(resolve_repo_root(ns)):
            return handler(ns)
    return run


#: ``verify`` takes the lock itself, only to write: never across its y/n prompt and page fetches.
HANDLERS = {name: fn if name == "verify" else _serialised(fn) for name, fn in {
    "start": cmd_start,
    "add-idea": cmd_add_idea,
    "list": cmd_list,
    "sessions": cmd_sessions,
    "close": cmd_close,
    "accept": cmd_accept,
    "reject": cmd_reject,
    "recommend": cmd_recommend,
    "promote": cmd_promote,
    "next-round": cmd_next_round,
    "frame": cmd_frame,
    "evidence": cmd_evidence,
    "add-evidence": cmd_add_evidence,
    "verify": cmd_verify,
    "park": cmd_park,
    "decide": cmd_decide,
    "realize": cmd_realize,
    "revise": cmd_revise,
    "merge": cmd_merge,
    "cluster": cmd_cluster,
}.items()}


def build_parser() -> argparse.ArgumentParser:
    """The ``specy-road brainstorm`` parser, each subcommand bound to its handler."""
    return bound_parser(HANDLERS)


def main(argv: list[str] | None = None) -> None:
    """Parse ``argv`` and run the chosen subcommand's handler."""
    run_handler(build_parser().parse_args(argv))


if __name__ == "__main__":
    main()
