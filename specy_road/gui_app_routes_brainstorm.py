"""Brainstorm panel API: chat, session triage, and promotion.

Handlers are module-level and registered at the bottom, the same shape as
``gui_app_routes_workspace``; nesting nine of them inside one register function
put it past the per-function line cap.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from specy_road.bundled_scripts.brainstorm_chat import chat_turn
from specy_road.bundled_scripts.brainstorm_prompt import (
    render_brainstorm_prompt,
    render_recommend_prompt,
)
from specy_road.bundled_scripts.brainstorm_promote import (
    pending_ideas,
    promote_session,
)
from specy_road.bundled_scripts.brainstorm_research import test_connection
from specy_road.bundled_scripts.brainstorm_session import (
    BrainstormError,
    BrainstormSession,
    add_idea,
    list_slugs,
    read_session,
    session_path,
    set_status,
    slugify,
    write_session,
)
from specy_road.bundled_scripts.review_node import ReviewError
from specy_road.bundled_scripts.roadmap_gui_lib import apply_llm_env_from_settings
from specy_road.gui_app_helpers import get_repo_root
from specy_road.gui_app_models import (
    BrainstormChatBody,
    BrainstormIdeaBody,
    BrainstormPromoteBody,
    BrainstormSessionBody,
    BrainstormTriageBody,
    ResearchTestBody,
)
from specy_road.pm_gui_concurrency import require_pm_gui_write_header


def _payload(session: BrainstormSession) -> dict[str, Any]:
    return {
        "slug": session.slug,
        "topic": session.topic,
        "under": session.under,
        "mode": session.mode,
        "ideas": [i.to_dict() for i in session.ideas],
        "pending_promotion": [i.id for i in pending_ideas(session)],
    }


def _load(root: Path, slug: str) -> BrainstormSession:
    try:
        return read_session(root, slug)
    except BrainstormError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


def _saved(root: Path, session: BrainstormSession) -> dict[str, Any]:
    write_session(root, session)
    return _payload(session)


def _bad_request(e: BrainstormError) -> HTTPException:
    return HTTPException(status_code=400, detail=str(e))


def _api_sessions() -> dict[str, Any]:
    return {"slugs": list_slugs(get_repo_root())}


def _api_session_get(slug: str = Query(...)) -> dict[str, Any]:
    return _payload(_load(get_repo_root(), slug))


def _api_session_post(body: BrainstormSessionBody) -> dict[str, Any]:
    root = get_repo_root()
    slug = (body.slug or "").strip() or slugify(body.topic or "")
    if not slug:
        raise HTTPException(status_code=400, detail="give the session a topic or a slug")
    if session_path(root, slug).is_file():
        session = _load(root, slug)
        if body.topic:
            session.topic = body.topic.strip()
        if body.under is not None:
            session.under = body.under.strip() or None
    else:
        session = BrainstormSession(
            slug=slug,
            topic=(body.topic or "").strip(),
            under=(body.under or "").strip() or None,
        )
    session.mode = body.mode
    return _saved(root, session)


def _api_chat(body: BrainstormChatBody) -> dict[str, Any]:
    """The session's mode picks the prompt: diverge asks for volume, converge for judgement."""
    root = get_repo_root()
    session = _load(root, body.slug)
    apply_llm_env_from_settings(body.llm)
    if session.mode == "roadmap":
        base = render_recommend_prompt(root, session)
    else:
        base = render_brainstorm_prompt(root, session, count=body.count)
    try:
        return chat_turn(
            [m.model_dump() for m in body.messages],
            system_prompt=base,
            research=body.research,
        )
    except ReviewError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e


def _api_idea(body: BrainstormIdeaBody) -> dict[str, Any]:
    root = get_repo_root()
    session = _load(root, body.slug)
    try:
        add_idea(
            session,
            title=body.title,
            rationale=body.rationale or "",
            kind=body.kind,
            effort=body.effort or "",
            evidence=list(body.evidence or []),
        )
    except BrainstormError as e:
        raise _bad_request(e) from e
    return _saved(root, session)


def _apply_triage(session: BrainstormSession, body: BrainstormTriageBody) -> None:
    """A status change, a content edit, or a recommendation — possibly all three.

    A recommendation is the model's advice, so recording it must not consume
    the PM's accept/reject decision. Same rule as the CLI's ``revise``.
    """
    if body.status is not None:
        set_status(session, body.idea_id, body.status)
    idea = session.by_id(body.idea_id)
    content_changed = False
    for attr in ("title", "rationale", "kind", "effort"):
        value = getattr(body, attr, None)
        if value is not None:
            setattr(idea, attr, value)
            content_changed = True
    if body.recommendation is not None:
        idea.recommendation = body.recommendation
    if content_changed and idea.status == "proposed":
        idea.status = "revised"


def _api_triage(body: BrainstormTriageBody) -> dict[str, Any]:
    root = get_repo_root()
    session = _load(root, body.slug)
    try:
        _apply_triage(session, body)
    except BrainstormError as e:
        raise _bad_request(e) from e
    return _saved(root, session)


def _api_promote(body: BrainstormPromoteBody) -> dict[str, Any]:
    root = get_repo_root()
    session = _load(root, body.slug)
    try:
        results = promote_session(
            root,
            session,
            under=body.under,
            node_type=body.type,
            dry_run=body.dry_run,
        )
    except BrainstormError as e:
        raise _bad_request(e) from e
    if not body.dry_run:
        write_session(root, session)
    return {
        "promoted": [
            {
                "idea_id": r.idea_id,
                "node_id": r.node_id,
                "node_key": r.node_key,
                "title": r.title,
                "parent_id": r.parent_id,
            }
            for r in results
        ],
        "dry_run": body.dry_run,
        "session": _payload(session),
    }


def _api_research_test(body: ResearchTestBody) -> dict[str, Any]:
    ok, msg = test_connection(body.research)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": msg}


def register_brainstorm_routes(api: APIRouter) -> None:
    guard = [Depends(require_pm_gui_write_header)]
    api.get("/brainstorm/sessions")(_api_sessions)
    api.get("/brainstorm/session")(_api_session_get)
    api.post("/brainstorm/session", dependencies=guard)(_api_session_post)
    api.post("/brainstorm/chat", dependencies=guard)(_api_chat)
    api.post("/brainstorm/idea", dependencies=guard)(_api_idea)
    api.post("/brainstorm/triage", dependencies=guard)(_api_triage)
    api.post("/brainstorm/promote", dependencies=guard)(_api_promote)
    # Guarded like the write routes: it takes a caller-supplied URL and fetches
    # it, so leaving it open let any page in the browser use the GUI to probe
    # the host's network.
    api.post("/research/test", dependencies=guard)(_api_research_test)
