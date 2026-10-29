#!/usr/bin/env python3
"""CLI for roadmap brainstorming: ``specy-road brainstorm``.

Two modes over one session file. ``start`` emits a divergent prompt and the
agent records what it generates with ``add-idea``; ``recommend`` emits the
convergent prompt; the PM triages with ``accept`` / ``reject`` / ``revise``;
``promote`` turns what survived into roadmap nodes.

Nothing here calls a model. The prompts are written for whichever agent is
already driving the IDE, which is the one with a web search tool. The PM GUI
runs the same prompt text against its own configured model.
"""

from __future__ import annotations

import argparse
import json
import sys

from specy_road.bundled_scripts.brainstorm_cli_args import build_parser
from specy_road.bundled_scripts.brainstorm_cli_v2 import (
    HANDLERS_V2,
    integration_branch_warning,
    next_step,
    stage,
    write_round_prompts,
)
from specy_road.bundled_scripts.brainstorm_close import close_session
from specy_road.bundled_scripts.brainstorm_fields import parse_origin, parse_overlap
from specy_road.bundled_scripts.brainstorm_prompt import (
    render_recommend_prompt,
    write_prompt,
)
from specy_road.bundled_scripts.brainstorm_promote import (
    execution_milestone_from_promote_sets,
    pending_ideas,
    promote_session,
    unverified_strong,
)
from specy_road.bundled_scripts.brainstorm_session import (
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
    write_session,
)
from specy_road.cli_entry import run_forwarded_cli
from specy_road.runtime_paths import resolve_repo_root


def _load(ns: argparse.Namespace) -> tuple:
    """Repo root plus the session named by ``--slug`` (or the only one open)."""
    root = resolve_repo_root(ns)
    slug = resolve_slug(root, getattr(ns, "slug", None))
    return root, read_session(root, slug)


def cmd_start(ns: argparse.Namespace) -> int:
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


def cmd_add_idea(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    idea = add_idea(
        session,
        title=ns.title,
        rationale=ns.rationale or "",
        kind=ns.kind,
        effort=ns.effort or "",
        evidence=list(ns.evidence or []),
        origin=parse_origin(ns.origin),
        hypothesis=ns.hypothesis or "",
        assumptions=list(ns.assumption or []),
    )
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
        "ideas": [i.to_dict() for i in session.ideas],
    }


def _print_rows(ideas: list, *, verdicts: bool) -> None:
    for i in ideas:
        rec = (i.recommendation or "-") if verdicts else ""
        mark = f" -> {i.promoted_node_key[:8]}" if i.promoted_node_key else ""
        src = f" [{len(i.sources)} src]" if i.sources else ""
        print(f"  {i.id:<5} {i.status:<9} {rec:<9} {i.kind:<11} {i.title}{src}{mark}")
        if verdicts and i.verdict_why:
            print(f"        why: {i.verdict_why}")
        if verdicts and i.critic:
            for role, text in i.critic.items():
                print(f"        {role}: {text}")


def cmd_list(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
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
    if not ideas:
        print("\n(no ideas match)")
    elif ns.by == "cluster":
        print("")
        clusters: dict[str, list] = {}
        for i in ideas:
            clusters.setdefault(i.cluster_id or "(unclustered)", []).append(i)
        for cid, members in sorted(clusters.items(), key=lambda kv: (kv[0] == "(unclustered)", kv[0])):
            print(f"{cid}  ({len(members)})")
            _print_rows(members, verdicts=ns.show_verdicts)
    else:
        print("")
        _print_rows(ideas, verdicts=ns.show_verdicts)
    print(next_step(session, stage(session)))
    return 0


def _triage(ns: argparse.Namespace, status: str) -> int:
    root, session = _load(ns)
    reason = (ns.reason or "").strip()
    if status == "rejected" and not reason:
        raise BrainstormError("reject needs --reason: the record of why is worth more than the reject")
    from datetime import date

    for ident in ns.idea_id:
        idea = set_status(session, ident, status)
        if reason:
            idea.decision = {"status": status, "reason": reason, "decided_at": date.today().isoformat()}
        elif idea.decision and idea.decision.get("status") != status:
            idea.decision = None   # an earlier reject/park reason does not describe this decision
        print(f"[ok] {idea.id} {status}")
    write_session(root, session)
    print(next_step(session, "triage"))
    return 0


def cmd_accept(ns: argparse.Namespace) -> int:
    return _triage(ns, "accepted")


def cmd_reject(ns: argparse.Namespace) -> int:
    return _triage(ns, "rejected")


def cmd_revise(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    idea = session.by_id(ns.idea_id)
    # A recommendation is the agent's advice; only a content edit is a revision,
    # so recording advice must not consume the PM's triage decision.
    content_changed = False
    for attr in ("title", "rationale", "kind", "effort"):
        value = getattr(ns, attr, None)
        if value is not None:
            setattr(idea, attr, value)
            content_changed = True
    if ns.recommendation is not None:
        idea.recommendation = ns.recommendation
    if ns.why is not None:
        idea.verdict_why = ns.why.strip()
    if ns.cluster is not None:
        idea.cluster_id = ns.cluster.strip() or None
    for item in ns.overlap or []:
        idea.overlap.append(parse_overlap(item))
    for item in ns.critic or []:
        role, _sep, text = item.partition(":")
        idea.critic = {**(idea.critic or {}), role.strip() or "critic": text.strip()}
    if content_changed and idea.status == "proposed":
        idea.status = "revised"
    write_session(root, session)
    print(f"[ok] {idea.id} {idea.status} (recommendation: {idea.recommendation or '-'})")
    print(next_step(session, stage(session)))
    return 0


def _check_converge(session: BrainstormSession) -> int:
    """Exit 1, listing each idea the converge pass left without a cluster or a recommendation."""
    missed = 0
    for i in session.ideas:
        gaps = [name for name, value in (("cluster", i.cluster_id), ("recommendation", i.recommendation))
                if not value]
        if gaps:
            missed += 1
            print(f"  {i.id:<5} no {' and no '.join(gaps)}  {i.title}")
    if missed:
        print(f"recommend --check: {missed} of {len(session.ideas)} idea(s) not converged; record each with "
              f"`specy-road brainstorm revise <IDEA_ID> --cluster CID --recommendation … --slug {session.slug}`")
        return 1
    print(f"recommend --check: all {len(session.ideas)} idea(s) have a cluster and a recommendation")
    print(next_step(session, "recommend"))
    return 0


def cmd_recommend(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    if ns.check:
        return _check_converge(session)
    session.mode = "roadmap"
    write_session(root, session)
    ppath = write_prompt(root, session, render_recommend_prompt(root, session), pass_name="recommend")
    print(f"prompt: {ppath.relative_to(root)} ({len(session.ideas)} ideas to assess)")
    print(next_step(session, "recommend"))
    return 0


def cmd_promote(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    if not pending_ideas(session):
        print(
            "nothing to promote — accept ideas first with: "
            f"specy-road brainstorm accept <IDEA_ID> --slug {session.slug}"
        )
        return 0
    for idea in unverified_strong(session):
        states = ", ".join(s["verification"] for s in idea.sources) or "no sources"
        fix = "verify" if idea.sources else f"evidence {idea.id}"
        print(f"warning: {idea.id} is recommended strong but no source is matched ({states}); "
              f"`specy-road brainstorm {fix} --slug {session.slug}`", file=sys.stderr)
    results = promote_session(
        root,
        session,
        under=ns.under,
        node_type=ns.type,
        execution_milestone=execution_milestone_from_promote_sets(getattr(ns, "set", None)),
        dry_run=ns.dry_run,
    )
    if not ns.dry_run:
        write_session(root, session)
    prefix = "would add" if ns.dry_run else "[ok] added"
    for r in results:
        parent = r.parent_id or "(root)"
        print(f"{prefix} {r.node_id} under {parent} — {r.title}  (from {r.idea_id})")
    if ns.dry_run:
        print("\nDry run — nothing written.")
        print(next_step(session, "dry-run"))
    else:
        print(f"\nPromoted {len(results)} idea(s).")
        print(next_step(session, "promote"))
    return 0


def cmd_sessions(ns: argparse.Namespace) -> int:
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
    print("next: `specy-road brainstorm list --slug SLUG` shows a session's ideas and its next step")
    return 1 if unreadable else 0


def cmd_close(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    slug = resolve_slug(root, ns.slug)
    for src, dst in close_session(root, slug):
        print(f"moved {src.relative_to(root).as_posix()} -> {dst.relative_to(root).as_posix()}")
    print(f"[ok] closed {slug}; it no longer counts as an open session")
    print("done: nothing follows for this session; `specy-road brainstorm start --topic '<question>'` opens another")
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
    "revise": cmd_revise,
    "recommend": cmd_recommend,
    "promote": cmd_promote,
    **HANDLERS_V2,
}.items()}


def main(argv: list[str] | None = None) -> None:
    run_forwarded_cli(lambda: build_parser(HANDLERS), "brainstorm", argv)


if __name__ == "__main__":
    main()
