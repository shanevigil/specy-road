"""``specy-road brainstorm revise`` — extracted so ``cmd_revise`` stays under C901."""

from __future__ import annotations

import argparse

from specy_road.bundled_scripts.brainstorm_cli_v2 import next_step, stage
from specy_road.bundled_scripts.brainstorm_fields import parse_overlap
from specy_road.bundled_scripts.brainstorm_session import read_session, resolve_slug, write_session
from specy_road.runtime_paths import resolve_repo_root


def _revise_content(idea, ns: argparse.Namespace) -> bool:
    # A recommendation is the agent's advice; only a content edit is a revision,
    # so recording advice must not consume the PM's triage decision.
    content_changed = False
    for attr in ("title", "rationale", "kind", "effort"):
        value = getattr(ns, attr, None)
        if value is not None:
            setattr(idea, attr, value)
            content_changed = True
    return content_changed


def _revise_why(idea, ns: argparse.Namespace) -> None:
    if ns.append_why is not None:
        addition = ns.append_why.strip()
        if addition:
            idea.verdict_why = f"{idea.verdict_why}\n{addition}".strip() if idea.verdict_why else addition
    elif ns.why is not None:
        idea.verdict_why = ns.why.strip()


def _revise_links(idea, ns: argparse.Namespace) -> None:
    if ns.cluster is not None:
        idea.cluster_id = ns.cluster.strip() or None
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


def cmd_revise(ns: argparse.Namespace) -> int:
    root = resolve_repo_root(ns)
    session = read_session(root, resolve_slug(root, getattr(ns, "slug", None)))
    idea = session.by_id(ns.idea_id)
    _apply_revise(idea, ns)
    write_session(root, session)
    print(f"[ok] {idea.id} {idea.status} (recommendation: {idea.recommendation or '-'})")
    print(next_step(session, stage(session)))
    return 0
