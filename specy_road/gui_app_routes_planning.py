"""Constitution, planning artifacts, and planning file API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from roadmap_crud_ops import run_validate_raise
from roadmap_load import load_roadmap
from planning_artifacts import (
    ancestor_planning_paths,
    normalize_planning_dir,
    planning_artifact_paths,
)
from scaffold_planning import scaffold_planning_for_node

from specy_road.constitution_scaffold import (
    ConstitutionExistsError,
    write_constitution,
)
from specy_road.gui_app_helpers import (
    assert_planning_file_api_path,
    get_repo_root,
    safe_rel_path,
)
from specy_road.gui_app_models import (
    ConstitutionScaffoldBody,
    PlanningScaffoldBody,
    PutFileBody,
)
from specy_road.pm_gui_concurrency import require_pm_gui_write_header


def api_constitution_scaffold(
    body: ConstitutionScaffoldBody = Body(default_factory=ConstitutionScaffoldBody),
    _pm: None = Depends(require_pm_gui_write_header),
) -> dict[str, Any]:
    root = get_repo_root()
    force = bool(body.force)
    try:
        result = write_constitution(root, force=force)
    except ConstitutionExistsError as e:
        raise HTTPException(
            status_code=409,
            detail={"message": str(e), "existing": list(e.existing)},
        ) from e
    return {
        "written": list(result.written),
        "skipped_existing": list(result.skipped_existing),
    }


def api_planning_scaffold(
    node_id: str,
    body: PlanningScaffoldBody = Body(default_factory=PlanningScaffoldBody),
    _pm: None = Depends(require_pm_gui_write_header),
) -> dict[str, Any]:
    root = get_repo_root()
    try:
        return scaffold_planning_for_node(
            root,
            node_id.strip(),
            planning_dir=body.planning_dir,
            force=body.force,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def api_planning_artifacts(node_id: str) -> dict[str, Any]:
    root = get_repo_root()
    nodes = load_roadmap(root)["nodes"]
    by_id = {n["id"]: n for n in nodes}
    if node_id not in by_id:
        raise HTTPException(status_code=404, detail="node not found")
    anc_out: list[dict[str, Any]] = []
    for rel, p in ancestor_planning_paths(node_id, by_id, root):
        anc_out.append(
            {
                "role": "ancestor",
                "path": rel,
                "exists": p.is_file(),
            },
        )
    pd = by_id[node_id].get("planning_dir")
    if not isinstance(pd, str) or not pd.strip():
        return {
            "planning_dir": None,
            "ancestor_planning_files": anc_out,
            "files": [],
        }
    try:
        norm = normalize_planning_dir(pd.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    paths = planning_artifact_paths(root, norm)
    p = paths["sheet"]
    out: list[dict[str, Any]] = []
    if p.is_file():
        rel = str(p.relative_to(root)).replace("\\", "/")
        out.append({"role": "sheet", "path": rel, "exists": True})
    else:
        rel = str(p.relative_to(root)).replace("\\", "/")
        out.append({"role": "sheet", "path": rel, "exists": False})
    return {
        "planning_dir": norm,
        "ancestor_planning_files": anc_out,
        "files": out,
    }


def api_planning_get(path: str = Query(..., description="Repo-relative path")) -> dict[str, str]:
    root = get_repo_root()
    p = safe_rel_path(root, path)
    assert_planning_file_api_path(root, p)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    text = p.read_text(encoding="utf-8", errors="replace")
    return {"path": path, "content": text}


def api_planning_put(
    path: str = Query(...),
    body: PutFileBody = Body(...),
    _pm: None = Depends(require_pm_gui_write_header),
) -> dict[str, str]:
    root = get_repo_root()
    p = safe_rel_path(root, path)
    assert_planning_file_api_path(root, p)
    had_file = p.is_file()
    previous: str | None = (
        p.read_text(encoding="utf-8", errors="replace") if had_file else None
    )
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body.content, encoding="utf-8")
        run_validate_raise(root)
    except ValueError as e:
        if had_file and previous is not None:
            p.write_text(previous, encoding="utf-8")
        elif p.is_file():
            p.unlink()
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": "true", "path": path}


def register_planning_routes(api: APIRouter) -> None:
    api.post("/constitution/scaffold")(api_constitution_scaffold)
    api.post("/planning/{node_id}/scaffold")(api_planning_scaffold)
    api.get("/planning/{node_id}/artifacts")(api_planning_artifacts)
    api.get("/planning/file")(api_planning_get)
    api.put("/planning/file")(api_planning_put)
