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

from specy_road.bundled_scripts.brainstorm_cli_args import build_parser
from specy_road.bundled_scripts.brainstorm_prompt import (
    render_brainstorm_prompt,
    render_recommend_prompt,
    write_prompt,
)
from specy_road.bundled_scripts.brainstorm_promote import (
    pending_ideas,
    promote_session,
)
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    list_slugs,
    read_session,
    resolve_slug,
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
    spath = write_session(root, session)
    ppath = write_prompt(
        root, session, render_brainstorm_prompt(root, session, count=ns.count)
    )
    print(f"session: {spath.relative_to(root)} ({len(session.ideas)} ideas)")
    print(f"prompt:  {ppath.relative_to(root)}")
    print("\nHand the prompt to your agent, then triage with:")
    print(f"  specy-road brainstorm list --slug {slug}")
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
    )
    write_session(root, session)
    print(f"[ok] {idea.id} {idea.title}")
    return 0


def _idea_payload(session: BrainstormSession) -> dict:
    return {
        "slug": session.slug,
        "topic": session.topic,
        "under": session.under,
        "mode": session.mode,
        "ideas": [i.to_dict() for i in session.ideas],
    }


def cmd_list(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    ideas = session.ideas
    if ns.status:
        ideas = [i for i in ideas if i.status == ns.status]
    if ns.json:
        payload = _idea_payload(session)
        payload["ideas"] = [i.to_dict() for i in ideas]
        print(json.dumps(payload, indent=2))
        return 0
    anchor = session.under or "(roadmap root)"
    print(f"{session.slug} — {session.topic or '(no topic)'}")
    print(f"mode: {session.mode}   anchor: {anchor}   ideas: {len(session.ideas)}")
    if not ideas:
        print("\n(no ideas match)")
        return 0
    print("")
    for i in ideas:
        rec = i.recommendation or "-"
        mark = f" -> {i.promoted_node_key[:8]}" if i.promoted_node_key else ""
        print(f"  {i.id:<5} {i.status:<9} {rec:<9} {i.kind:<11} {i.title}{mark}")
    return 0


def _triage(ns: argparse.Namespace, status: str) -> int:
    root, session = _load(ns)
    for ident in ns.idea_id:
        idea = set_status(session, ident, status)
        print(f"[ok] {idea.id} {status}")
    write_session(root, session)
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
    if content_changed and idea.status == "proposed":
        idea.status = "revised"
    write_session(root, session)
    print(f"[ok] {idea.id} {idea.status} (recommendation: {idea.recommendation or '-'})")
    return 0


def cmd_recommend(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    session.mode = "roadmap"
    write_session(root, session)
    ppath = write_prompt(root, session, render_recommend_prompt(root, session))
    print(f"prompt: {ppath.relative_to(root)} ({len(session.ideas)} ideas to assess)")
    return 0


def cmd_promote(ns: argparse.Namespace) -> int:
    root, session = _load(ns)
    if not pending_ideas(session):
        print(
            "nothing to promote — accept ideas first with: "
            f"specy-road brainstorm accept <IDEA_ID> --slug {session.slug}"
        )
        return 0
    results = promote_session(
        root,
        session,
        under=ns.under,
        node_type=ns.type,
        dry_run=ns.dry_run,
    )
    if not ns.dry_run:
        write_session(root, session)
    prefix = "would add" if ns.dry_run else "[ok] added"
    for r in results:
        parent = r.parent_id or "(root)"
        print(f"{prefix} {r.node_id} under {parent} — {r.title}  (from {r.idea_id})")
    if ns.dry_run:
        print("\nDry run — nothing written. Re-run without --dry-run to apply.")
    else:
        print(f"\nPromoted {len(results)} idea(s). Refresh generated files:")
        print("  specy-road export && specy-road digest")
    return 0


def cmd_sessions(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    slugs = list_slugs(root)
    if not slugs:
        print("no brainstorm sessions in work/")
        return 0
    for slug in slugs:
        session = read_session(root, slug)
        print(f"  {slug:<24} {session.mode:<10} {len(session.ideas):>3} ideas")
    return 0


HANDLERS = {
    "start": cmd_start,
    "add-idea": cmd_add_idea,
    "list": cmd_list,
    "sessions": cmd_sessions,
    "accept": cmd_accept,
    "reject": cmd_reject,
    "revise": cmd_revise,
    "recommend": cmd_recommend,
    "promote": cmd_promote,
}


def main(argv: list[str] | None = None) -> None:
    run_forwarded_cli(lambda: build_parser(HANDLERS), "brainstorm", argv)


if __name__ == "__main__":
    main()
