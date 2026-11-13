"""FastAPI server for the PM Gantt SPA.

Includes roadmap CRUD, planning files, and settings endpoints, publish (scoped git commit and
push), the read-only Workers drawer routes, the read-only orchestration snapshot
(``GET /api/orchestration``), and the one orchestration write: a PM decision from the status modal
(``POST /api/pm-decisions``), behind a per-session code printed at startup.
"""

from __future__ import annotations

import os
import secrets
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from fastapi import APIRouter, Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from specy_road.grind_status import StatusError, build_report
from specy_road.gui_app_helpers import get_repo_root
from specy_road.gui_app_models import PublishRoadmapBody
from specy_road.gui_app_routes_archive import register_archive_routes
from specy_road.gui_app_routes_brainstorm import register_brainstorm_routes
from specy_road.gui_app_routes_core import register_core
from specy_road.gui_app_routes_nodes import register_add_node, register_node_mutations
from specy_road.gui_app_routes_planning import register_planning_routes
from specy_road.gui_app_routes_workspace import (
    register_settings_and_remote,
    register_workspace_routes,
)
from specy_road.pm_gui_concurrency import require_pm_gui_write_header
from specy_road.pm_publish import publish_roadmap, publish_status_dict
from specy_road.worker_cli_render import timeline, usage
from specy_road.worker_reconcile import sync_marks
from specy_road.worker_state import WorkerError, events_since, list_records, load_record
from specy_road.clock import utc_now_iso
from specy_road.decisions import close_entry, decisions_path, read_decisions
from specy_road.decisions_local import load_merged
from specy_road.review_override import (
    OPERATOR,
    PM_GUI,
    blocks_to_settle,
    commit_ledger_entry,
    integration_preflight,
    over_block_preflight,
    record_over_block,
    settle_lines,
)

_PKG_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _PKG_DIR / "pm_gantt_static"

READ_ONLY_ENV = "SPECY_ROAD_GUI_READ_ONLY"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_ALL_METHODS = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


def _register_read_only_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def refuse_writes(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method not in _SAFE_METHODS and request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=403,
                content={"detail": "server is read-only (specy-road gui --read-only)"},
            )
        return await call_next(request)


def _register_publish_routes(api: APIRouter) -> None:
    """Publish roadmap and planning changes: a scoped git commit and push."""

    @api.get("/publish/status")
    def api_publish_status() -> dict:
        """Return git scope status for the Publish toolbar control."""
        return publish_status_dict(get_repo_root())

    @api.post("/publish")
    def api_publish(
        body: PublishRoadmapBody,
        _pm: None = Depends(require_pm_gui_write_header),
    ) -> dict:
        """Stage publish-scope paths, commit, and push to upstream."""
        root = get_repo_root()
        try:
            return publish_roadmap(root, body.message)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e


# Read-only worker routes for the PM GUI's Workers drawer. The records and event logs live in the
# main worktree's ``work/.workers/`` (gitignored; ``docs/orchestration-workers.md``). These routes
# only read them: no stall sweep, no ack, no lock; the coordinator's commands are the writers.
# Phase durations and usage totals are the same arithmetic as ``specy-road worker timeline`` and
# ``worker usage``.


def _last_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not events:
        return None
    e = events[-1]
    return {k: e.get(k) for k in ("seq", "at", "type", "source", "summary")}


def _worker_row(rec, events: list[dict[str, Any]]) -> dict[str, Any]:
    total = usage([(rec, events)])["total"]
    return {"worker_id": rec.worker_id, "node_id": rec.node_id, "harness": rec.harness,
            "model": rec.model, "state": rec.state, "attempt": rec.attempt,
            "flags": list(rec.flags), "updated": rec.updated,
            "last_event": _last_event(events), "total_cost_usd": total["cost_usd"],
            "cost_is_estimate": total["cost_is_estimate"]}


def _api_workers() -> dict[str, Any]:
    root = get_repo_root()
    rows = [_worker_row(r, [e.to_dict() for e in events_since(root, r.worker_id)])
            for r in list_records(root)]
    return {"workers": rows}


def _api_worker_events(worker_id: str) -> dict[str, Any]:
    root = get_repo_root()
    try:
        rec = load_record(root, worker_id)
    except WorkerError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    events = [e.to_dict() for e in events_since(root, worker_id)]
    return {**_worker_row(rec, events), "events": events,
            "phases": timeline(rec, events, sync_marks(root).get(worker_id))["phases"],
            "usage": usage([(rec, events)])["total"]}


def _make_api_router() -> APIRouter:
    """The PM Gantt JSON API router; the worker routes come last, as their own router did."""
    api = APIRouter(prefix="/api")
    register_core(api)
    register_node_mutations(api)
    register_add_node(api)
    register_planning_routes(api)
    register_workspace_routes(api)
    register_settings_and_remote(api)
    _register_publish_routes(api)
    register_archive_routes(api)
    register_brainstorm_routes(api)
    api.get("/workers")(_api_workers)
    api.get("/workers/{worker_id}/events")(_api_worker_events)
    return api


def _main_project_root() -> Path:
    """The main checkout's project root for the snapshot.

    ``get_repo_root`` follows the working directory into a linked worktree; claims, READY files
    and worker records live in the main checkout. A project nested under the git root stays that
    project.
    """
    from specy_road.worktree_env import main_project_root

    return main_project_root(get_repo_root())


def _register_orchestration_route(app: FastAPI) -> None:
    @app.get("/api/orchestration")
    def orchestration() -> JSONResponse:
        """``orchestration.state.snapshot`` of the main project root, with no added keys."""
        from specy_road.orchestration import snapshot

        return JSONResponse(snapshot(_main_project_root()))


def _register_grind_status_route(app: FastAPI, clock: Callable[[], datetime] | None) -> None:
    @app.get("/api/grind-status")
    def grind_status(until: str | None = None, under: str | None = None) -> JSONResponse:
        """``grind-session --status --json``'s object, unchanged; 400 where the CLI exits 2."""
        now = clock() if clock else datetime.now().astimezone()
        try:
            return JSONResponse(build_report(get_repo_root(), until, under, now))
        except StatusError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e


DECISION_CODE_HEADER = "X-PM-Decision-Code"
_ANSWERABLE = ("decision", "human-action")
NOT_STAMPED = "the registry was not stamped"


class _OptionRefused(Exception):
    """The integration branch's entry does not offer the chosen option; nothing is committed."""


def _option_problem(eid: str, option: Any, entry: dict[str, Any] | None) -> str | None:
    """Why ``option`` (a label, or ``None`` for Other) is not one of ``entry``'s recorded
    options."""
    labels = [o.get("label") for o in (entry or {}).get("options") or [] if isinstance(o, dict)]
    if option is not None and option not in labels:
        return (f"option {option!r} is not one of {eid}'s options ({', '.join(labels)}) "
                "nor Other")
    return None


def _refuse_option_at(project: Path, eid: str, option: Any) -> None:
    """:class:`_OptionRefused` when ``project``'s open ledger entry ``eid`` lacks ``option``.

    An entry missing or closed there is left to :func:`close_entry` (409).
    """
    entries = read_decisions(decisions_path(project)).get("entries") or []
    entry = next((e for e in entries if isinstance(e, dict) and e.get("id") == eid), None)
    if entry and entry.get("status") == "open" and (why := _option_problem(eid, option, entry)):
        raise _OptionRefused(why)


def _answer(root: Path, payload: dict[str, Any], words: str) -> tuple[int, dict[str, Any]]:
    """Close an open decision or human-action entry with ``<option>: <words>``.

    For Other (``option`` null) the answer is the words alone. Closed as the operator, channel
    pm-gui, the sheet line left to the coordinator. A shared entry is closed in a temporary
    worktree of the integration branch and committed there, its option checked again against that
    branch's entry; a ``decisions.local.yaml`` one in place.
    """
    eid, option = payload.get("id"), payload.get("option")
    # an unreadable ledger is empty here: the id is unknown
    doc, local_ids, _problems = load_merged(root)
    entry = next((e for e in doc.get("entries") or []
                  if isinstance(e, dict) and e.get("id") == eid), None)
    if entry is None or entry.get("kind") not in _ANSWERABLE:
        return 400, {"detail": f"{eid!r} is not a decision or human-action entry in the ledger"}
    if entry.get("status") != "open":
        return 409, {"detail": f"{eid} is no longer open (closed since the status was loaded); "
                               "nothing was recorded"}
    if why := _option_problem(eid, option, entry):
        return 400, {"detail": why}
    answer = words if option is None else f"{option}: {words}"

    def close(project: Path, local: bool = False) -> dict[str, Any]:
        # the integration branch's entry, which the coordinator may have changed since the GUI read
        if not local:
            _refuse_option_at(project, eid, option)
        return close_entry(project, eid, answer, sheet_text=None, ledger_only=True, local=local,
                           decided_by=OPERATOR, channel=PM_GUI)

    try:
        if eid in local_ids:
            close(root, local=True)
            return 200, {"id": eid, "integration_commit": None, "destination": "local ledger"}
        return _commit_answer(root, eid, close)
    except _OptionRefused as e:
        return 400, {"detail": f"{e} on the integration branch; nothing was recorded"}
    except ValueError as e:   # the local ledger's copied schema refuses channel
        return 400, {"detail": f"{e}; run `specy-road refresh-schemas`; nothing was recorded"}
    # close_entry: not open on the integration branch (closed there, or never committed there)
    except SystemExit:
        return 409, {"detail": f"{eid} is not open on the integration branch; nothing was recorded"}


def _commit_answer(
    root: Path, eid: str, close: Callable[[Path], dict[str, Any]]
) -> tuple[int, dict[str, Any]]:
    """The shared answer: preflight, then ``close`` in a temporary worktree of the integration
    branch, committed."""
    ref, why = integration_preflight(root)
    if why or ref is None:
        return 400, {"detail": why}
    landed = commit_ledger_entry(root, ref, close,
                                 lambda _e: f"roadmap: PM GUI answer closes {eid}")
    if landed.error:
        return 400, {"detail": f"{landed.error}; nothing was recorded"}
    return 200, {"id": eid, "integration_commit": landed.commit, "destination": landed.where}


def _approve_over_block(
    root: Path, payload: dict[str, Any], words: str
) -> tuple[int, dict[str, Any]]:
    """An operator approval over a reviewer block, for the commit and settlement set the modal
    showed (409 otherwise)."""
    from specy_road.review_gate import evaluate_gate
    from specy_road.review_target import ReviewTargetError, resolve_target

    node_id, commit = payload.get("node_id"), payload.get("commit")
    settles = payload.get("settles")
    try:
        t = resolve_target(root, str(node_id))
    except ReviewTargetError as e:
        return 400, {"detail": str(e)}
    branch = (t.entry or {}).get("branch")
    if not branch:
        return 400, {"detail": f"{node_id} is not a claimed leaf; an approval over a block is "
                               "for one leaf's branch"}
    gate = evaluate_gate(root, t.node, t.commit, branch=branch)
    if gate.commit != commit:
        return 409, {"detail": f"the commit under review is now {gate.commit}, not {commit}; "
                               "reload the status"}
    if not gate.blocks:
        return 400, {"detail": f"no reviewer block counts at {gate.commit}; "
                               "nothing to approve over"}
    gate, ref, why = over_block_preflight(root, t.node, gate, branch)
    if why or ref is None:
        return 400, {"detail": f"approval over the block withheld: {why}"}
    if settle_lines(root, gate, blocks_to_settle(root, gate, str(gate.commit))) != settles:
        return 409, {"detail": "what the decision would settle changed since the status was "
                               "loaded; reload it"}
    rec = record_over_block(root, t.node, gate, ref, words, branch,
                            session=f"pm-gui {utc_now_iso()}", channel=PM_GUI)
    landed = rec.landed
    if landed.error or landed.entry is None or rec.gate is None:
        return 400, {"detail": f"{landed.error}; nothing was recorded"}
    body = {"id": landed.entry["id"], "integration_commit": landed.commit,
            "destination": landed.where, "gate_met": rec.gate.passed}
    if not rec.gate.passed:
        body["detail"] = (f"decision {landed.entry['id']} is recorded on {landed.where}, but the "
                          f"review gate is still not met; {NOT_STAMPED}: "
                          + "; ".join(rec.gate.problems()))
    return 200, body


def record_pm_decision(root: Path, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """``(HTTP status, body)`` for one decision; every refusal comes before anything is written."""
    words = payload.get("words")
    if (not isinstance(words, str) or not words.strip()
            or "\n" in words.strip() or "\r" in words.strip()):
        # one line: an answer's `<ID>: <answer>` planning-sheet line is how the coordinator
        # marks it processed
        return 400, {"detail": "words: say why, in your own words, on one line"}
    if payload.get("kind") == "answer":
        return _answer(root, payload, words.strip())
    if payload.get("kind") == "approve-over-block":
        return _approve_over_block(root, payload, words.strip())
    return 400, {"detail": "kind: answer or approve-over-block"}


@asynccontextmanager
async def _draw_decision_code(app: FastAPI) -> AsyncIterator[None]:
    """At server startup (not import): draw the PM decision code and keep it in memory.

    It is shown once to the person who started the server, on its stderr. Never in a file, an
    environment variable, a log line or a response.
    """
    if app.state.decision_code is None:
        app.state.decision_code = secrets.token_urlsafe(16)
        print("PM decisions: enter this code in the Status window to confirm a decision: "
              f"{app.state.decision_code} "
              "(kept in memory only; it changes each time the GUI starts)",
              file=sys.stderr, flush=True)
    yield


def _register_pm_decision_route(app: FastAPI) -> None:
    @app.post("/api/pm-decisions")
    def pm_decision(payload: dict[str, Any] = Body(...),  # noqa: B008
                    code: str | None = Header(None, alias=DECISION_CODE_HEADER)) -> JSONResponse:
        """Record a PM decision (an answer, or an approval over a block).

        403 without the startup code.
        """
        expected = app.state.decision_code
        if (not expected or code is None
                or not secrets.compare_digest(code.encode(), expected.encode())):
            raise HTTPException(status_code=403,
                                detail=f"wrong or missing {DECISION_CODE_HEADER}: enter the code "
                                       "`specy-road gui` printed in its terminal")
        status, body = record_pm_decision(get_repo_root(), payload)
        return JSONResponse(body, status_code=status)


def create_app(read_only: bool | None = None, clock: Callable[[], datetime] | None = None,
               decision_code: str | None = None) -> FastAPI:
    """The app. ``decision_code`` fixes the PM decision code (tests).

    Otherwise one is drawn at startup, and under ``read_only`` none is drawn or printed.
    """
    if read_only is None:
        read_only = os.environ.get(READ_ONLY_ENV) == "1"
    app = FastAPI(title="specy-road PM Gantt API", version="1.0.0",
                  lifespan=None if read_only else _draw_decision_code)
    app.state.decision_code = None if read_only else decision_code
    if read_only:
        _register_read_only_guard(app)
    app.add_middleware(
        CORSMiddleware,
        # Loopback only. The built UI is served from this same origin, so the
        # regex exists for the Vite dev server. With `allow_origins=["*"]` and
        # credentials, Starlette echoes back whichever Origin asked, so any
        # page the user had open could read `/api/settings` — which carries
        # their LLM and git tokens.
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(_make_api_router())
    _register_grind_status_route(app, clock)
    _register_pm_decision_route(app)
    _register_orchestration_route(app)

    # Registered before the SPA fallback so scripts get JSON, not the HTML shell.
    @app.api_route("/api/{rest:path}", methods=_ALL_METHODS, include_in_schema=False)
    def api_not_found(rest: str) -> None:
        raise HTTPException(status_code=404, detail=f"no API route /api/{rest}")

    if _STATIC_DIR.is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=_STATIC_DIR / "assets"),
            name="assets",
        )

        @app.get("/{full_path:path}")
        def spa_fallback(full_path: str) -> FileResponse:
            index = _STATIC_DIR / "index.html"
            if full_path == "" or full_path == "/":
                return FileResponse(index)
            target = (_STATIC_DIR / full_path).resolve()
            try:
                target.relative_to(_STATIC_DIR.resolve())
            except ValueError:
                return FileResponse(index)
            if target.is_file():
                return FileResponse(target)
            return FileResponse(index)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    host = os.environ.get("SPECY_ROAD_GUI_HOST", "127.0.0.1")
    port = int(os.environ.get("SPECY_ROAD_GUI_PORT", "8765"))
    uvicorn.run(
        "specy_road.gui_app:app",
        host=host,
        port=port,
        reload=os.environ.get("SPECY_ROAD_GUI_RELOAD") == "1",
    )


if __name__ == "__main__":
    main()
